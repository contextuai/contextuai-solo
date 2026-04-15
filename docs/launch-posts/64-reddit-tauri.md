# Reddit — r/tauri

**Target:** Tauri developers and community

---

**Title:** Shipped a production Tauri v2 app with a Python sidecar, 35+ local AI models, and auto-updater — here's the architecture

**Body:**

Built **ContextuAI Solo** with Tauri v2 and wanted to share the architecture with the community.

**App overview:** Desktop AI assistant with 93+ business agents, 35+ local GGUF models, multi-agent crews.

**Tauri v2 architecture:**

**`main.rs` — Boot sequence:**
- Initialize Tauri app with plugins (updater, shell, dialog)
- Set up system tray
- Register IPC command handlers
- Spawn sidecar on app ready

**`sidecar.rs` — Python process management:**
- Spawns PyInstaller-bundled Python binary
- Health-checks via HTTP GET to `/health` with retry loop
- Kills process tree on app exit
- Windows-specific: `taskkill /T /F /PID` to catch llama-cpp threads

**`commands.rs` — IPC bridge:**
- `api_request` command proxies frontend HTTP requests to sidecar
- Frontend calls `invoke('api_request', { method, path, body })`
- Rust forwards to `http://127.0.0.1:18741/api/v1/{path}`

**SSE streaming decision:**
Streaming bypasses Tauri IPC entirely. The React frontend streams directly to the Python backend via HTTP SSE. IPC isn't designed for long-lived streaming connections, and the latency of proxying token-by-token through Rust was noticeable.

**Auto-updater:**
Using `tauri-plugin-updater`. Checks for updates on launch, prompts user, downloads and installs.

**Plugins used:**
- tauri-plugin-updater
- tauri-plugin-shell
- tauri-plugin-dialog

**Bundle size:** ~80MB installed on Windows (.msi)

**What I'd tell other Tauri devs:**
1. The sidecar pattern works great for non-Rust backends
2. Don't stream through IPC — go HTTP direct
3. Process tree cleanup on Windows needs extra work
4. Tauri v2's plugin system is solid

GitHub: https://github.com/contextuai/contextuai-solo

Happy to answer Tauri-specific questions.
