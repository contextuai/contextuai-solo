# Reddit — r/PrivacyGuides (or r/privacy)

**Target:** Privacy-conscious users

---

**Title:** Open-source desktop AI assistant — zero telemetry, zero cloud, all data on your machine

**Body:**

Built **ContextuAI Solo** for people who want AI capabilities without the privacy tradeoffs.

**Privacy architecture:**

- **No network calls** (when using local models) — the app doesn't phone home, ever
- **No telemetry** — zero analytics, zero tracking, zero usage data collection
- **No accounts** — no login, no registration, no email required
- **No cloud sync** — all data stays in a local SQLite database
- **Local inference** — 35+ GGUF models run on your CPU via llama-cpp-python
- **Auditable** — fully open source, inspect every line of code

**Data locations:**
```
~/.contextuai-solo/
├── data/contextuai.db    # All app data (SQLite)
├── models/               # Downloaded GGUF model files
└── logs/                 # Local logs only
```

**What it does:**
- 93+ pre-built AI agents for business tasks (strategy, marketing, finance, HR, legal, etc.)
- Custom agent builder
- Multi-agent crews
- 35+ local AI models (DeepSeek R1, Qwen 3.5, Llama 3.1, Phi-4, Mistral)
- One-click model download from HuggingFace (the only network call, and only when you explicitly download)

**Optional cloud (your choice):**
If you want more powerful models, you can connect Anthropic Claude or AWS Bedrock. But it's entirely optional — the app is fully functional offline with local models.

**Tech:** Tauri v2 (Rust) + React 19 + FastAPI + SQLite

~80MB installed. Windows, macOS, Linux.

GitHub: https://github.com/contextuai/contextuai-solo

If anyone wants to audit the network behavior, the code is open. Happy to answer questions about the privacy architecture.
