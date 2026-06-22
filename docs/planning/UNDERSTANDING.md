# System Understanding — ContextuAI

> Snapshot of the full review done 2026-06-11/12. Verify file:line references before relying on them — code moves.

## 1. The three repos

| Repo | What it is | Stack |
|------|-----------|-------|
| `contextuai-solo` | Open-source single-user desktop AI assistant (the product this docset is about) | Tauri v2 (Rust) + React 19 + FastAPI sidecar + SQLite |
| `contextuai-marketing-site` | Marketing website (contextuai.* on Firebase Hosting) | Vite + Handlebars partials + Tailwind, Firebase Hosting/Firestore/Functions (py312) |
| `Contextuai_enterprise` | Multi-user SaaS edition (separate codebase) | Not deeply reviewed. Self-hosted containers, platform JWT auth, MongoDB (per project memory). |

Positioning: Solo is free forever (Apache 2.0), Enterprise is custom-priced. Solo's differentiators: 96 prebuilt business agents, local GGUF models, folder-mapped local RAG, 10 distribution channels, multi-agent crews, human-in-the-loop approvals, Coder mode, OpenAI-compatible local API.

## 2. Solo desktop architecture

```
Tauri Shell (Rust)  →  React SPA (dev port 1420)  →  FastAPI Sidecar (127.0.0.1:18741)
```

- **Tauri shell** `frontend/src-tauri/src/`: `main.rs` boots, `sidecar.rs` spawns + health-checks the backend (PyInstaller exe in `src-tauri/sidecar/`), `commands.rs` has IPC handlers (`api_request`, `get_sidecar_port`).
- **Frontend** `frontend/src/`: routes in `routes/`, API clients in `lib/api/`, transport in `lib/transport.ts`.
- **Backend** `backend/`: `app.py` entry; `routers/` → `services/` → `repositories/` → `adapters/`.

### Transport (important for any frontend work)
- Regular requests: **Tauri IPC** (`api_request` command) in production; direct `fetch` to `http://127.0.0.1:18741/api/v1` in dev (`lib/transport.ts:38-80`).
- **Streaming is always raw `fetch` + SSE over HTTP**, even in Tauri (`streamRequest()`, and `downloadModel()` in `lib/api/local-models-client.ts`). This works because backend CORS is currently `allow_origins=["*"]` (`app.py:71-76`) — SPEC-01 changes this; any CORS lockdown must keep the Tauri webview origin working (`http://tauri.localhost` on Windows, `tauri://localhost` on macOS) or streaming breaks.
- Retry: 5 attempts, exponential backoff; cold-start 404s on writes are retried until first success (`transport.ts:100-131`).
- Backend returns camelCase, frontend types are snake_case — bridged by `normalizeMessage()` in `lib/api/chat-client.ts`.

### Database
SQLite at `~/.contextuai-solo/data/contextuai.db` behind a **Motor (MongoDB) compatibility layer**: `adapters/sqlite_adapter.py` (aiosqlite) + `adapters/motor_compat.py` (DatabaseProxy/CollectionProxy). Tables are `_id TEXT PRIMARY KEY, data JSON`; Mongo operators (`$set`, `$in`, `$regex`…) are translated to SQL/JSON. **`update_one` is read-modify-write, not atomic** (see REL-2). Backend was ported from MongoDB; enterprise still runs real Mongo.

### Auth model
Desktop mode = static admin user, **no auth at all**; dependency overrides in `app.py`. `auth_service.py` retains Cognito JWT for enterprise. The sidecar port is reachable by any local process (see SEC-1).

### Local models (Model Hub)
- Catalog: `services/model_catalog.py` — 41 curated GGUF entries (id, hf_repo, hf_filename, RAM tiers, chat_template).
- Download: `services/model_manager.py` — **as of branch `fix/model-hub-downloads`** uses plain ranged-HTTPS GET (requests) from `huggingface.co/<repo>/resolve/main/<file>` with `.part` resume, per-1MB-chunk cancel checks, disk-space preflight, `HF_TOKEN` env support, friendly error mapping. It deliberately does NOT use `hf_hub_download` (Xet protocol broke on locked-down networks). Router: `routers/local_models.py` (SSE progress; on `done` it syncs the file into the `models` collection via `services/local_model_seeder.py`).
- Inference: `services/local_model_service.py`, llama-cpp-python, CPU; one model in memory, `asyncio.Lock` serializes access; models dir `~/.contextuai-solo/models/` (+ legacy `chat/` subdir).
- Dispatch: `services/model_dispatcher.py` routes `anthropic:` / `openai:` / `google:` / `bedrock:` / `ollama:` / bare local IDs. Cloud keys in `cloud_provider_keys` collection (plaintext today — SEC-2); `services/cloud_model_seeder.py` registers models on key-save.
- OpenAI-compat surface: `routers/openai_compat.py` mounts `/v1/models` + `/v1/chat/completions` at the backend root for Aider/Continue/Cursor.

### Agents / Crews / Automations
- `agent-library/` markdown agents seeded into `workspace_agents` with a `kind` field (`prompt|database|web|mcp|api|file|coder`). Solo shows 96; `engineering` + `coder-companion` are excluded (coder agents appear only in Coder mode).
- Crews: 7-step wizard (`components/crews/crew-builder.tsx`); `connection_bindings[]` with direction, `triggers[]` (reactive + scheduled), `approval_required`. Crew rows carry `kind: "crew"|"project"`. Runs orchestrated by `services/workspace/orchestrator.py` (job queue poll) + `agent_runner.py`.
- Automations: NL `@agent` mentions (`services/automation_parser.py` / `automation_engine.py`), output actions chat/PDF/PPTX/MD/any distribution adapter, "Promote to Crew".
- Blueprints: 10 markdown workflow templates seeded into `blueprints`.

### Knowledge Base / RAG
- Upload path: chunk (~500 tokens / 50 overlap) → embed with bundled all-MiniLM-L6-v2 ONNX (384-dim, unit-norm) → JSON arrays in SQLite (`kb_documents`, `kb_chunks`). Retrieval = numpy dot product.
- Folder mappings (`routers/personal_docs.py`, `services/personal_docs_service.py`, `folder_walker.py`): user picks a folder via Tauri dialog; walker classifies new/updated/removed by `(abs_path, size, mtime)`; jobs in `kb_index_jobs` with SSE progress; schedules manual/1h/6h/24h via `personal_docs_scheduler.py`; friction threshold 1,000 files, caps 10MB/file, 5,000 files, depth 10.
- Chat integration: `knowledge_base_id` on chat request; citations prepended to prompt.

### Connections / Distributions
10 platforms under `/connections` (sidebar label "Distributions"): Telegram, Discord, Reddit (praw poller, 60s loop), LinkedIn, Twitter/X, Instagram, Facebook, Blog, Email, Slack webhook. Token-paste, OAuth2, or API-key flows. Outbound can be gated by the Approvals queue.

### Coder mode
Top-center pill toggles `solo|coder` (Ctrl+Shift+M; `contexts/mode-context.tsx`). Own sidebar (Projects, Running, Templates, Models, Settings). Projects scaffold from 4 templates; **trust state is a per-project boolean** gating allowlisted shell exec (`services/coder_run_service.py` — shlex.split + create_subprocess_exec, no shell). Runs stream stdout over SSE; `run_headless()` is the crew/automation handoff. 5 coder-companion agents.

### Build & packaging (Windows)
`build.ps1`: (1) PyInstaller via `backend/contextuai-solo-backend.spec` → `frontend/src-tauri/sidecar/` (COLLECT flattened; bundles `agent-library/` + `blueprints/` as data; collects huggingface_hub/tqdm/psutil submodules; llama_cpp + onnxruntime dynamic libs), (2) `npm run tauri build` → MSI + NSIS. **Implication: source installs get floating dep versions** — venv currently has `huggingface_hub 1.8.0`, `requests 2.32.3` (pinned), `huggingface-hub>=0.20.0` (unpinned).

### Testing
- Backend: pytest in `backend/tests/` (~1,000 tests; `-k "model or catalog or download"` ≈ 82).
- Frontend: Playwright E2E in `frontend/tests/e2e/` (Chromium, single worker, needs dev server + backend).

### Conventions (enforced)
- Never commit to `main` (protected). Topic branches `feat/|fix/|docs/|chore/` + PR. Conventional Commits.
- TS strict, no `any`; Python typed, Pydantic v2, all I/O async.
- Port 18741 everywhere (sidecar.rs / transport.ts / settings.py must stay aligned).

## 3. Marketing site

Static Vite + Handlebars partials (`partials/`), pages: index, solo, features, crews, enterprise, docs, cookbook (orphaned — not in navbar). Firebase Hosting via `firebase.json` (good cache headers; references `firestore.rules` and a py312 `functions/` — existence needs verifying). No secrets in client code. Three placeholder blog cards (`href="#"`), several placeholder footer links, no sitemap.xml/404. Biggest content gap: the product's differentiators (Reddit integration, folder-mapped KB auto-sync, OpenAI-compat API, coder-companion agents, Brand Voice) are built but unmarketed.

## 4. Known environmental facts

- Dev machine: Windows 11, PowerShell 5.1.
- HuggingFace: now rate-limits anonymous downloads (429s observed in warnings); `google/gemma-3-*-qat-q4_0-gguf` repos are gated (`gated: manual`) — catalog was switched to `bartowski/google_gemma-3-*-it-GGUF` Q4_0 mirrors on `fix/model-hub-downloads`.
- The user-facing failure history that motivated the download rewrite is recorded in GAPS.md REL-0.
