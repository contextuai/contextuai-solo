use std::sync::atomic::{AtomicBool, AtomicU16, Ordering};
use std::sync::Mutex;
use tauri::{AppHandle, Manager};

static SIDECAR_PORT: AtomicU16 = AtomicU16::new(18741);
static SIDECAR_RUNNING: AtomicBool = AtomicBool::new(false);
static SIDECAR_CHILD: Mutex<Option<std::process::Child>> = Mutex::new(None);

pub fn get_port() -> u16 {
    SIDECAR_PORT.load(Ordering::Relaxed)
}

pub fn is_running() -> bool {
    SIDECAR_RUNNING.load(Ordering::Relaxed)
}

pub fn stop_sidecar() {
    if let Ok(mut guard) = SIDECAR_CHILD.lock() {
        if let Some(ref mut child) = *guard {
            let _ = child.kill();
            let _ = child.wait();
            log::info!("Sidecar process stopped");
        }
        *guard = None;
    }
    SIDECAR_RUNNING.store(false, Ordering::Relaxed);
}

pub async fn start_sidecar(app_handle: &AppHandle) -> Result<(), String> {
    // Find an available port
    let port = find_available_port().map_err(|e| e.to_string())?;
    SIDECAR_PORT.store(port, Ordering::Relaxed);

    log::info!("Starting FastAPI sidecar on port {}", port);

    // In development, assume backend is already running
    #[cfg(debug_assertions)]
    {
        log::info!("Dev mode: expecting backend at 127.0.0.1:{}", port);
        SIDECAR_RUNNING.store(true, Ordering::Relaxed);
        return Ok(());
    }

    #[cfg(not(debug_assertions))]
    {
        // Resolve the sidecar binary path
        let resource_dir = app_handle
            .path()
            .resource_dir()
            .map_err(|e| format!("Failed to get resource dir: {}", e))?;

        // The sidecar is bundled alongside the app
        let sidecar_dir = resource_dir.join("sidecar");
        let sidecar_exe = if cfg!(target_os = "windows") {
            sidecar_dir.join("contextuai-solo-backend.exe")
        } else {
            sidecar_dir.join("contextuai-solo-backend")
        };

        if !sidecar_exe.exists() {
            return Err(format!(
                "Sidecar binary not found at: {}",
                sidecar_exe.display()
            ));
        }

        log::info!("Spawning sidecar from: {}", sidecar_exe.display());

        let child = std::process::Command::new(&sidecar_exe)
            .args(["--port", &port.to_string(), "--host", "127.0.0.1"])
            .current_dir(&sidecar_dir)
            .spawn()
            .map_err(|e| format!("Failed to start sidecar: {}", e))?;

        if let Ok(mut guard) = SIDECAR_CHILD.lock() {
            *guard = Some(child);
        }

        // Wait for the backend to become healthy
        let url = format!("http://127.0.0.1:{}/health", port);
        for i in 0..30 {
            tokio::time::sleep(std::time::Duration::from_secs(1)).await;
            if let Ok(resp) = reqwest::get(&url).await {
                if resp.status().is_success() {
                    log::info!("Sidecar healthy after {} seconds", i + 1);
                    SIDECAR_RUNNING.store(true, Ordering::Relaxed);
                    return Ok(());
                }
            }
        }

        Err("Sidecar failed to become healthy within 30 seconds".to_string())
    }
}

fn find_available_port() -> Result<u16, std::io::Error> {
    let listener = std::net::TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    Ok(port)
}
