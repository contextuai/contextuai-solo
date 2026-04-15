# LinkedIn — Shawn Wang (swyx) / AI Engineering

**Target:** Comment on swyx's LinkedIn posts about AI engineering, agents, or the AI ecosystem

---

The AI agent ecosystem is converging on cloud-hosted solutions. I went the opposite direction.

ContextuAI Solo is a desktop-native AI agent platform:

**Agent layer:** 93+ specialized business agents defined as markdown files with system prompts, organized by 13 business categories. Auto-seeded on first launch. Custom agent builder for user-defined agents.

**Orchestration layer:** Multi-agent crews with 4 execution modes — sequential, parallel, pipeline, autonomous. Job queue, checkpoint/resume, persistent crew memory across sessions.

**Inference layer:** 35+ GGUF models via llama-cpp-python on CPU. Model Hub with one-click HuggingFace download. Async lock to prevent concurrent model access. Also supports Anthropic Claude and AWS Bedrock.

**Transport layer:** SSE streaming over HTTP with AbortSignal for mid-stream cancellation. Retry with exponential backoff. Tauri IPC in desktop mode, direct HTTP in dev mode.

The whole thing runs offline on a regular laptop. No API keys needed to start.

Open source: https://github.com/contextuai/contextuai-solo
