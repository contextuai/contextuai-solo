# LinkedIn — Amanda Askell / Claude Capabilities

**Target:** Comment on Amanda Askell's LinkedIn posts about Claude, AI capabilities, or AI development

---

Here's what Claude Code looks like as an engineering partner on a real project:

**The project:** ContextuAI Solo — a desktop AI assistant with 93+ business agents, 35+ local models, multi-agent crews. Tauri v2 (Rust) + React 19 + FastAPI + SQLite.

**What Claude Code did well:**
- Cross-language architecture decisions (Rust, TypeScript, Python in one project)
- Writing a MongoDB-to-SQLite compatibility layer that translates query operators to SQL/JSON
- Debugging platform-specific issues (Windows process tree cleanup, macOS code signing quirks)
- Designing the sidecar pattern for bundling Python inside a Rust desktop app
- Maintaining consistency across a growing codebase over months of development

**What surprised me:**
- Claude Code remembers architectural decisions from earlier in the conversation and applies them consistently
- It catches edge cases in error handling that I would have shipped without
- The quality of its Rust code (sidecar lifecycle management) was production-ready

This felt less like "AI-assisted coding" and more like pair programming with a senior engineer who happens to know every language.

Open source: https://github.com/contextuai/contextuai-solo
