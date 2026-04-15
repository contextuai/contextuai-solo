# LinkedIn — Jim Fan / Multi-Agent Systems

**Target:** Comment on Jim Fan's LinkedIn posts about AI agents, embodied AI, or agent architectures

---

Multi-agent systems don't have to live in the cloud.

Built a desktop-native multi-agent platform with 4 execution modes:

**Sequential:** Agents execute in order. Agent A's output becomes Agent B's input. Good for linear workflows like research → analysis → report.

**Parallel:** Multiple agents work simultaneously on different facets of a problem. Results aggregated at the end. Good for comprehensive analysis.

**Pipeline:** Structured input/output contracts between stages. Each stage can have multiple agents. Good for content pipelines.

**Autonomous:** Agents self-coordinate using shared crew memory. The orchestrator manages the job queue but agents decide task allocation. Good for open-ended exploration.

Supporting infrastructure: workspace orchestrator with polling job queue, checkpoint/resume for long-running workflows, persistent crew memory across sessions.

All of this runs on a laptop with 8B-14B GGUF models on CPU. The constraint of small local models forced better agent design — clear system prompts, focused responsibilities, tight scope.

93+ pre-built agents across 13 business categories. Open source.

GitHub: https://github.com/contextuai/contextuai-solo
