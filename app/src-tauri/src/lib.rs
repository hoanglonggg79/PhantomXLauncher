mod sidecar;

use sidecar::{get_sidecar_info, init_sidecar_state, SidecarState};
use tauri::Manager;

#[tauri::command]
async fn hide_launcher(window: tauri::Window) -> Result<(), String> {
    window.hide().map_err(|e| e.to_string())
}

#[tauri::command]
async fn show_launcher(window: tauri::Window) -> Result<(), String> {
    window.show().map_err(|e| e.to_string())?;
    window.set_focus().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
async fn close_launcher(window: tauri::Window, state: tauri::State<'_, SidecarState>) -> Result<(), String> {
    state.kill_child();
    window.close().map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::async_runtime::block_on(async {
        let sidecar_state = init_sidecar_state()
            .await
            .expect("Failed to initialize sidecar. Is Python installed and sidecar/main.py valid?");

        let app = tauri::Builder::default()
            .plugin(tauri_plugin_opener::init())
            .manage(sidecar_state)
            .invoke_handler(tauri::generate_handler![
                get_sidecar_info,
                hide_launcher,
                show_launcher,
                close_launcher
            ])
            .build(tauri::generate_context!())
            .expect("error while building tauri application");

        app.run(|app_handle, event| {
            if let tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app_handle.try_state::<SidecarState>() {
                    state.kill_child();
                }
            }
        });
    });
}

