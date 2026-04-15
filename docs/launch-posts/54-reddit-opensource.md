# Reddit — r/opensource

**Target:** Open-source community

---

**Title:** Open-sourced my desktop AI assistant — 93+ business agents, 35+ local models, built by one developer with Claude Code

**Body:**

Just open-sourced **ContextuAI Solo** — a desktop AI assistant built for business professionals who want AI agents without cloud dependency.

**The problem:** Every AI tool requires sending your business data to someone else's servers. For consultants, freelancers, and privacy-conscious professionals, that's a dealbreaker.

**The solution:** A native desktop app with 35+ local AI models running on CPU. No GPU needed, no API keys required to start.

**Features:**
- 93+ pre-built business agents across 13 categories
- Custom agent builder
- Multi-agent crews (sequential, parallel, pipeline, autonomous)
- 35+ GGUF models — DeepSeek R1, Qwen 3.5, Llama 3.1, Phi-4, Mistral, Gemma 3
- 10 workflow blueprint templates
- Platform connections (Telegram, Discord, LinkedIn, Twitter/X, Instagram, Facebook)
- Windows, macOS, Linux installers

**Tech stack (all open source):**
- Tauri v2 (Rust) — MIT
- React 19 — MIT
- FastAPI — MIT
- SQLite — public domain
- llama-cpp-python — MIT

**How I built it:** Solo developer using Anthropic's Claude Code. The entire app — Rust, TypeScript, Python — was built with AI-assisted development. One of the more complex things Claude Code handled was a MongoDB-to-SQLite compatibility layer that translates Motor API calls and query operators to SQL/JSON.

**Contributing:** Agents are markdown files — easy to add or improve without coding. Model suggestions, platform testing, and localization all welcome. Good first issues are labeled.

GitHub: https://github.com/contextuai/contextuai-solo

License: [check repo]
