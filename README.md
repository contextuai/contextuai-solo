# ContextuAI Solo

### Your personal AI assistant desktop app — powered by your own API keys

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-brightgreen.svg)]()
[![Tauri](https://img.shields.io/badge/Built%20with-Tauri%20v2-FFC131.svg)](https://tauri.app/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.11+-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57.svg)](https://sqlite.org/)

**ContextuAI Solo** is a free, open-source desktop AI assistant that gives you an entire team of 50+ specialized AI business agents — right on your machine. Bring your own API keys, keep your data local, and get enterprise-grade AI assistance without the enterprise price tag.

---

## What is ContextuAI Solo?

ContextuAI Solo is the community edition of the [ContextuAI](https://contextuai.com) enterprise platform. It's a single-user desktop application that turns your computer into a command center for AI-powered business operations.

### Why Solo?

- **BYOK (Bring Your Own Key)** — Use your existing API keys from Anthropic, OpenAI, Google, AWS Bedrock, or run completely free with Ollama local models
- **50+ Pre-Built Business Agents** — Ready-to-use AI agents across 11 departments: C-Suite, Marketing, Finance, Legal, HR, Design, Data Science, IT, Product, Startup, and Operations
- **Multi-Agent Crews** — Assemble teams of agents that collaborate autonomously on complex tasks
- **Custom Personas** — Create AI personas with tailored system prompts and enterprise connectors
- **Workshop Mode** — Run multi-agent brainstorming sessions with structured outputs and artifact generation
- **External Connections** — Connect to Telegram, Discord, and LinkedIn for automated messaging workflows
- **100% Local** — Your data never leaves your machine. SQLite database + localStorage. No cloud required.
- **Beautiful UI** — Dark/Light theme, brand voice customization, and a polished desktop experience built with Tauri v2

---

## Screenshots

> **Screenshots coming soon.** We're preparing a visual walkthrough of the app. Star this repo to get notified!

---

## Project Structure

```
contextuai-solo/
├── frontend/           # Tauri v2 + React 19 + Vite desktop app
│   ├── src/            # React components, routes, and lib
│   ├── src-tauri/      # Tauri Rust shell configuration
│   └── package.json
├── backend/            # FastAPI server (Python 3.11+, SQLite)
│   ├── app.py          # Application entry point
│   ├── adapters/       # Database, auth, storage, scheduler adapters
│   ├── routers/        # API route handlers
│   ├── services/       # Business logic and AI orchestration
│   └── requirements.txt
├── agent-library/      # Built-in agent templates (50+ agents)
├── run.sh              # One-command backend launcher
├── docker-compose.yml  # Docker-based development setup
└── LICENSE             # Apache 2.0
```

---

## Quick Start

### Prerequisites

- **Node.js 18+** — [Download](https://nodejs.org/)
- **Python 3.11+** — [Download](https://python.org/)
- **Rust** (for Tauri desktop builds only) — [Install](https://rustup.rs/)

### Installation

```bash
# Clone the repo
git clone https://github.com/contextuai/solo.git
cd solo

# Install frontend dependencies
cd frontend && npm install

# Install backend dependencies
cd ../backend && pip install -r requirements.txt
```

### Running the App

**Option A — Use the convenience script:**

```bash
./run.sh
```

This creates a virtual environment, installs dependencies, and starts the backend.

**Option B — Manual start:**

**Terminal 1 — Start the backend:**

```bash
cd backend
CONTEXTUAI_MODE=desktop uvicorn app:app --host 127.0.0.1 --port 18741 --reload
```

**Terminal 2 — Start the frontend:**

```bash
cd frontend
npm run dev
```

Open **http://localhost:1420** and you're ready to go.

**Option C — Docker:**

```bash
docker compose up
```

This starts the backend on port 18741. Run the frontend separately with `cd frontend && npm run dev`.

### Building the Desktop App

To create a native desktop executable:

```bash
cd frontend
npm run tauri build
```

The built app will be in `frontend/src-tauri/target/release/`.

### First Run

1. The app launches a **Setup Wizard** that walks you through API key configuration
2. Choose your preferred AI provider (or use Ollama for free local models)
3. Start chatting, building agents, or assembling crews

---

## Solo vs Enterprise

| Feature | Solo (Free) | Enterprise |
|---------|:-----------:|:----------:|
| AI Chat with Streaming | Yes | Yes |
| 50+ Business Agents | Yes | Yes |
| Custom Personas | Yes | Yes |
| Multi-Agent Crews | Yes | Yes |
| Workshop (Brainstorming) | Yes | Yes |
| BYOK (Bring Your Own Key) | Yes | Yes |
| Ollama Local Models | Yes | Yes |
| Dark/Light Theme | Yes | Yes |
| Telegram/Discord/LinkedIn | Yes | Yes |
| SQLite (Local Storage) | Yes | -- |
| MongoDB + Cloud Infra | -- | Yes |
| Multi-User / Teams | -- | Yes |
| Role-Based Access Control | -- | Yes |
| SSO / MFA / SCIM 2.0 | -- | Yes |
| Analytics Dashboard | -- | Yes |
| Automations & Scheduling | -- | Yes |
| CodeMorph (Code Gen) | -- | Yes |
| Control Center (23 integrations) | -- | Yes |
| Enterprise DB Connectors | -- | Yes |
| Audit Logs & Compliance | -- | Yes |
| Dedicated Support | -- | Yes |

> Interested in enterprise features? Visit [contextuai.com](https://contextuai.com) or email hello@contextuai.com.

---

## Architecture

```
+-------------------+     +-------------------------+     +--------------------+
|                   |     |                         |     |                    |
|   Tauri v2 Shell  |     |   FastAPI Backend       |     |   AI Providers     |
|   (Rust)          |     |   (Python 3.11+)        |     |   (BYOK)           |
|                   |     |                         |     |                    |
|  +-------------+  |     |  +-------------------+  |     |  - Anthropic       |
|  | Vite + React|  | --> |  | SQLite Database   |  | --> |  - OpenAI          |
|  | SPA (1420)  |  | API |  | (via async adapter)|  |     |  - Google Gemini   |
|  +-------------+  |     |  +-------------------+  |     |  - AWS Bedrock     |
|                   |     |  Port 18741             |     |  - Ollama (local)  |
+-------------------+     +-------------------------+     +--------------------+
```

- **Frontend**: React 19 SPA served by Vite dev server (port 1420) or bundled into the Tauri desktop shell
- **Backend**: FastAPI with SQLite via an async adapter layer that mirrors the enterprise Motor/MongoDB interface
- **AI Routing**: BYOK keys configured in the Setup Wizard; the backend routes requests to the selected provider
- **Data**: Everything stored locally in SQLite + localStorage. No telemetry. No cloud calls (except to your chosen AI provider).

---

## Agent Library

Solo ships with **50+ pre-built business agents** across 11 categories:

| Category | Example Agents |
|----------|---------------|
| **C-Suite** | CEO Strategic Advisor, CFO Financial Strategist, COO Operations Optimizer, CTO Technology Advisor |
| **Marketing** | Content Strategist, SEO Specialist, Social Media Manager, Brand Voice Designer, Email Campaign Builder |
| **Finance** | Financial Analyst, Budget Planner, Invoice Processor, Tax Advisor, Revenue Forecaster |
| **Legal** | Contract Reviewer, Compliance Checker, IP Advisor, Privacy Policy Drafter, Terms of Service Generator |
| **HR** | Recruiter Assistant, Job Description Writer, Employee Handbook Drafter, Performance Review Helper |
| **Design** | UI/UX Advisor, Brand Identity Designer, Presentation Builder, Color Palette Generator |
| **Data Science** | Data Analyst, SQL Query Builder, Dashboard Designer, Statistical Modeler, Data Cleaning Assistant |
| **IT** | DevOps Assistant, Security Auditor, Infrastructure Planner, Incident Response Helper |
| **Product** | Product Manager, Feature Prioritizer, User Story Writer, Roadmap Planner, Competitive Analyst |
| **Startup** | Pitch Deck Builder, Business Model Canvas Creator, Investor Brief Writer, Go-to-Market Strategist |
| **Operations** | Process Optimizer, Supply Chain Analyst, Quality Assurance Planner, Vendor Evaluation Assistant |

Each agent comes with a specialized system prompt, recommended model, and relevant tool configurations.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Desktop Shell** | [Tauri v2](https://tauri.app/) (Rust) — lightweight, secure, cross-platform |
| **Frontend** | [React 19](https://react.dev/) + [Vite](https://vitejs.dev/) + [TypeScript 5.9](https://typescriptlang.org/) |
| **Styling** | [Tailwind CSS](https://tailwindcss.com/) + [Framer Motion](https://motion.dev/) |
| **Icons** | [Lucide Icons](https://lucide.dev/) |
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+) |
| **Database** | [SQLite](https://sqlite.org/) via async adapter |
| **AI Providers** | Anthropic Claude, OpenAI GPT, Google Gemini, AWS Bedrock, Ollama |
| **Agent Framework** | [Strands Agents SDK](https://github.com/strands-agents/sdk-python) |

---

## Contributing

We welcome contributions from the community! Whether it's bug fixes, new agents, UI improvements, or documentation — every contribution helps.

Please read our [Contributing Guide](CONTRIBUTING.md) before submitting a pull request.

### Quick Contribution Steps

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`npm run test` for frontend, `pytest` for backend)
5. Commit with clear messages (`git commit -m "feat: add amazing feature"`)
6. Push and open a Pull Request

---

## Community

- **GitHub Issues** — Bug reports and feature requests
- **GitHub Discussions** — Questions, ideas, and general chat
- **Twitter/X** — Follow [@contextuai](https://twitter.com/contextuai) for updates

---

## License

ContextuAI Solo is released under the [Apache License 2.0](LICENSE).

You are free to use, modify, and distribute this software. See the LICENSE file for full details.

---

<p align="center">
  <strong>Built with love by ContextuAI</strong><br>
  Star us on GitHub if you find this useful!
</p>
