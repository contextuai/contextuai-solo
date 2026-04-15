# Reddit — r/artificial

**Target:** AI enthusiasts and researchers

---

**Title:** Built an open-source desktop AI with multi-agent orchestration — 4 execution modes, persistent crew memory, runs on local models

**Body:**

Hey r/artificial,

Built **ContextuAI Solo** — a desktop AI assistant focused on multi-agent orchestration for business tasks.

**The agent system:**

93+ pre-built agents, each with a system prompt tuned for a specific business role. Agents are organized into 13 categories: C-suite strategy, marketing & sales, finance & operations, HR, legal & compliance, product development, research, creative, data analytics, IT security, and more.

**Multi-agent crews — the interesting part:**

You can chain agents into "crews" with 4 execution modes:

1. **Sequential** — Agent A finishes, output goes to Agent B, then Agent C. Linear workflows like research → analysis → report.

2. **Parallel** — All agents work simultaneously on different aspects. Results merged. Good for comprehensive analysis from multiple perspectives.

3. **Pipeline** — Structured stages with defined input/output contracts. Multiple agents per stage. Content creation pipelines, data processing flows.

4. **Autonomous** — Agents self-coordinate using shared crew memory. Orchestrator manages the queue but agents decide what to work on. Open-ended exploration and problem-solving.

**Supporting infrastructure:**
- Workspace orchestrator with polling job queue
- Checkpoint/resume for long-running workflows
- Persistent crew memory across sessions
- Blueprint templates for common workflow patterns

**All local:** 35+ GGUF models on CPU via llama.cpp. The constraint of running on 8B-14B models forces tighter agent design — which arguably produces better results than lazy prompts on GPT-4.

**Tech:** Tauri v2 + React 19 + FastAPI + SQLite

GitHub: https://github.com/contextuai/contextuai-solo

Interested in feedback on the multi-agent architecture — especially from people building similar systems.
