# LinkedIn — ThePrimeagen / Rust & Performance

**Target:** Comment on ThePrimeagen's LinkedIn posts about Rust, performance, or anti-Electron

---

The "Electron is fine" crowd should see this comparison:

**ContextuAI Solo (Tauri v2):**
- ~80MB installed
- Rust shell managing process lifecycle
- Native window management, system tray
- Python sidecar spawned and health-checked by Rust
- Process tree cleanup on exit (including llama-cpp threads on Windows via taskkill /T)

**Equivalent Electron app:**
- 500MB+ installed
- Chromium bundled for... a local app
- Memory usage: yes

Tauri v2 handled everything I threw at it: sidecar process management, IPC between Rust and React, auto-updater, system tray, and SSE streaming for real-time AI chat.

The app runs 35+ local GGUF models on CPU with 93+ business agents. Desktop-native AI that respects your RAM.

Open source: https://github.com/contextuai/contextuai-solo
