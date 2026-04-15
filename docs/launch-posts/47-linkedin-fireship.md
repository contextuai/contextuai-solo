# LinkedIn — Fireship / Tech Stack Deep Dive

**Target:** Comment on Fireship's LinkedIn posts about tech stacks, frameworks, or developer trends

---

Desktop AI app tech stack breakdown:

**Shell:** Tauri v2 (Rust) — window management, system tray, auto-updater, sidecar lifecycle. ~80MB vs 500MB+ Electron.

**Frontend:** React 19 + TypeScript strict + Vite + Tailwind. SSE streaming for real-time chat. AbortController for stopping generation mid-stream.

**Backend:** FastAPI (Python) bundled via PyInstaller as a standalone sidecar binary. Spawned by Rust on launch, health-checked, killed on exit.

**Database:** SQLite with a MongoDB compatibility layer. Translates Motor API and query operators ($set, $in, $regex) to SQL/JSON. One .db file, fully portable.

**Inference:** llama-cpp-python running 35+ GGUF models on CPU. Async lock prevents concurrent model access. One-click download from HuggingFace.

**Agents:** 93+ business agents as markdown files. Auto-seeded on first launch. Multi-agent crews with 4 execution modes.

**Built with:** Claude Code (the whole thing, solo developer)

Open source: https://github.com/contextuai/contextuai-solo
