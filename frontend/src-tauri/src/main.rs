#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod sidecar;
mod tray;

use tauri::{Manager, RunEvent};

fn main() {
    env_logger::init();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        // .plugin(tauri_plugin_notification::init()) // disabled — config deserialization issue
        .plugin(tauri_plugin_os::init())
        .setup(|app| {
            // Start the FastAPI sidecar
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = sidecar::start_sidecar(&app_handle).await {
                    log::error!("Failed to start sidecar: {}", e);
                }
            });

            // Setup system tray (non-fatal — don't block the window)
            if let Err(e) = tray::setup_tray(app) {
                log::error!("Failed to setup tray: {}", e);
            }

            // Ensure the main window is visible
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }

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
        .build(tauri::generate_context!())
        .expect("error while building ContextuAI Solo");

    app.run(|_app_handle, event| {
        if let RunEvent::Exit = event {
            log::info!("App exiting — stopping sidecar");
            sidecar::stop_sidecar();
        }
    });
}
