from __future__ import annotations

import io
import os
import platform
import re
import subprocess
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from sidecar.services.tasks import TaskCancelled, TaskContext, start_task
from sidecar.utils.path_resolver import get_runtimes_dir
from sidecar.utils.file_ops import safe_rmtree, safe_write_text

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADOPTIUM_API = "https://api.adoptium.net/v3/assets/latest/{major}/hotspot?os=windows&arch=x64&image_type=jre&heap_size=normal"
DOWNLOAD_CHUNK = 1 << 17  # 128 KiB

# Well-known install roots to probe on Windows.
_SCAN_ROOTS: List[str] = [
    r"C:\Program Files\Java",
    r"C:\Program Files\Eclipse Adoptium",
    r"C:\Program Files\Microsoft",
    r"C:\Program Files\Zulu",
    r"C:\Program Files\BellSoft\LibericaJDK",
    r"C:\Program Files (x86)\Java",
]

# Registry hives/keys that list installed JREs/JDKs on Windows.
_REGISTRY_KEYS: List[Tuple[str, str]] = [
    ("HKLM", r"SOFTWARE\JavaSoft\Java Runtime Environment"),
    ("HKLM", r"SOFTWARE\JavaSoft\JRE"),
    ("HKLM", r"SOFTWARE\JavaSoft\Java Development Kit"),
    ("HKLM", r"SOFTWARE\JavaSoft\JDK"),
    ("HKLM", r"SOFTWARE\WOW6432Node\JavaSoft\Java Runtime Environment"),
    ("HKLM", r"SOFTWARE\WOW6432Node\JavaSoft\JRE"),
    ("HKLM", r"SOFTWARE\Eclipse Adoptium\JRE"),
    ("HKLM", r"SOFTWARE\Eclipse Foundation\JDK"),
]

_JAVA_VERSION_RE = re.compile(
    r'version\s+"?(?:1\.)?(\d+)[\._]?(\d*)[\._]?(\d*)[_\d]*"?',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Version mapping: Minecraft → required Java major
# ---------------------------------------------------------------------------

def required_java_for_mc(mc_version: str) -> int:
    """
    Return the minimum Java major version required for a given MC version string.

    Matrix:
      MC < 1.17           → Java 8
      1.17 ≤ MC < 1.20.5  → Java 17
      MC ≥ 1.20.5         → Java 21
    """
    parsed = _parse_mc_version(mc_version)
    if parsed is None:
        return 17  # safe default for unknown strings

    minor, patch = parsed
    if minor < 17:
        return 8
    if (minor, patch) < (20, 5):
        return 17
    return 21


def _parse_mc_version(version: str) -> Optional[Tuple[int, int]]:
    """
    Parse a Minecraft version string like '1.20.4', '1.21', '1.8.9' etc.
    Returns (minor, patch) or None if unparseable.
    """
    m = re.match(r"^1\.(\d+)(?:\.(\d+))?", version.strip())
    if not m:
        return None
    minor = int(m.group(1))
    patch = int(m.group(2)) if m.group(2) else 0
    return minor, patch


def to_console_java_exe(path_str: str) -> str:
    """Ensure path points to java.exe (console binary) rather than javaw.exe."""
    p = (path_str or "").strip()
    if not p:
        return ""
    if p.lower().endswith("javaw.exe"):
        cand = Path(p).with_name("java.exe")
        if cand.is_file():
            return str(cand)
        return p[:-9] + "java.exe"
    return p


def resolve_java_executable(mc_version: str = "", custom_path: str = "") -> str:
    """
    Resolve an absolute path to a suitable java.exe binary.

    Resolution order:
      1. User-configured custom_path (if set and valid).
      2. PhantomX-managed runtime (<runtimes_dir>/jre-{target}/bin/java.exe).
      3. First detected installation matching the required major version.
      4. Any detected Java installation.
      5. PATH lookup for 'java.exe' / 'java'.
    Always ensures the executable is java.exe (console app, suitable for CLI installers).
    """
    # 1. Custom path
    if custom_path and custom_path.strip():
        cp = to_console_java_exe(custom_path.strip())
        if Path(cp).is_file():
            return cp

    # Determine target major version if mc_version provided
    target_major = required_java_for_mc(mc_version) if mc_version else 0

    # 2. PhantomX-managed runtimes
    if target_major > 0:
        managed_exe = get_runtimes_dir() / f"jre-{target_major}" / "bin" / "java.exe"
        if managed_exe.is_file():
            return str(managed_exe)

    # 3 & 4. Scanned installations
    installs = scan_java_installations()
    if target_major > 0:
        for item in installs:
            if item.get("major") == target_major:
                p = to_console_java_exe(item.get("path", ""))
                if Path(p).is_file():
                    return p

    # Fallback to any detected installation
    for item in installs:
        p = to_console_java_exe(item.get("path", ""))
        if Path(p).is_file():
            return p

    # 5. Check PATH
    from shutil import which
    found = which("java.exe") or which("java")
    if found:
        return str(Path(found).resolve())

    return ""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_java_version(output: str) -> Optional[int]:
    """
    Extract the Java major version from the text output of `java -version`.
    Returns None if unparseable.
    """
    m = _JAVA_VERSION_RE.search(output)
    if not m:
        return None
    first = int(m.group(1))
    # 1.8.x → 8, 17.x → 17, 21 → 21
    return int(m.group(2)) if first == 1 and m.group(2) else first


def get_java_info(java_exe: str | Path) -> Optional[Dict[str, Any]]:
    """
    Run `java -version` on *java_exe* and return a normalised dict, or None on
    failure.  Output is on stderr for all known JVM implementations.
    """
    exe = str(java_exe)
    try:
        result = subprocess.run(
            [exe, "-version"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        raw = (result.stderr or result.stdout or "").strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    major = _parse_java_version(raw)
    if major is None:
        return None

    arch = "x64" if "64-Bit" in raw else ("x86" if "32-Bit" in raw else "unknown")
    version_line = raw.splitlines()[0] if raw else "unknown"

    return {
        "path": exe,
        "version_string": version_line,
        "major": major,
        "arch": arch,
    }


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def _probe_exe(candidate: Path) -> Optional[Dict[str, Any]]:
    """Return a JavaInstall dict if *candidate* is a working java.exe, else None."""
    if not candidate.is_file():
        return None
    info = get_java_info(candidate)
    return info


def _find_java_in_dir(base: Path) -> List[Dict[str, Any]]:
    """Scan a directory root for java executables (one or two levels deep)."""
    results: List[Dict[str, Any]] = []
    if not base.is_dir():
        return results

    # Pattern: base/bin/java.exe  or  base/jre-XX/bin/java.exe
    for pattern in ("bin/java.exe", "bin/javaw.exe"):
        hit = _probe_exe(base / pattern)
        if hit:
            results.append(hit)
            break

    for child in base.iterdir():
        if not child.is_dir():
            continue
        for pattern in ("bin/java.exe",):
            hit = _probe_exe(child / pattern)
            if hit:
                results.append(hit)
                break

    return results


def _scan_registry() -> List[str]:
    """
    Query the Windows Registry for JavaHome paths.
    Returns a list of paths (may not exist on disk yet).
    Silently skips on non-Windows or if winreg is unavailable.
    """
    paths: List[str] = []
    if platform.system() != "Windows":
        return paths

    try:
        import winreg
    except ImportError:
        return paths

    def _hive(name: str):
        return getattr(winreg, name, None)

    hklm = _hive("HKEY_LOCAL_MACHINE")
    if hklm is None:
        return paths

    for _hive_name, key_path in _REGISTRY_KEYS:
        try:
            with winreg.OpenKey(hklm, key_path) as hkey:  # type: ignore[attr-defined]
                # Sub-keys are version strings like "21.0.3"
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(hkey, i)  # type: ignore[attr-defined]
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(hkey, sub_name) as subkey:  # type: ignore[attr-defined]
                            home, _ = winreg.QueryValueEx(subkey, "JavaHome")  # type: ignore[attr-defined]
                            if home and isinstance(home, str):
                                paths.append(home)
                    except OSError:
                        continue
        except OSError:
            continue

    return paths


def scan_java_installations() -> List[Dict[str, Any]]:
    """
    Discover all JRE/JDK installations visible to the launcher.

    Search order (first unique path wins):
    1. JAVA_HOME environment variable
    2. PATH (first `java.exe` on PATH)
    3. Windows Registry (JavaHome values)
    4. Well-known install directories
    5. PhantomX-managed runtimes in <runtimes_dir>
    """
    seen_paths: set[str] = set()
    results: List[Dict[str, Any]] = []

    def _add(info: Dict[str, Any], source: str) -> None:
        key = info["path"].lower()
        if key not in seen_paths:
            seen_paths.add(key)
            results.append({**info, "source": source})

    # 1. JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "").strip()
    if java_home:
        for info in _find_java_in_dir(Path(java_home)):
            _add(info, "env_java_home")

    # 2. PATH — `java -version` directly, which may resolve via PATH
    from shutil import which
    java_on_path = which("java")
    if java_on_path:
        info = get_java_info(java_on_path)
        if info:
            _add(info, "system_path")

    # 3. Windows Registry
    for reg_path in _scan_registry():
        for info in _find_java_in_dir(Path(reg_path)):
            _add(info, "registry")

    # 4. Well-known roots
    for root_str in _SCAN_ROOTS:
        for info in _find_java_in_dir(Path(root_str)):
            _add(info, "system")

    # 5. PhantomX-managed runtimes
    runtimes_dir = get_runtimes_dir()
    if runtimes_dir.is_dir():
        for child in sorted(runtimes_dir.iterdir()):
            if not child.is_dir():
                continue
            for info in _find_java_in_dir(child):
                _add(info, "phantomx")

    logger.info(f"Java scan found {len(results)} installation(s)")
    return results


# ---------------------------------------------------------------------------
# Adoptium download
# ---------------------------------------------------------------------------

def _fetch_adoptium_asset(major: int) -> Optional[Dict[str, Any]]:
    """
    Call the Adoptium API to get the download URL + size for a JRE build.
    Returns a dict with keys: download_url, filename, size_bytes.
    Returns None on network error or unexpected response structure.
    """
    url = ADOPTIUM_API.format(major=major)
    logger.info(f"Querying Adoptium API: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PhantomX-Launcher/2.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            import json as _json
            data = _json.loads(resp.read())
    except urllib.error.URLError as e:
        logger.error(f"Adoptium API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Adoptium API unexpected error: {e}")
        return None

    if not data or not isinstance(data, list) or len(data) == 0:
        logger.error(f"Adoptium API returned empty list for Java {major}")
        return None

    asset = data[0]
    try:
        binary = asset["binary"]
        package = binary["package"]
        return {
            "download_url": package["link"],
            "filename": package["name"],
            "size_bytes": package.get("size", 0),
            "checksum": package.get("checksum", ""),
            "checksum_link": package.get("checksum_link", ""),
        }
    except (KeyError, TypeError) as e:
        logger.error(f"Adoptium API response parse error: {e}")
        return None


def _strip_root_extract(zip_data: bytes, dest: Path) -> None:
    """
    Extract a ZIP archive into *dest*, stripping the top-level folder.

    Adoptium archives look like:
      jdk-21.0.3+9-jre/bin/java.exe
      jdk-21.0.3+9-jre/release
      ...

    We strip that root component so the result is:
      <dest>/bin/java.exe
      <dest>/release
      ...

    This ensures the path `bin/java.exe` inside the destination is always
    consistent regardless of Adoptium's versioned folder name (RULE 2).
    """
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        members = zf.infolist()
        if not members:
            return

        # Determine the common root prefix (first path component).
        first_parts = members[0].filename.split("/", 1)
        root_prefix = first_parts[0] + "/" if len(first_parts) > 1 else ""

        dest.mkdir(parents=True, exist_ok=True)
        for member in members:
            # Strip the root folder from the path.
            rel_path = member.filename
            if root_prefix and rel_path.startswith(root_prefix):
                rel_path = rel_path[len(root_prefix):]

            if not rel_path:  # was the root folder entry itself
                continue

            target = dest / rel_path

            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                data = zf.read(member.filename)
                target.write_bytes(data)


def download_java(major: int) -> str:
    """
    Start a background task that downloads and installs JRE *major* from
    Adoptium.  Returns the task_id immediately (RULE 1).
    """
    def _worker(ctx: TaskContext) -> Dict[str, Any]:
        ctx.log(f"Starting Java {major} download via Adoptium API…")
        ctx.progress(0, 100, f"Fetching Adoptium metadata for Java {major}…")

        # ── 1. Query API ───────────────────────────────────────────────────
        ctx.check_cancelled()
        asset = _fetch_adoptium_asset(major)
        if asset is None:
            raise RuntimeError(
                f"Could not fetch Adoptium metadata for Java {major}. "
                "Check your internet connection."
            )

        download_url: str = asset["download_url"]
        total_bytes: int = asset["size_bytes"] or 0
        filename: str = asset["filename"]
        ctx.log(f"Resolved: {filename} ({total_bytes // (1024*1024)} MB)")

        # ── 2. Download ────────────────────────────────────────────────────
        ctx.check_cancelled()
        ctx.progress(5, 100, f"Downloading {filename}…")

        try:
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "PhantomX-Launcher/2.0"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                chunks: List[bytes] = []
                downloaded = 0
                while True:
                    ctx.check_cancelled()
                    chunk = resp.read(DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if total_bytes > 0:
                        pct = int(5 + 85 * downloaded / total_bytes)
                        ctx.progress(pct, 100, f"Downloading… {downloaded // (1024*1024)} MB / {total_bytes // (1024*1024)} MB")
                zip_data = b"".join(chunks)
        except urllib.error.URLError as e:
            raise RuntimeError(f"Download failed: {e}") from e

        ctx.log(f"Download complete ({len(zip_data) // (1024*1024)} MB). Extracting…")
        ctx.progress(90, 100, "Extracting archive…")

        # ── 3. Wipe old installation & extract ─────────────────────────────
        ctx.check_cancelled()
        dest_dir = get_runtimes_dir() / f"jre-{major}"

        if dest_dir.exists():
            ctx.log(f"Removing existing installation at {dest_dir}…")
            result = safe_rmtree(dest_dir)
            if not result.ok:
                raise RuntimeError(f"Could not remove old JRE: {result.error}")

        try:
            _strip_root_extract(zip_data, dest_dir)
        except (zipfile.BadZipFile, Exception) as e:
            raise RuntimeError(f"Extraction failed: {e}") from e

        # ── 4. Verify ──────────────────────────────────────────────────────
        java_exe = dest_dir / "bin" / "java.exe"
        if not java_exe.is_file():
            raise RuntimeError(
                f"Extraction succeeded but bin/java.exe not found at {dest_dir}. "
                "The archive may have an unexpected layout."
            )

        info = get_java_info(java_exe)
        if info is None:
            raise RuntimeError("Extracted java.exe did not respond to -version. The archive may be corrupted.")

        # Auto-save newly installed Java to settings so the launcher recognizes it immediately
        from sidecar.services.core_service import save_settings
        saved_settings = save_settings({"java_path": str(java_exe)})
        ctx.log(f"Auto-saved java_path in settings: {java_exe}")

        ctx.log(f"Java {major} installed successfully at {dest_dir}")
        ctx.log(f"Version: {info['version_string']}")
        ctx.progress(100, 100, f"Java {major} ready")

        return {
            "major": major,
            "path": str(java_exe),
            "version_string": info["version_string"],
            "dest": str(dest_dir),
            "settings": saved_settings,
        }

    task_id = start_task(_worker, name=f"java-download-{major}")
    logger.info(f"Java {major} download task started: {task_id}")
    return task_id
