# Reddit — r/rust

**Target:** Rust developers

---

**Title:** Built a production desktop app with Tauri v2 — Rust shell managing a Python sidecar with 35+ local AI models

**Body:**

Sharing my experience using Tauri v2 (Rust) for a non-trivial desktop application: **ContextuAI Solo**, a desktop AI assistant.

**What the Rust layer does:**

- **Sidecar management** (`sidecar.rs`): Spawns a PyInstaller-bundled Python backend on launch, health-checks it via HTTP, and kills the process tree on exit. On Windows, this includes `taskkill /T` to clean up llama-cpp threads.

- **IPC bridge** (`commands.rs`): Tauri commands that proxy HTTP requests from the React frontend to the Python sidecar. The frontend calls `api_request` via IPC, Rust forwards it to `http://127.0.0.1:18741`.

- **Window management** (`main.rs`): Boot sequence, system tray, auto-updater via tauri-plugin-updater.

**Interesting challenges:**

1. **Process tree cleanup on Windows:** When the Python sidecar spawns llama-cpp inference threads, a simple `process.kill()` doesn't catch them. Had to use `taskkill /T /F /PID` from Rust to kill the entire tree.

2. **Health check timing:** The Python sidecar takes 2-5 seconds to boot (PyInstaller unpacking). The Rust shell polls `/health` with retries before telling the frontend the backend is ready.

3. **SSE streaming:** The frontend streams AI responses via SSE directly to the Python backend (not through Tauri IPC), because IPC isn't designed for long-lived streaming connections.

**Why Tauri over Electron:**
- ~80MB installed vs 500MB+
- Native Rust performance for process management
- No Chromium bundled — uses the system webview

**Full stack:** Tauri v2 (Rust) + React 19 (TypeScript) + FastAPI (Python) + SQLite + llama-cpp-python

Open source: https://github.com/contextuai/contextuai-solo

Happy to discuss the Tauri v2 sidecar pattern in detail.
