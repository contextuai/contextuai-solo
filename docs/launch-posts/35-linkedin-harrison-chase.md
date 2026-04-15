# LinkedIn — Harrison Chase / AI Agent Orchestration

**Target:** Comment on Harrison Chase's LinkedIn posts about AI agents, LangChain, or orchestration

---

Built a multi-agent orchestration system that runs entirely on the desktop — no cloud infrastructure required.

ContextuAI Solo ships with 93+ specialized business agents and a crew system that supports 4 execution modes:

- **Sequential** — agents execute in order, each building on the previous output
- **Parallel** — agents work simultaneously on different aspects of a problem
- **Pipeline** — structured input/output flow between agent stages
- **Autonomous** — agents self-coordinate with shared crew memory

Under the hood: workspace orchestrator with a job queue, checkpoint/resume for long-running workflows, and persistent crew memory so agents maintain context across sessions.

The interesting constraint: everything runs on local GGUF models via llama.cpp on CPU. Orchestrating agents on 8B parameter models forces you to write better system prompts and design tighter workflows.

Open source: https://github.com/contextuai/contextuai-solo
