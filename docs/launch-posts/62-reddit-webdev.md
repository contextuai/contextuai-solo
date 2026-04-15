# Reddit — r/webdev

**Target:** Web developers interested in desktop app development

---

**Title:** From web app to desktop app: how I shipped a React + FastAPI project as a native desktop app using Tauri v2

**Body:**

Sharing my experience porting a web stack to a desktop app for **ContextuAI Solo**, an AI assistant with 93+ business agents.

**The stack transition:**
- Web: React SPA + FastAPI backend + MongoDB
- Desktop: Same React SPA + Same FastAPI (as sidecar) + SQLite (via compatibility layer) + Tauri v2 (Rust shell)

**What stayed the same:**
- All React components and routes
- All FastAPI routers and services
- All repository code

**What changed:**
- Added Tauri v2 Rust shell for window management, system tray, auto-updater
- Added transport abstraction — Tauri IPC in production, direct HTTP in dev
- Replaced MongoDB with SQLite via a compatibility layer (~400 LOC)
- Bundled Python backend via PyInstaller into a standalone binary
- Added sidecar management in Rust (spawn, health-check, kill)

**Key learnings for web devs going desktop:**

1. **Tauri v2 is web-dev friendly.** Your React app runs in a webview. Vite HMR works. The main new thing is learning the Rust-side commands for IPC.

2. **The sidecar pattern is underrated.** If you have a Python backend, don't try to rewrite it in Rust. Bundle it with PyInstaller and let Tauri manage the process.

3. **SSE streaming works fine** — just go HTTP direct to the sidecar, don't try to pipe it through Tauri IPC.

4. **Bundle size matters.** ~80MB for Tauri vs 500MB+ for Electron. Your users will notice.

5. **Distribution is the hard part.** Code signing, platform-specific installers, Windows SmartScreen, macOS Gatekeeper — budget time for this.

GitHub: https://github.com/contextuai/contextuai-solo
