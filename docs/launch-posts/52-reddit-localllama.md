# Reddit — r/LocalLLaMA

**Target:** Local model enthusiasts

---

**Title:** Built a desktop app that makes local GGUF models accessible to non-technical business users — 35+ models, 93+ agents, one-click everything

**Body:**

Hey r/LocalLLaMA,

I've been lurking here for months and your community directly influenced this project. **ContextuAI Solo** is a desktop AI assistant with a built-in Model Hub of 35+ GGUF models.

**Model Hub highlights:**
- DeepSeek R1: 7B, 8B, 14B, 32B, 70B
- Qwen 3.5: 1.5B, 4B, 9B, 14B, 27B
- Llama 3.1 8B
- Phi-4 14B
- Mistral Small 22B
- Gemma 3: 1B, 4B, 12B
- ...and more

All running via llama-cpp-python on CPU. No GPU required. One-click download from HuggingFace.

**What makes this different from other UIs:**

1. **93+ pre-built business agents** — not just a chat wrapper. Each agent has a tuned system prompt for a specific business role (CFO analyst, content strategist, legal reviewer, etc.)

2. **Multi-agent crews** — chain agents together in sequential, parallel, pipeline, or autonomous execution modes. Run a strategy analysis → market research → report generation pipeline locally.

3. **Custom GGUF support** — drop any .gguf file into `~/.contextuai-solo/models/` and it auto-registers after a sync.

4. **No Python env required for users** — the backend is bundled via PyInstaller. Users download an installer and it just works.

**Hardware recommendations from my testing:**
- 8GB RAM: stick to 1B-4B models (Gemma 3 1B, Qwen 3.5 1.5B)
- 16GB RAM: comfortable with 8B-14B (DeepSeek R1 14B, Phi-4 14B, Qwen 3.5 9B)
- 32GB RAM: can run 22B-32B (Mistral Small 22B, DeepSeek R1 32B)
- 64GB RAM: go wild with 70B

**Tech stack:** Tauri v2 (Rust) + React 19 + FastAPI + SQLite + llama-cpp-python

**Known limitation:** CPU-only inference. GPU support (CUDA, Metal) is on the roadmap but not there yet.

GitHub: https://github.com/contextuai/contextuai-solo

What models would you add to the hub? What quantization levels do you prefer for business tasks?
