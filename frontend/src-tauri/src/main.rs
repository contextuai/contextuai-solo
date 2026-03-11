#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod sidecar;
mod tray;

use tauri::Manager;

fn main() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_os::init())
        .setup(|app| {
            // Start the FastAPI sidecar
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = sidecar::start_sidecar(&app_handle).await {
                    log::error!("Failed to start sidecar: {}", e);
                }
            });

            // Setup system tray
            tray::setup_tray(app)?;

            Ok(())
        })
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                sidecar::stop_sidecar();
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::api_request,
            commands::get_sidecar_port,
            commands::get_sidecar_status,
        ])
        .run(tauri::generate_context!())
        .expect("error while running ContextuAI Solo");
}
