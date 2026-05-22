# ContextuAI Solo — User Guide

Welcome to ContextuAI Solo, your private desktop AI assistant with 96 pre-built business agents. This guide covers every module in the app to help you get started quickly.

## Modules

| # | Module | What it does |
|---|--------|-------------|
| 1 | [Chat](01-chat.md) | Have conversations with AI models, manage sessions, pick agents |
| 2 | [Model Hub](02-model-hub.md) | Configure cloud AI providers and download local models |
| 3 | [Agents](04-agents.md) | Browse 96 business agents, organised by kind (Prompt · Database · Web · MCP · API · File) — Personas were folded in here in v1.0.0-11. The legacy [Personas](03-personas.md) page still works for one release |
| 4 | Automations | Natural-language `@agent`-mention workflows with PDF / PPTX / channel outputs |
| 5 | [Crews](05-crews.md) | Build multi-agent teams that work together on tasks — now includes a Coder-project step |
| 6 | [Blueprints](06-blueprints.md) | Use workflow templates to jumpstart projects |
| 7 | [Workspace](07-workspace.md) | Legacy — workspace projects now live as `kind="project"` rows under [Crews](05-crews.md) |
| 8 | [Distributions](08-connections.md) | Connect to Telegram, Discord, Reddit, LinkedIn, Twitter/X, Instagram, Facebook, Blog, Email, Slack |
| 9 | Knowledge | Upload PDFs / DOCX / TXT / MD or map a folder on disk; chat with citations (local RAG) |
| 10 | [Settings](09-settings.md) | API keys (Distributions-style provider cards), brand voice, appearance, data export |
| 11 | [VS Code / IDE](10-openai-endpoint.md) | Use Solo as the model backend for Continue, Cline, Cursor, Aider, Zed, etc. |
| 12 | [Solo Coder](11-coder.md) | Multi-agent coding environment with per-role models, workflow modes, and live preview |

## Quick Start

1. **Open the app** — No login required. You're the admin.
2. **Add an AI provider** — Go to **Settings > AI Providers** and enter an API key (Anthropic, OpenAI, or Google), or download a free local model.
3. **Start chatting** — Head to **Chat**, pick a model, and send your first message.
4. **Explore agents** — Browse the **Agent Library** to find pre-built specialists for your business needs.
5. **Build a crew** — Combine agents into a **Crew** to tackle complex, multi-step tasks.

## Where is my data stored?

All data stays on your machine. Nothing is sent to ContextuAI servers.

- **Database:** `~/.contextuai-solo/data/contextuai.db` (SQLite)
- **Local models:** `~/.contextuai-solo/models/` (GGUF files)
- **Exports:** Downloaded to your default Downloads folder

## Screenshots

Screenshots referenced in these guides are located in [`docs/screenshots/`](../screenshots/).

| Screenshot | Module |
|-----------|--------|
| ![Chat](../screenshots/001-dashboard-chat.png) | Chat |
| ![Model Hub](../screenshots/002-ModelHub-Selection.png) | Model Hub |
| ![Models Installed](../screenshots/003-ModelsInstalled.png) | Model Hub |
| ![Personas](../screenshots/004-Personas.png) | Personas |
| ![Create Persona](../screenshots/005-CreatePersona.png) | Personas |
| ![Agent Library](../screenshots/006-AgentLibrary.png) | Agents |
| ![Create Agent](../screenshots/007-CreateAgent.png) | Agents |
| ![Crews](../screenshots/008-CrewHome.png) | Crews |
| ![Blueprints](../screenshots/009-Blueprints.png) | Blueprints |
| ![Create Blueprint](../screenshots/010-CreateBlueprint.png) | Blueprints |
| ![Workspace](../screenshots/011-Workspace.png) | Workspace |
| ![Distributions](../screenshots/012-Connections.png) | Distributions |
| ![Crew Approvals](../screenshots/013-CrewApprovals.png) | Crews |
| ![Settings](../screenshots/014-Settings.png) | Settings |
