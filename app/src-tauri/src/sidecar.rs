use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdout, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::time::timeout;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

const HANDSHAKE_PREFIX: &str = "PHANTOMX_READY:";
/// 15s, not 5s: on a cold start Windows Defender scans the Nuitka-compiled
/// sidecar binary before it runs, which pushes first boot to 8-10 seconds.
const HANDSHAKE_TIMEOUT_SECS: u64 = 15;

#[cfg(windows)]
const SIDECAR_BINARIES: [&str; 2] = ["phantomx-sidecar.exe", "main.exe"];
#[cfg(not(windows))]
const SIDECAR_BINARIES: [&str; 2] = ["phantomx-sidecar", "main"];

#[derive(Debug, Clone, serde::Serialize)]
pub struct SidecarInfo {
    pub port: u16,
    pub token: String,
}

pub struct SidecarState {
    pub child: Arc<Mutex<Option<Child>>>,
    pub info: Arc<Mutex<Option<SidecarInfo>>>,
}

impl SidecarState {
    pub fn kill_child(&self) {
        if let Ok(mut child) = self.child.lock() {
            if let Some(mut process) = child.take() {
                let _ = process.kill();
                let _ = process.wait();
            }
        }
    }
}

impl Drop for SidecarState {
    fn drop(&mut self) {
        self.kill_child();
    }
}

/// How the sidecar is started: a compiled binary in the portable release layout,
/// or `python -m sidecar.main` from the repository during development.
#[derive(Debug)]
enum SidecarSource {
    Bundled(PathBuf),
    PythonModule(PathBuf),
}

fn exe_dir() -> Option<PathBuf> {
    std::env::current_exe()
        .ok()?
        .parent()
        .map(|p| p.to_path_buf())
}

/// Portable layout: <base>/binaries/sidecar/phantomx-sidecar.exe
fn find_bundled(base: &Path) -> Option<PathBuf> {
    for name in SIDECAR_BINARIES {
        let candidate = base.join("binaries").join("sidecar").join(name);
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

/// Dev layout: the nearest ancestor holding sidecar/main.py
fn find_project_root(start: &Path) -> Option<PathBuf> {
    start
        .ancestors()
        .find(|dir| dir.join("sidecar").join("main.py").is_file())
        .map(|dir| dir.to_path_buf())
}

fn resolve_source() -> Result<SidecarSource, String> {
    if let Ok(custom) = std::env::var("PHANTOMX_SIDECAR_EXE") {
        let path = PathBuf::from(custom);
        if path.is_file() {
            return Ok(SidecarSource::Bundled(path));
        }
    }

    if let Some(dir) = exe_dir() {
        for base in dir.ancestors().take(4) {
            if let Some(found) = find_bundled(base) {
                return Ok(SidecarSource::Bundled(found));
            }
        }
    }

    let mut roots: Vec<PathBuf> = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        roots.push(cwd);
    }
    if let Some(dir) = exe_dir() {
        roots.push(dir);
    }
    roots.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));

    for start in roots {
        if let Some(root) = find_project_root(&start) {
            return Ok(SidecarSource::PythonModule(root));
        }
    }

    Err(concat!(
        "Sidecar not found: expected binaries/sidecar/phantomx-sidecar.exe next to ",
        "the executable, or sidecar/main.py in a parent directory"
    )
    .to_string())
}

fn python_program() -> String {
    std::env::var("PHANTOMX_PYTHON").unwrap_or_else(|_| "python".to_string())
}

fn build_command(source: &SidecarSource) -> Command {
    let mut cmd = match source {
        SidecarSource::Bundled(exe) => {
            let mut c = Command::new(exe);
            if let Some(dir) = exe.parent() {
                c.current_dir(dir);
            }
            c
        }
        SidecarSource::PythonModule(root) => {
            let mut c = Command::new(python_program());
            c.args(["-m", "sidecar.main"]).current_dir(root);
            c
        }
    };

    cmd.stdout(Stdio::piped()).stderr(Stdio::inherit());

    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    cmd
}

/// Reads stdout until the handshake line appears, ignoring anything before it.
fn read_handshake(stdout: ChildStdout) -> Result<String, String> {
    let mut reader = BufReader::new(stdout);
    let mut line = String::new();

    loop {
        line.clear();
        let bytes = reader
            .read_line(&mut line)
            .map_err(|e| format!("IO error reading sidecar stdout: {}", e))?;

        if bytes == 0 {
            return Err("Sidecar exited before sending the handshake".to_string());
        }

        let trimmed = line.trim();
        if trimmed.starts_with(HANDSHAKE_PREFIX) {
            return Ok(trimmed.to_string());
        }
    }
}

fn parse_handshake(line: &str) -> Result<SidecarInfo, String> {
    let payload = line
        .strip_prefix(HANDSHAKE_PREFIX)
        .ok_or_else(|| format!("Invalid handshake format: '{}'", line))?;

    let (port_str, token) = payload
        .split_once(':')
        .ok_or_else(|| format!("Invalid handshake format: '{}'", line))?;

    let port: u16 = port_str
        .parse()
        .map_err(|_| format!("Invalid port in handshake: {}", port_str))?;

    if token.is_empty() {
        return Err("Handshake carried an empty token".to_string());
    }

    Ok(SidecarInfo {
        port,
        token: token.to_string(),
    })
}

fn kill(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

/// Spawns the Python sidecar and waits for the handshake (HANDSHAKE_TIMEOUT_SECS).
pub async fn spawn_sidecar() -> Result<(Child, SidecarInfo), String> {
    let source = resolve_source()?;

    let mut child = build_command(&source)
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar ({:?}): {}", source, e))?;

    let stdout = match child.stdout.take() {
        Some(stdout) => stdout,
        None => {
            kill(&mut child);
            return Err("Failed to capture sidecar stdout".to_string());
        }
    };

    let result = timeout(
        Duration::from_secs(HANDSHAKE_TIMEOUT_SECS),
        tokio::task::spawn_blocking(move || read_handshake(stdout)),
    )
    .await;

    let line = match result {
        Err(_) => {
            kill(&mut child);
            return Err(format!(
                "Timeout: sidecar did not send handshake within {} seconds",
                HANDSHAKE_TIMEOUT_SECS
            ));
        }
        Ok(Err(e)) => {
            kill(&mut child);
            return Err(format!("Handshake task failed: {}", e));
        }
        Ok(Ok(Err(e))) => {
            kill(&mut child);
            return Err(e);
        }
        Ok(Ok(Ok(line))) => line,
    };

    match parse_handshake(&line) {
        Ok(info) => Ok((child, info)),
        Err(e) => {
            kill(&mut child);
            Err(e)
        }
    }
}

/// Tauri command to get sidecar connection info
#[tauri::command]
pub fn get_sidecar_info(state: tauri::State<SidecarState>) -> Result<SidecarInfo, String> {
    state
        .info
        .lock()
        .map_err(|_| "Failed to lock info".to_string())?
        .clone()
        .ok_or("Sidecar not initialized".to_string())
}

/// Initialize sidecar state during Tauri setup
pub async fn init_sidecar_state() -> Result<SidecarState, String> {
    let (child, info) = spawn_sidecar().await?;

    Ok(SidecarState {
        child: Arc::new(Mutex::new(Some(child))),
        info: Arc::new(Mutex::new(Some(info))),
    })
}
