# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ContextuAI Solo is a single-user desktop AI assistant with 96 pre-built business agents (108 in repo, engineering category excluded from desktop). It's a Tauri v2 desktop app with a React 19 frontend and a FastAPI Python backend running as a sidecar process. Data is stored locally in SQLite. Supports both cloud AI providers (Anthropic, AWS Bedrock) and local GGUF models via llama-cpp-python.

## Commands

### Frontend (run from `frontend/`)
```bash
npm install                  # Install dependencies
npm run dev                  # Vite dev server on port 1420
npm run build                # TypeScript check + Vite production build
npm run tauri dev            # Run full Tauri desktop app (dev mode)
npm run tauri build          # Build platform installers (.exe/.msi)
npx playwright test          # Run E2E tests (requires dev server running)
npx playwright test tests/e2e/some-test.spec.ts  # Run a single test
```

### Backend (run from `backend/`)
```bash
pip install -r requirements.txt   # Install dependencies
CONTEXTUAI_MODE=desktop uvicorn app:app --host 127.0.0.1 --port 18741 --reload  # Dev server
pytest tests/ -v                  # Run backend tests
```

### Quick Start
```bash
./run.sh                     # Creates venv, installs deps, starts backend
# Then in another terminal: cd frontend && npm run dev
```

### Docker
```bash
docker compose up            # Starts backend only; run frontend separately
```

## Architecture

### Three-Layer Desktop App
```
Tauri Shell (Rust)  →  React SPA (port 1420)  →  FastAPI Sidecar (port 18741)
```

- **Tauri shell** (`frontend/src-tauri/src/`): Window management, system tray, sidecar process lifecycle. `main.rs` boots the app, `sidecar.rs` spawns/health-checks the backend, `commands.rs` provides IPC handlers.
- **React frontend** (`frontend/src/`): Routes in `routes/`, reusable UI in `components/ui/`, API clients in `lib/api/`, transport layer in `lib/transport.ts`.
- **FastAPI backend** (`backend/`): Entry point is `app.py`. Routers in `routers/`, business logic in `services/`, data access in `repositories/`, adapters in `adapters/`.

### Frontend-Backend Communication
- **Tauri mode**: React → Tauri IPC (`api_request` command) → HTTP to sidecar
- **Dev mode**: React → direct HTTP fetch to `http://127.0.0.1:18741/api/v1`
- **Streaming**: Always SSE over HTTP (not IPC), consumed via `streamRequest()` in `transport.ts`. Supports `AbortSignal` for cancelling mid-stream.
- Retry logic: 5 attempts with exponential backoff
- **Stream abort**: Frontend uses `AbortController` to cancel HTTP fetch on stop. Backend `LocalModelService` has `asyncio.Lock` to prevent concurrent model access — second request waits for first to finish/abort.

### Database: SQLite with MongoDB-Compatible API
The backend was ported from MongoDB. A compatibility layer preserves the Motor API:
- `adapters/sqlite_adapter.py` — Async SQLite wrapper (aiosqlite)
- `adapters/motor_compat.py` — `DatabaseProxy`/`CollectionProxy` that mimic Motor's `AsyncIOMotorDatabase`/`AsyncIOMotorCollection`
- Tables use `_id TEXT PRIMARY KEY, data JSON NOT NULL` pattern — documents stored as JSON blobs
- MongoDB query operators (`$set`, `$in`, `$regex`, `$gt`, etc.) are translated to SQL/JSON expressions
- DB path: `~/.contextuai-solo/data/contextuai.db`

### Backend Patterns
- **Repository pattern**: `repositories/*.py` — Generic async CRUD via `BaseRepository<T>`
- **Service layer**: `services/*.py` — Business logic injected with repositories via FastAPI `Depends()`
- **Workspace orchestration**: `services/workspace/orchestrator.py` polls job queue, `agent_runner.py` executes individual agents, `checkpoint_service.py` handles pause/resume
- **Crew system**: Multi-agent teams with persistent memory (`crew_memory_service.py`)

### Local AI Models (`backend/routers/local_models.py`)
GGUF models downloaded from HuggingFace, stored in `~/.contextuai-solo/models/`. Inference via llama-cpp-python on CPU.
- 41 curated GGUF models (Gemma 4, Qwen 3/3.5, DeepSeek R1, Llama 3, Mistral, Phi-4, etc.) from 0.5B to 70B
- Download: `POST /api/v1/local-models/{model_id}/download` (SSE progress)
- Sync to DB: `POST /api/v1/local-models/sync` (registers downloaded models in the `models` collection)
- Models appear in chat dropdown after sync

### Agent Library (`agent-library/`)
108 business agents as markdown files across 13 categories (c-suite, marketing-sales, finance-operations, etc.). Engineering category (12 agents) is excluded from desktop mode, so users see 96 across 12 categories. Each markdown file contains a system prompt, recommended model, and tool configs. Auto-seeded into `workspace_agents` collection on first startup. Re-seed via `POST /api/v1/desktop/reseed`.

### Crew System
Multi-agent teams with persistent memory. Crew builder (`components/crews/crew-builder.tsx`) is a 7-step wizard:
1. **Details** — name, description, blueprint, AI model selection
2. **Execution Mode** — sequential, parallel, pipeline, autonomous
3. **Agent Team** — add agents from the 96-agent library or manually (skipped for autonomous)
4. **Connections & Directions** — bind crew to channels with per-connection direction chip (`Inbound` / `Outbound` / `Both`)
5. **Trigger** — reactive (keywords/hashtags/mentions) and/or scheduled (cron or one-shot date); manual is always implicit
6. **Approval** — toggle `approval_required` to hold outbound in the Approvals queue before sending
7. **Review & Create** — configuration summary before create

Connection bindings stored as `connection_bindings[]` on the crew document (`ConnectionBinding` model: `connection_id`, `platform`, `direction`). `triggers[]` holds reactive and scheduled trigger configs. Crew-level model selection applies to all agents in the crew.

### Blueprint Library (`blueprints/`)
10 pre-built workflow templates across 5 categories (strategy, content, marketing, product, research). Markdown files auto-seeded into `blueprints` collection on startup. Integrated into crew builder and workspace project dialog via `BlueprintSelector` component. API: `GET /api/v1/blueprints/`, `GET /api/v1/blueprints/{id}`.

### Knowledge Base / RAG (`routers/knowledge_base.py`, `services/rag_service.py`)
Local-only retrieval-augmented generation. Users create knowledge bases at `/knowledge`, upload PDFs / DOCX / TXT / MD, and the documents are chunked (~500 tokens, 50 overlap, page-tracked for PDFs), embedded with the bundled all-MiniLM-L6-v2 ONNX model (384-dim, unit-normalised), and persisted as JSON arrays in SQLite (`kb_documents` + `kb_chunks` collections). Retrieval is numpy dot-product (= cosine for unit vectors); top-k MMR not yet implemented. The chat input has a "Knowledge" dropdown — when a KB is selected, `ai_chat.py` runs a query, prepends the formatted citations to the prompt for both local and Bedrock paths, and instructs the model to cite `[1]`, `[2]`, etc. REST API: `GET/POST /api/v1/knowledge-bases`, `GET/PUT/DELETE /api/v1/knowledge-bases/{id}`, `GET/POST /api/v1/knowledge-bases/{id}/documents` (multipart upload), `DELETE /api/v1/knowledge-bases/{id}/documents/{doc_id}`, `POST /api/v1/knowledge-bases/{id}/query`. Chat request body accepts `knowledge_base_id` (optional). Pre-built RAG packs live under `knowledge-base-packs/` for users to download (e.g. IRS tax docs, personal finance, cybersecurity); each pack is a folder of source files plus a `manifest.json`.

### Personal Docs / Folder Mappings (`routers/personal_docs.py`, `services/personal_docs_service.py`)
A KB can also have folder sources: pick any folder via the Tauri dialog plugin (`tauri-plugin-dialog`, exposed through `lib/tauri-fs.ts`), the backend walks it (depth + glob filtered; supported extensions `.pdf .docx .txt .md .html .htm .rtf .csv .json`), classifies new / updated / removed files vs. existing docs by `(abs_path, size, mtime)`, and re-uses the same chunk → embed → query pipeline. Backed by two new collections: `kb_folder_sources` (one row per mapping) and `kb_index_jobs` (one row per sync run with progress + error fields). Manual "Sync now" plus a per-mapping schedule (`manual` / `1h` / `6h` / `24h`) honoured by `services/personal_docs_scheduler.py`. Walks above the friction threshold (default 1,000 files) pause the job in `awaiting_confirmation` so the UI can show ETA and require explicit confirm before any embeddings are computed. Hard caps: 10 MB / file, 5,000 files / mapping, depth 10 — overridable per mapping or via env (`PERSONAL_DOCS_MAX_*`). Crews and workspace agents bind to KBs via `knowledge_base_ids: string[]` (per-agent overrides crew default); `services/workspace/agent_runner.py` queries those KBs each turn and prepends a citation block to the system prompt. UI lives at `/knowledge/<kb_id>` under a new "Folders" tab next to "Documents" + "Test Query"; SSE stream at `/api/v1/personal-docs/jobs/{job_id}/stream` drives the live progress panel.

### Reddit Connection (`routers/reddit.py`, `services/reddit_poller.py`)
Inbound polling via praw (Reddit API wrapper). `RedditPoller` runs a 60s background loop, fetching new comments from configured subreddits (filtered by keywords) and inbox DMs. Dispatches through `channel_service.handle_message()` so triggers + approval pipeline apply. Account config stored in `reddit_accounts` collection. REST API: `GET/POST/PUT/DELETE /api/v1/reddit/account`, `POST /api/v1/reddit/test`, `POST /api/v1/reddit/reply`.

### Connections / Distributions (`routes/connections.tsx`)
10 platform integrations displayed under the sidebar label **Distributions** (URL remains `/connections`). Seven social platforms: Telegram, Discord, Reddit (inbound + outbound), LinkedIn, Twitter/X, Instagram, Facebook (outbound-only). Three outbound-only channels: Blog (Ghost/WordPress/custom), Email (SendGrid/SES/SMTP), Slack Webhook. Token-paste flow for Telegram/Discord/Twitter/Reddit; OAuth2 flow for LinkedIn/Instagram/Facebook; API-key/webhook-URL for Blog/Email/Slack.

### Authentication
Desktop mode uses a static admin user — no login required. Auth is bypassed via dependency overrides in `app.py`. The `auth_service.py` has Cognito JWT support for the enterprise edition.

### Persona Types
Desktop mode seeds 10 persona types: Nexus Agent, Web Researcher, PostgreSQL, MySQL, MSSQL, Snowflake, MongoDB, MCP Server, API Connector, File Operations. Social platforms (Slack, Twitter/X) are NOT persona types — they belong in Distributions (the page formerly labelled Connections; URL and code identifiers still use `connections`). Persona creation uses a 2-step wizard: Step 1 = type selection card grid with search, Step 2 = configure details (name, credentials, system prompt).

### Key Configuration
- `backend/settings.py` — Centralized env-var config with defaults (port 18741)
- `frontend/src-tauri/tauri.conf.json` — Tauri app config, sidecar path, window settings
- `frontend/vite.config.ts` — Path alias `@/` → `./src/`, dev port 1420

### Port Convention
Backend sidecar runs on **port 18741** (not 8000). This avoids conflicts with Docker stacks, common dev tools, and other desktop apps. All references are aligned: `sidecar.rs`, `transport.ts`, `settings.py`.

### camelCase / snake_case Mismatch
Backend API returns camelCase (`messageType`, `messageId`, `sessionId`) but frontend types use snake_case (`message_type`, `message_id`, `session_id`). The `normalizeMessage()` function in `lib/api/chat-client.ts` bridges this gap when loading messages from the API.

## Code Conventions

- **Branching**: NEVER commit directly to `main`. `main` is branch-protected — direct commits will be rejected/reverted. Always create a topic branch first (`feat/<x>`, `fix/<x>`, `docs/<x>`, `chore/<x>`) and open a PR. Applies to docs-only changes too. Releases go through the `/prod-release` and `/release` skills, which handle branch hygiene correctly.
- **Commits**: Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
- **TypeScript**: Strict mode, no untyped `any`. Functional components with hooks. `@/*` import alias. `cn()` utility for conditional Tailwind classes.
- **Python**: Type hints on all signatures. Pydantic v2 for models. All I/O must be async. PEP 8 naming.
- **Tailwind**: Dark mode via `class` strategy. Custom color tokens: `primary` (orange), `secondary` (sky blue), `dark` (zinc).

## Testing
- **E2E (Playwright)**: Tests in `frontend/tests/e2e/`. Chromium only, single worker. Global setup seeds localStorage with wizard completion flag. Requires both frontend dev server and backend running.
- **Backend (pytest)**: Standard pytest in `backend/tests/`.
