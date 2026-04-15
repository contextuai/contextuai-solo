# Reddit — r/selfhosted (Detailed)

**Target:** Self-hosting enthusiasts who care about control and portability

---

**Title:** Open-sourced a self-hosted desktop AI assistant — everything runs locally, single SQLite file, no Docker required

**Body:**

Hey r/selfhosted,

Built **ContextuAI Solo** for people who want AI agents on their own hardware without the cloud dependency.

**Why self-hosters will care:**

- **Single SQLite file** — all data at `~/.contextuai-solo/data/contextuai.db`. Back it up, sync it, inspect it with any SQLite tool.
- **Models are just files** — GGUF files at `~/.contextuai-solo/models/`. Standard format, no proprietary container.
- **No Docker required** — native desktop app, ~80MB installed. Though Docker Compose is available if you want to run just the backend.
- **No accounts, no auth** — desktop mode uses a static admin user. No login screen, no tokens.
- **No telemetry** — zero analytics, zero phoning home. Audit the source code yourself.
- **No internet required after setup** — download models once, then go offline forever.

**What it does:**

- 93+ business agents (strategy, marketing, finance, ops, HR, legal, product, research, creative, analytics, IT security)
- Custom agent builder — define your own system prompts
- Multi-agent crews with 4 execution modes
- 35+ GGUF models via llama-cpp-python on CPU
- One-click model download from HuggingFace
- Drop custom .gguf files into the models folder
- Optional: connect Anthropic Claude or AWS Bedrock

**Data layout:**
```
~/.contextuai-solo/
├── data/
│   └── contextuai.db          # All app data (SQLite)
├── models/
│   ├── deepseek-r1-14b.gguf   # Downloaded models
│   ├── qwen3.5-9b.gguf
│   └── ...
└── logs/
```

**Tech:** Tauri v2 (Rust) + React 19 + FastAPI (Python sidecar) + SQLite

**Installers:** Windows (.msi/.exe), macOS (.dmg), Linux (.deb/.AppImage)

**Docker (backend only):**
```bash
docker compose up
# Then open the frontend separately
```

GitHub: https://github.com/contextuai/contextuai-solo

Beta release. Feedback welcome — especially from Linux users.
