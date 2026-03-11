use std::sync::atomic::{AtomicBool, AtomicU16, Ordering};
use tauri::AppHandle;

static SIDECAR_PORT: AtomicU16 = AtomicU16::new(18741);
static SIDECAR_RUNNING: AtomicBool = AtomicBool::new(false);

pub fn get_port() -> u16 {
    SIDECAR_PORT.load(Ordering::Relaxed)
}

pub fn is_running() -> bool {
    SIDECAR_RUNNING.load(Ordering::Relaxed)
}

pub async fn start_sidecar(_app_handle: &AppHandle) -> Result<(), String> {
    // Find an available port
    let port = find_available_port().map_err(|e| e.to_string())?;
    SIDECAR_PORT.store(port, Ordering::Relaxed);

    log::info!("Starting FastAPI sidecar on port {}", port);

    // In development, assume backend is already running
    // In production, spawn the bundled Python executable
    #[cfg(debug_assertions)]
    {
        log::info!("Dev mode: expecting backend at 127.0.0.1:{}", port);
        SIDECAR_RUNNING.store(true, Ordering::Relaxed);
        return Ok(());
    }

    #[cfg(not(debug_assertions))]
    {
        // TODO: Spawn bundled Python backend
        // let _child = std::process::Command::new("contextuai-solo")
        //     .args(["--port", &port.to_string(), "--host", "127.0.0.1"])
        //     .spawn()
        //     .map_err(|e| format!("Failed to start sidecar: {}", e))?;

        SIDECAR_RUNNING.store(true, Ordering::Relaxed);
        Ok(())
    }
}

fn find_available_port() -> Result<u16, std::io::Error> {
    // Try to bind to port 0 to get a random available port
    let listener = std::net::TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    Ok(port)
}
