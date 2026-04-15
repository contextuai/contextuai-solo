# Reddit — r/selfhosted

**Target:** Self-hosted community

---

**Title:** Open-sourced a self-hosted desktop AI assistant — 93+ business agents, 35+ local models, no cloud dependency

**Body:**

Just open-sourced **ContextuAI Solo** — a desktop AI assistant designed for people who want AI agents running on their own hardware.

**Why self-hosters will like this:**

- Everything runs locally — Python backend as a sidecar process, SQLite database, GGUF models on CPU
- No telemetry, no phoning home, no accounts, no cloud sync
- Data stored at `~/.contextuai-solo/` — back it up, move it, nuke it, your choice
- Models stored at `~/.contextuai-solo/models/` — standard GGUF files, drop your own in
- ~80MB installed (Tauri v2, not Electron)

**What it does:**

- 93+ pre-built business agents (strategy, marketing, finance, ops, HR, legal, product, research, creative, analytics, IT security)
- Create your own custom agents
- Multi-agent crews — chain agents together in sequential, parallel, pipeline, or autonomous modes
- 35+ GGUF models — DeepSeek R1, Qwen 3.5, Llama 3.1, Phi-4, Mistral, Gemma 3
- One-click model download from HuggingFace
- Optional: connect Anthropic Claude / AWS Bedrock if you want cloud models too

**Tech:** Tauri v2 (Rust) + React 19 + FastAPI + SQLite + llama-cpp-python

**Installers:** Windows (.msi/.exe), macOS (.dmg), Linux (.deb/.AppImage)

Beta release — feedback welcome.

GitHub: https://github.com/contextuai/contextuai-solo
