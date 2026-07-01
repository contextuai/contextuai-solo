# TODO — ContextuAI Solo Moonshot

> Master task list. Prioritized by phases. Check off as completed.
> **Created:** 2026-03-19 | **Last synced with code:** 2026-06-30

---

## CURRENTLY PENDING (audit 2026-05-17)

Phases 0–4 and Phase 5 (Coder multi-agent) are shipped and verified against the codebase. v1.0.0-11 cut on 2026-05-15 carried the Phase 5 Coder multi-agent stack (workflow execution engine, Team panel, project-creation ModelPicker, AI Providers onboarding cards). The only meaningful work left:

- **P0-1 verification** — test the OpenAI-compat endpoint with Aider + Continue.dev externally (router shipped, dispatcher now also handles all cloud providers via `services/model_dispatcher.py`).
- **3 starter RAG packs** — engine is shipped (P2.5-2/3). `knowledge-base-packs/README.md` documents the manifest format. Still need curated content packs (IRS tax, personal finance, cybersecurity-101) for users to download.
- **CI: bundle the all-MiniLM-L6-v2 ONNX weights** so the KB lifecycle + Personal Docs folder e2e tests can run on GitHub Actions (currently `test.skip(!!process.env.CI)`).
- **Phase 3/4 dead-code cleanup** — `frontend/src/routes/distribution.tsx`, `frontend/src/routes/schedule.tsx`, `frontend/src/routes/personas.tsx` (banner-only, one-release deprecation), `frontend/src/routes/workspace.tsx`. Delete after one more release cycle past v1.0.0-11.
- **Backlog (BL-4 / BL-5 / BL-6 / BL-7)** — BL-2 (coding agents) absorbed into Phase 4 PR 6 coder-companion category. The rest are nice-to-haves, none committed.

---

## CLOUD PROVIDERS & RELEASE (in flight — 2026-06-30)

Tracked after the v1.0.0-16 release (crew run-flow fixes + Ollama provider).

### CR-1: Fix `Create Tag` 404 handling in release workflow ⭐
`.github/workflows/release.yml` "Create Tag" step mis-handles a 404: `existing_sha=$(gh api .../git/ref/tags/$TAG --jq '.object.sha' 2>/dev/null || echo "")` captures the 404 body into `existing_sha` (the `|| echo ""` is *inside* the `$()`), so a non-existent tag is read as "already exists at a different SHA" and the job hard-fails.
- [ ] Move the fallback outside the substitution: `existing_sha=$(gh api … 2>/dev/null) || existing_sha=""`.
- Symptom: the auto-triggered release on `main` fired correctly but died at Create Tag; v1.0.0-16 had to be published via a manual `git push origin v1.0.0-16` (tag-push path skips this job). Until fixed, every normal release needs that manual recovery.

### CR-2: Cloud endpoint review (verify each provider end-to-end)
Test connection → save/persist → chat → crew, per provider:
- [x] **Ollama** — Test/Save (`/api/tags` probe), chat, crew routing. Done in v1.0.0-16.
- [x] **OpenAI** — Test/Save, **live model discovery** (filtered from `/v1/models`, no rot), chat + crew via dispatcher, classic (gpt-4o) + reasoning (gpt-5.x/o-series) models, adaptive param retry, clear errors, **cost shown**. Done in PR #57.
- [x] **Anthropic** — dummy `sk-ant-…` placeholder deleted; routes via Claude SDK (crews) / dispatcher (chat). Real-key test + live discovery still TODO.
- [ ] **Google (Gemini)** — Test/Save, chat, crew + live discovery.
- [ ] **AWS Bedrock** — Test/Save (boto3 list-foundation-models), chat, crew.

Also shipped in PR #57 (surfaced during the review):
- Cloud routing **unified on `model_dispatcher`** across Chat + Crews + `/v1` (OpenAI/Anthropic/Google/openai_compat were dead in Chat/Crews before — only local/ollama/bedrock worked).
- Models **seed on Save** (gated on credential, not the never-set `connected` flag); removed on delete.
- **Run cost** shown in the crew Run Progress panel + fixed field mismatches (agents→steps, total_cost_usd→cost_usd, duration_ms→duration_seconds, progress). Pricing table rots + can't cover new families (gpt-5.x → $0 until priced).
- **Approvals** post before marking approved (no false "approved" on a failed publish); 502 + provider message on failure.

### CR-3: Generic `openai_compat` provider (#48 — closes #45) — ✅ DONE (PR #57)
One integration for **any** OpenAI-compatible server (vLLM / LM Studio / llama.cpp / TGI / Ollama `/v1` / Azure OpenAI / LiteLLM / OpenRouter).
- [x] `OPENAI_COMPAT` provider type (base_url required, key optional).
- [x] Parameterized endpoint + optional key in `openai_direct_service`.
- [x] `_probe_openai(base_url, require_key)` + `openai_compat` test branch.
- [x] `model_dispatcher` prefix + routing; also wired into Chat + Crews + `/v1`.
- [x] Dynamic model discovery via the server's `/v1/models` (preserve-on-failure).
- [x] Frontend provider guide + Settings card.
- [x] Adaptive param retry → works even when a compat endpoint fronts gpt-5/o-series.

### CR-4: LinkedIn company-page (organization) posting — follow-up
Personal posting works end-to-end (verified: crew → approval → `/v2/ugcPosts` 201).
Company-page posting is blocked by **LinkedIn app permissions**, not our code:
- [ ] Company posting needs the **Community Management API** product (`w_organization_social`), which LinkedIn requires to be the **only** product on a dedicated app → **create a separate LinkedIn app** for it (current app has OpenID + Share products; Request-access is greyed out). Requires a **Privacy Policy URL** on the app + LinkedIn approval + the member being an **admin** of the org.
- [ ] Then: point the LinkedIn connection at the new app's `client_id`/`client_secret`, add `w_organization_social` to requested scopes, set `author_urn = urn:li:organization:<id>`.
- ContextuAI side is mostly config (per-connection creds + scope list already stored) — no architectural change.
- Interim: channel `author_urn` set to `urn:li:person:<id>` (posts as the member).

---

## PHASE 0: FOUNDATION (Do First — Unblocks Everything)

### P0-1: OpenAI-Compatible API Endpoint ⭐ HIGH PRIORITY
**Status:** [x] COMPLETE (2026-03-20)
**Effort:** 2 days → done in 1 session

**What was built:**
- [x] New router: `backend/routers/openai_compat.py`
- [x] `GET /v1/models` — lists installed GGUF models in OpenAI format
- [x] `POST /v1/chat/completions` — accepts OpenAI-format requests, routes to llama-cpp-python
- [x] Streaming support via SSE (`data: {...}\n\n` + `data: [DONE]`)
- [x] Non-streaming support (full OpenAI-format response with usage stats)
- [x] Fuzzy model resolution (id, normalized, substring match)
- [x] Registered router in `app.py`
- [x] Tested with curl: non-streaming ✓, streaming ✓, /v1/models ✓
- [ ] Test with Aider: `aider --openai-api-base http://localhost:18741/v1 --model qwen2.5-1.5b`
- [ ] Test with Continue.dev (VS Code extension)

**Key insight:** llama-cpp-python returns OpenAI-format natively, so the router is thin — resolve model, load GGUF, pass through.

### P0-2: Handle `<think>` Tags in Streaming
**Status:** [x] COMPLETE (2026-03-19)
**Effort:** 0.5 day

**What was built:**
- [x] `backend/services/think_tag_parser.py` — streaming + non-streaming parser utility
  - `parse_think_tags()` for completed text: strips tags, returns `ParsedResponse(content, reasoning)`
  - `StreamingThinkParser` for chunk-by-chunk: stateful, handles partial tag boundaries
- [x] Wired into `local_model_service.py` — `_sync_response` strips tags and adds `reasoning` field; `_stream_response` emits separate `chunk`/`thinking` fields per SSE frame
- [x] Wired into `openai_compat.py` — strips thinking by default; `?include_thinking=true` query param passes thinking through in both streaming and non-streaming
- [x] Wired into `ai_chat.py` — forwards `thinking` field from local model streaming to frontend SSE
- [x] Frontend: `transport.ts` yields `"thinking"` stream chunks; `chat.tsx` tracks `streamingThinking` state; `message-list.tsx` renders collapsible "Thinking" block (purple-themed, Brain icon, auto-opens during streaming)
- [x] Qwen 3 + 3.5 catalog entries verified: all 12 entries use correct `unsloth/` repos with proper casing
- **Decision:** Chat UI strips thinking from content, shows in collapsible UI. OpenAI API strips by default (clean for Aider/Continue.dev).

---

## PHASE 1: THE DEMO (Days 1-6) — Social Auto-Reply

### P1-1: Wire Channel → AI/Crew (GAP 1 — SHOWSTOPPER)
**Status:** [x] COMPLETE (2026-03-20)
**Effort:** 2 days → done in 1 session

**What was built:**
- [x] Replaced stub in `handle_message()` with real AI dispatch
- [x] `_get_ai_response()` resolves default model (local/cloud) and generates response
- [x] `_get_channel_history()` retrieves conversation history for context
- [x] `_store_channel_message()` persists inbound + outbound messages to `channel_messages` collection
- [x] Trigger system integration: checks triggers first, falls through to direct AI if no trigger matches
- [x] Updated Telegram webhook handler to store messages and skip reply for pending approvals

### P1-2: Build Trigger System (GAP 2)
**Status:** [x] COMPLETE (2026-03-20)
**Effort:** 2 days → done in 1 session

**What was built:**
- [x] `backend/repositories/trigger_repository.py` — CRUD + `find_for_channel()` with wildcard support
- [x] `backend/services/trigger_service.py` — cooldown checks, crew dispatch, agent dispatch, approval gating
- [x] `backend/routers/triggers.py` — REST API (GET/POST/PUT/DELETE)
- [x] Wired into `channel_service.handle_message()` — trigger check runs first, falls through to direct AI if none
- [x] Supports: crew execution (async wait up to 2min), single agent execution, cooldown per trigger

### P1-3: Trigger Config UI
**Status:** [x] COMPLETE (2026-03-20)
**Effort:** 1-2 days → done in 1 session

**What was built:**
- [x] `frontend/src/lib/api/triggers-client.ts` — API client (CRUD)
- [x] Auto-reply toggle per connected inbound channel in Connections page
- [x] "Require approval" checkbox per trigger
- [x] Triggers loaded on mount, toggled inline

### P1-4: Human-in-the-Loop Approval Queue
**Status:** [x] COMPLETE (2026-03-20)
**Effort:** 2 days → done in 1 session

**What was built:**
- [x] `backend/repositories/approval_repository.py` — CRUD with pending/approve/reject
- [x] `backend/services/approval_service.py` — create, approve+send, reject, count
- [x] `backend/routers/approvals.py` — REST API (list, count, get, approve, reject)
- [x] `frontend/src/routes/approvals.tsx` — full approval queue page with edit, approve, reject
- [x] `frontend/src/lib/api/approvals-client.ts` — API client
- [x] Added "Approvals" to sidebar navigation with ClipboardCheck icon
- [x] Route registered in App.tsx at `/approvals`
- [x] Flow: trigger fires → AI generates → stored as pending → user reviews → approve/edit/reject → sent via channel

### P1-5: End-to-End Polish & Test
**Status:** [x] COMPLETE (2026-03-20)

**What was tested:**
- [x] Trigger CRUD: create, list, update, delete — all verified via curl
- [x] Approval flow: create pending → list → get → approve with edit → status transitions
- [x] Cooldown logic: tested programmatically
- [x] Error handling: crew not found, agent not found, model not available — all return helpful messages
- [x] Channel message history: stored in `channel_messages` collection
- [x] Rate limiting: cooldown_seconds per trigger (default 0, configurable)
- [x] TypeScript: compiles clean (only pre-existing agents.tsx error)
- [x] Python: all files compile without errors

---

## PHASE 2.5: DIFFERENTIATORS (Next Up — Before Launch)

### P2.5-1: Reddit Connection ⭐
**Status:** [x] COMPLETE (2026-04-15)
**Effort:** 2-3 days → done in 1 session
**Why:** r/LocalLLaMA + r/selfhosted are the exact ICP. Same trigger+approval pipeline as Telegram/Discord. Highest-signal inbound channel for a local-AI product.

**What was built:**
- [x] Reddit script-app auth via praw (token-paste flow, not browser OAuth)
- [x] `backend/models/reddit_models.py` — Pydantic v2 models (account, update, reply)
- [x] `backend/repositories/reddit_repository.py` — CRUD + `get_active()` + `update_last_seen()`
- [x] `backend/services/reddit_client.py` — async praw wrapper (comments, inbox, reply, DM)
- [x] `backend/services/reddit_poller.py` — 60s background poll subreddits + keyword filter + inbox DMs
- [x] `backend/routers/reddit.py` — REST API: account CRUD, test connection, reply
- [x] `ChannelType.REDDIT` added to `channel_service.py`
- [x] Poller dispatches through `channel_service.handle_message()` → triggers + approval pipeline
- [x] `last_seen_ids` per subreddit + inbox for dedupe
- [x] Outbound: `POST /api/v1/reddit/reply` (comment + DM)
- [x] Frontend: Reddit card in Connections UI (orange Flame icon, token-paste)
- [x] `frontend/src/lib/api/reddit-client.ts` — full API client
- [x] `backend/tests/test_reddit.py` — 6 passing tests
- [x] praw==7.8.1 added to requirements.txt
- [x] Respects Reddit rate limits (praw handles 60 req/min internally)

### P2.5-2: Knowledge Base (Local RAG) ⭐⭐ MAJOR DIFFERENTIATOR
**Status:** [x] COMPLETE (2026-04-29)
**Effort:** 3-4 days → done in 1 session
**Why:** Every prospect asks "can I use it with my PDFs/docs?" Fine-tuning is wrong answer (needs GPU, loses facts, can't update). RAG is right: CPU-friendly, citeable, incremental. Directly sells the "local + private" story.

**What was built:**
- [x] Reuses bundled `backend/services/embedding_service.py` (ONNX MiniLM-L6-v2, 384-dim) — no new model needed
- [x] `backend/services/rag_service.py` — ingest, chunk (~500 tokens, 50 overlap, page-tracked for PDFs), embed (batched), numpy cosine retrieval
- [x] PDF via PyMuPDF (already in requirements), DOCX via python-docx, TXT/MD direct
- [x] **Vector store decision:** JSON arrays in SQLite via existing motor_compat layer (no sqlite-vec / chromadb dependency). Cosine = dot product on unit-normalised vectors. Adequate for desktop scale.
- [x] `backend/repositories/knowledge_base_repository.py`, `document_repository.py`, `chunk_repository.py`
- [x] `backend/routers/knowledge_base.py` — KB CRUD, multipart upload, doc list/delete, top-k query
- [x] `backend/models/knowledge_base_models.py` — Pydantic v2 (KnowledgeBaseCreate/Update, KbDocument, Citation, QueryRequest)
- [x] `backend/tests/test_knowledge_base.py` — 12 tests, all passing (10 CRUD/validation + 2 ingest-skipped-without-onnx)
- [x] Frontend `/knowledge` route — two-pane layout: KB list + per-KB tabs (Documents / Test Query). Drag-drop upload, status pills, query test with score-ranked citations
- [x] `frontend/src/lib/api/knowledge-base-client.ts` — full CRUD + multipart upload helper (bypasses JSON-only `apiRequest`)
- [x] Sidebar "Knowledge" entry (Library icon) at `/knowledge`
- [x] Chat input gains a third MiniDropdown: **Knowledge** — pick a KB per chat session
- [x] `routers/ai_chat.py` — `ChatRequest.knowledge_base_id` field; injects formatted citations + `[1] [2] ...` cite-instruction into the prompt for **both** local and Bedrock paths. Original prompt preserved for storage / title generation
- [x] Works with all model providers (local GGUF, Ollama, Bedrock cloud)

**Deferred / next steps:**
- [ ] 3 starter RAG packs in `knowledge-base-packs/` (IRS tax, personal finance, cybersecurity-101) — content task, see `knowledge-base-packs/README.md` for the format
- [ ] Citation chip UI in message bubbles (currently the model just inserts `[1]`/`[2]` text; no hover/click)
- [ ] "Knowledge Base" persona type (persona = KB + system prompt) — convenience wrapper
- [ ] URL ingestion (scrape + chunk web pages)
- [ ] Obsidian vault import
- [x] Incremental re-index on file change — covered by P2.5-3 folder mapping (mtime/size diff classifier)

### P2.5-3: Personal Docs / Folder-Mapped RAG ⭐⭐ MAJOR DIFFERENTIATOR
**Status:** [x] COMPLETE (2026-05-03, shipped in v1.0.0-10)
**Effort:** 4-5 days → done across the `feat/p2.5-3-personal-docs-folder-rag` branch (16 commits)
**Why:** Lets users point Solo at any folder on disk and treat it as a live, citeable knowledge base. Removes the "drag every PDF in by hand" friction from P2.5-2 and turns Solo into a true second brain for an existing notes/Documents folder. Crews + workspace agents can cite from these KBs automatically.

**What was built:**
- [x] `backend/services/folder_walker.py` — depth + glob filtered walk, classifies new/updated/removed via `(abs_path, size, mtime)` diff against existing docs
- [x] `backend/services/personal_docs_service.py` — orchestrator: walk → friction check → embed → persist; surfaces SSE progress
- [x] `backend/services/personal_docs_scheduler.py` — periodic loop honouring per-mapping `manual / 1h / 6h / 24h` schedules
- [x] `backend/repositories/folder_source_repository.py`, `index_job_repository.py` — `kb_folder_sources` + `kb_index_jobs` collections
- [x] `backend/models/personal_docs_models.py` — Pydantic v2 models for sources, jobs, friction-confirm payload
- [x] `backend/routers/personal_docs.py` — REST CRUD + `POST /{kb_id}/folders/{id}/sync` + `GET /jobs/{job_id}/stream` (SSE)
- [x] `backend/services/rag_service.py::ingest_from_path` + `delete_for_source` — re-uses chunk → embed pipeline for folder-sourced files
- [x] **Friction guardrails:** walks above 1,000 files (env-overridable) pause in `awaiting_confirmation` so the UI can show ETA + require explicit confirm before any embeddings run. Hard caps: 10 MB / file, 5,000 files / mapping, depth 10
- [x] Crew + workspace-agent KB binding: `knowledge_base_ids: string[]` on both, with per-agent override of crew default. `services/workspace/agent_runner.py` queries those KBs each turn and prepends a citation block to the system prompt
- [x] Frontend: new `Folders` tab on each KB at `/knowledge/<kb_id>`, `AddFolderModal` (Tauri folder picker via `tauri-plugin-dialog` + `lib/tauri-fs.ts`), `FolderRow` with sync/pause/delete, `SyncProgressPanel` driven by SSE, `KbMultiSelect` shared component
- [x] Sidebar reorder: Knowledge promoted to slot #2 right under Chat for discoverability
- [x] `knowledge-base-packs/README.md` documents the manifest format for downloadable content packs
- [x] Backend tests: `test_folder_walker.py`, `test_folder_source_repository.py`, `test_personal_docs_service.py`, `test_personal_docs_router.py`, `test_rag_ingest_from_path.py`, `test_agent_runner_kb.py`
- [x] E2E: `frontend/tests/e2e/knowledge/personal-docs-folder.spec.ts` — add folder → ingest → docs visible (CI-skipped pending bundled embedding model)

**Deferred / next steps:**
- [ ] CI bundling of the ONNX embedding weights so the e2e suite covers the folder flow
- [ ] Tauri-only inotify/FSEvents watcher for sub-minute incremental updates (current scheduler is poll-based, 1h minimum)
- [ ] Per-source mime/extension allow-list editor in the UI (currently the supported set is static)

---

## PHASE 2: EXPAND REACH

### P2-1: Twitter/X Inbound Polling (GAP 3)
**Status:** [x] COMPLETE (2026-04-19)
- [x] `backend/services/twitter_poller.py` — 90s poll cycle (tighter than Twitter free-tier cap)
- [x] `backend/models/twitter_models.py`, `backend/repositories/twitter_repository.py`, `backend/services/twitter_client.py` (OAuth 1.0a HMAC-SHA1 signing reused from distribution_service)
- [x] `backend/routers/twitter.py` — REST CRUD + `/test` + `/reply`
- [x] `ChannelType.TWITTER` added; poller dispatches through `channel_service.handle_message()`
- [x] `frontend/src/lib/api/twitter-client.ts`

### P2-2: Fix Instagram Publishing (GAP 4)
**Status:** [x] COMPLETE (2026-04-19)
- [x] OAuth callback now calls `GET /me/accounts` → `GET /{page_id}?fields=instagram_business_account`
- [x] Stores `instagram_user_id`, `page_access_token`, `page_id` in the auto-created distribution channel
- [x] Graceful no-op + warning if user has no IG-linked pages

### P2-3: Fix Facebook Publishing (GAP 4)
**Status:** [x] COMPLETE (2026-04-19)
- [x] OAuth callback calls `GET /me/accounts`, stores `page_id` + `page_access_token` (first page)
- [x] TODO: multi-page selection UI (future)

### P2-4: Distribution UI (GAP 5)
**Status:** [x] COMPLETE (2026-04-19)
- [x] `frontend/src/routes/distribution.tsx` — Channels list + Delivery history tabs
- [x] Dynamic per-type config fields (LinkedIn / Twitter OAuth1+bearer / IG / FB / Blog / Email / Slack)
- [x] Multi-channel Publish dialog with per-channel success/fail summary
- [x] Enable/disable toggle, edit/delete, masked credentials on edit
- [x] Route + sidebar (Send icon) wired

### P2-5: Add 15 Social Media Agents
**Status:** [x] COMPLETE 15/15 (2026-04-19)
- [x] Added: `thread-composer.md`, `dm-closer.md`, `community-manager.md`

### P2-6: Pre-built Crew Templates
**Status:** [x] COMPLETE (2026-04-19)
- [x] 4 JSON templates in `backend/crew-templates/`: auto-reply, sales-dm, content-distribution, crisis-response
- [x] `backend/services/crew_template_seeder.py` — seeds into separate `crew_templates` collection on startup
- [x] Re-seed via `POST /api/v1/desktop/reseed` (includes crew_templates_seeded count)

---

## BACKLOG — Post-Launch

### BL-2: Coding Agents (Agent Library)
**Status:** [x] COMPLETE (2026-05-08, absorbed into Phase 4 PR 6 — see `agent-library/coder-companion/`)
**Effort:** 1 day
- [x] Code Reviewer, Bug Analyzer, Test Writer, Doc Generator, Refactoring Advisor — all 5 shipped under `kind="coder"` so they only surface in Coder mode
- [ ] Crew template: Code Review Crew (sequential) — still pending; the `coder_project` crew step (PR 9) lets a crew run a Coder project but a pre-built review template hasn't shipped

### BL-3: Scheduled Crews + Scheduled Posts (Cron-style)
**Status:** [x] COMPLETE (2026-04-19)
- [x] `backend/services/scheduler_service.py` — APScheduler-backed, supports `job_type=post` (via DistributionService) and `job_type=crew` (via CrewService.start_run)
- [x] `backend/models/scheduled_job.py`, `backend/repositories/scheduled_job_repository.py`, `backend/routers/scheduled_jobs.py`
- [x] REST: CRUD + `/run-now` + `/toggle` + `/validate-cron` (returns next 5 fire times)
- [x] Frontend `/schedule` route — cron picker with presets (daily 9am, weekdays, hourly, Monday), timezone select, live preview of next runs
- [x] Publishes on behalf of user to LinkedIn / Twitter / Instagram / Facebook / Slack / Blog / Email via existing DistributionService
- [x] Survives restarts (APScheduler SQLite jobstore)

### BL-4: Crew Templates Marketplace
**Status:** [ ] Not Started
**Effort:** 3-5 days
- [ ] Export/import crew configs as JSON
- [ ] Community GitHub repo for shared templates

### BL-5: Voice Input for Crews
**Status:** [ ] Not Started
**Effort:** 3-5 days
- [ ] Whisper.cpp for local speech-to-text
- [ ] "Hey Solo, run the auto-reply crew"

### BL-6: Mobile Approvals via Telegram Bot
**Status:** [ ] Not Started
**Effort:** 1-2 days

**What it is:** Reuse the existing Telegram connection as the mobile UX. When an approval lands, Solo DMs the user via their personal Telegram bot with the draft + inline buttons (Approve / Edit / Reject). Tap a button → callback hits the backend → reply gets sent through whatever channel originally triggered the approval.

**Why this beats a real app:** zero install, no pairing flow, no push-notification infra, no second codebase. Telegram already handles auth, push, and cross-platform delivery on every phone the user owns.

**Scope:**
- [ ] Reserve one Telegram chat as the "approvals inbox" (user-configurable in settings)
- [ ] On new approval: bot sends message with draft text + 3 inline keyboard buttons (Approve / Edit / Reject)
- [ ] Telegram callback handler in `backend/routers/telegram.py` routes Approve/Reject through existing `approval_service.py`
- [ ] Edit flow: bot prompts for replacement text in a reply thread, then sends
- [ ] Optional: same flow over Discord DM for users who prefer it

**Skipped:** native app, QR pairing, push infra, on-device anything.

### BL-7: LinkedIn Inbound Polling
**Status:** [ ] Not Started
**Effort:** 1-2 days
- [ ] Poll `GET /socialActions/{activityId}/comments` for comment replies
- [ ] LinkedIn messaging API is restricted — comments only

---

## QUICK REFERENCE

**Total models in catalog:** 41 (9 families: Qwen 2.5, Qwen 3, Qwen 3.5, Gemma 3, Gemma 4, Llama, Mistral, Phi, DeepSeek)
**Total agents:** 113 markdown files across 14 categories (engineering 12 + coder-companion 5 excluded from Solo's main library → 96 visible in Solo; the 5 coder-companion agents surface in Coder mode)
**Current release tag:** v1.0.0-11 (cut 2026-05-15)
**Moonshot pick model:** Qwen 3.5 35B-A3B (MoE) — 35B brain, 3B speed, thinking + vision + 256K context
**Backend port:** 18741
**Key files for Phase 1:**
- `backend/services/channels/channel_service.py` (stub to replace)
- `backend/services/local_model_service.py` (inference engine)
- `backend/services/model_catalog.py` (37 models)
- `frontend/src/routes/connections.tsx` (trigger UI)

**Key files for Phase 2.5 (Reddit + KB):**
- `backend/routers/desktop_oauth.py` (add reddit provider)
- `backend/services/reddit_poller.py` (new — inbound polling)
- `backend/services/rag_service.py` (new — ingest/embed/retrieve)
- `backend/routers/knowledge_base.py` (new)
- `frontend/src/routes/knowledge.tsx` (new)

**Next up order:**
1. ~~Merge `feat/crew-channel-wiring` → main + cut `v1.0.0-beta.4`~~ DONE (#17 merged, beta.6 tagged)
2. ~~P2.5-1 Reddit Connection~~ DONE (2026-04-15)
3. ~~Phase 2 remainder (P2-1…P2-6) + BL-3 Scheduler~~ DONE (2026-04-19)
4. P2.5-2 Knowledge Base (RAG) — reuse existing `embedding_service.py`
5. ~~Phase 3 Launch~~ DONE (2026-04-22)

---

## PHASE 3: UNIFY CONNECTIONS + CREWS (IA Refactor) ⭐ HIGH PRIORITY
**Status:** [x] COMPLETE (2026-04-22)
**Added:** 2026-04-20
**Effort estimate:** ~4 PRs, 3–5 dev sessions

> This is a **UI-first information-architecture refactor**. Today we have three confusing surfaces (Connections, Distribution, Schedule) that each hold their own auth or scheduling state. A user who connects Reddit once has to re-configure it to publish; a user who sets a schedule doesn't see it in their crew. This phase collapses everything into a cleaner mental model.

### Mental model (the "north star")
- The app is a **team**. Agents = team members, Crews = teams.
- Teams (crews) **do work** using **connections** (their tools). Connections are user-level, not crew-level — Solo is single-user, so the user authenticates once per platform.
- A crew picks which connections it uses, which **direction** per connection (`Inbound`, `Outbound`, or `Both`), and a **trigger** (Reactive on inbound messages, Scheduled via cron/date-picker, or Manual via the existing "Run" button).
- Distribution and Schedule stop being destinations — publishing is just "a crew with outbound connections on a scheduled trigger." Scheduling is just "a trigger on a crew." Approvals flow through the existing Approvals page when a crew is flagged `approval_required`.

### Confirmed decisions (do not revisit)
1. **Manual trigger** = the existing "Run" button on each crew card (`frontend/src/routes/crews.tsx:481`). Not a new trigger-type selection in the builder. Always available on every crew.
2. **Runs view** = the existing `Runs` tab on the Crews page (`frontend/src/routes/crews.tsx:130` — tab state `activeTab: "crews" | "runs"`). Extend the existing `CrewRun` type with trigger metadata; do not build a new component.
3. **Distribution & Schedule are removed from the sidebar.** Their functionality lives entirely inside Crews now (outbound publishing via `connection_bindings`, scheduling via `triggers[type=scheduled]`); a Coming Soon stop would be redundant. Sidebar drops from 12 → 10 items; nav E2E test (`frontend/tests/e2e/navigation/navigation.spec.ts`) updated accordingly.
4. **Blog / Email / Slack webhook** ship as new Connection types (outbound-only) inside the same Connections grid as the social platforms.
5. **Inbound keyword-match ties** → LLM disambiguates. No per-crew priority UI.
6. **Connection-level fallback crew** for unmatched inbound → **not in v1**. Drop messages silently; reconsider if users complain.

### Data model

**Connection (existing stores — additive changes)**
- Add `inbound_enabled: bool` and `outbound_enabled: bool` capability flags on each connection record across:
  - `oauth_tokens` (LinkedIn, Instagram, Facebook)
  - `reddit_accounts`
  - Telegram/Discord/Twitter token-paste stores
- Add three **new connection types** — outbound-only, stored in a new `outbound_connections` table or extend existing `distribution_channels`:
  - `blog` (Ghost, WordPress, custom API)
  - `email` (SendGrid, SES, SMTP)
  - `slack_webhook` (incoming webhook URL)

**Crew (extend existing crew document)**
- Rename `channel_bindings[]` → `connection_bindings[]`:
  ```
  { connection_id, platform, direction: "inbound" | "outbound" | "both" }
  ```
- Add `triggers[]`:
  - Reactive: `{ type: "reactive", connection_id, keywords: string[], hashtags: string[], mentions: string[] }`
  - Scheduled: `{ type: "scheduled", connection_ids: string[], cron?: string, run_at?: ISO, content_brief?: string }`
  - Manual is implicit — no entry needed; "Run" button always works.
- Add `approval_required: bool` (top-level on crew).

**CrewRun (extend existing model)**
- Add `trigger_type: "reactive" | "scheduled" | "manual"`
- Add `trigger_source`: connection_id (reactive), cron expression or run_at (scheduled), "manual" (button)
- So the existing Runs tab can display *why* each run fired.

**Runs persistence**
- Reuse `workspace_jobs` table (don't add another). Each reactive match or scheduled fire creates a workspace_job with `status`, `trigger_type`, `inbound_message_id?`, `output`, and `approval_state`.

### Backend work

**New files**
- [x] `backend/services/connection_service.py` — unified aggregator over existing stores. Exposes:
  - `list_connections() -> [ConnectionSummary]`
  - `get_capabilities(conn_id) -> {inbound, outbound}`
  - `set_capability(conn_id, direction, enabled)`
- [x] `backend/services/inbound_router.py` — on inbound message:
  1. Find crews with reactive trigger on this connection.
  2. Keyword/hashtag/mention substring match.
  3. If >1 match, call an LLM (cheap model — Haiku or local Gemma) to pick best match.
  4. Dispatch the chosen crew via existing agent_runner.
  - Initially: thin wrapper over existing `channel_service.handle_message`; layer matching logic on top to avoid regression.
- [x] `backend/services/scheduled_runner.py` — polls crews for `triggers[type=scheduled]`, fires at cron/run_at boundaries. **Replaces** the internals of the standalone scheduler — but the standalone Schedule page still shows Coming Soon.
- [x] `backend/routers/connections.py` (new aggregator):
  - `GET /api/v1/connections` — unified list
  - `PATCH /api/v1/connections/{id}/capabilities` — toggle inbound/outbound
  - Existing per-platform credential endpoints (OAuth/token paste/Reddit) remain unchanged.

**Modified files**
- [x] `backend/services/workspace/agent_runner.py` — after crew run completes, if any `connection_binding` has outbound enabled, publish the final agent output via the corresponding adapter. No more separate `distribution_service`. If `crew.approval_required`, create an approval record instead of sending directly.
- [x] `backend/services/crew_service.py` — add trigger + approval fields; validate trigger configs.
- [x] `backend/models/crew_models.py` — Pydantic additions for `connection_bindings`, `triggers`, `approval_required`.

**Deprecated (do NOT delete yet — user asked to keep Coming Soon)**
- `backend/routers/distribution.py` — leave wired but return `{status: "coming_soon"}` stub on routes called by the deprecated frontend page. Or mark the router unused once frontend stops calling it.
- `backend/services/distribution_service.py` — logic folded into agent_runner's outbound publishing. File can stay for the outbound adapters it owns (LinkedIn/Twitter/IG/FB/Blog/Email/Slack publishers) — reuse them from connection_service / agent_runner.
- Standalone scheduler service (if any — check `backend/routers/triggers.py` and `backend/services/` for cron impl) — disable once `scheduled_runner.py` handles crew-level scheduling. Keep code around until the Schedule page is retired.

### Frontend work

**Rewrite**
- [x] `frontend/src/routes/connections.tsx` — one grid with all 10 types:
  - 7 socials: Telegram, Discord, Reddit, LinkedIn, Twitter/X, Instagram, Facebook
  - 3 new outbound-only: Blog, Email, Slack webhook
  - Each card: auth status, **Inbound toggle** (hidden for outbound-only types), **Outbound toggle**, Manage/Disconnect.
- [x] `frontend/src/components/crews/crew-builder.tsx` — revise the 5-step wizard → 7-step wizard:
  - **Step 4 "Connections & Directions"**: pick connections, per-connection direction chip selector (`Inbound` / `Outbound` / `Both`).
  - **Step 5 "Trigger"**: Reactive (+ `keywords`, `hashtags`, `mentions` multi-input) and/or Scheduled (cron field + one-shot date-picker). Both can be enabled; manual is implicit.
  - **Step 6 "Approval"**: single toggle "Review outbound before sending."
  - Step 7 "Review & Create" — summary reflects all new fields.

**Removed (PR 4)**
- [x] Drop `/distribution` and `/schedule` route registrations from `App.tsx`.
- [x] Drop the Distribution + Schedule sidebar entries from `frontend/src/components/navigation/desktop-sidebar.tsx` (sidebar 12 → 10 items).
- [x] Update nav E2E test in `frontend/tests/e2e/navigation/navigation.spec.ts` to expect 10 items.
- [x] Page files `frontend/src/routes/distribution.tsx` and `frontend/src/routes/schedule.tsx` stay on disk for one release cycle as dead code — the FUTURE cleanup task deletes them.

**Modified**
- [x] `frontend/src/routes/crews.tsx` — **Crews tab**: filter chips for Inbound, Outbound, Scheduled, Reactive, Approval-required. **Runs tab**: `trigger_type` badge on each run row.
- [x] `frontend/src/lib/api/crews-client.ts` — `CrewRun` type extended with `trigger_type`, `trigger_source`.
- [x] `frontend/src/lib/api/distribution-client.ts` — no longer consumed by active UI; stays for future-cleanup phase.

**Not changed**
- Sidebar entries other than Distribution + Schedule — order, icons, labels untouched.

### Migration

**File:** `backend/migrations/0002_unify_connections.py`

Must be idempotent, dry-run capable (`MIGRATE_DRY_RUN=1` env var), and must write a version marker so it doesn't double-run.

1. Read all `distribution_channels` docs → for LinkedIn/Twitter/IG/FB, upsert into the corresponding OAuth connection store (merging credentials where overlap exists). For Blog/Email/Slack webhook, insert into the new `outbound_connections` table.
2. Read any existing standalone scheduled jobs (check `backend/routers/triggers.py` + scheduler storage):
   - For each, find the crew associated with its channel binding.
   - Append a matching `{type: "scheduled"}` entry to `crew.triggers`.
   - Log orphans (no crew match) as warnings and list them to a `migration_orphans.json` artifact for manual review.
3. For every crew, transform existing `channel_bindings[]` → `connection_bindings[]` with `direction: "both"` (preserves current behavior — every currently-bound channel was implicitly doing both directions).
4. For each connection record, set `inbound_enabled` / `outbound_enabled` defaults based on what that connection was actively doing (any bound crew + any active trigger polling = inbound_enabled; any distribution channel or schedule posting through it = outbound_enabled).
5. Write `{migration: "0002_unify_connections", applied_at: <iso>}` to a migrations tracking collection.

### Risks & mitigations

- **Migration correctness** — scheduled jobs / distribution channels could be miswired. Mitigation: dry-run mode that emits a diff JSON the user reviews before real run. Surface unresolved orphans in a startup log banner.
- **Inbound routing regressions** — Telegram/Reddit users in prod today rely on `channel_service.handle_message`. Mitigation: `inbound_router.py` starts as a thin delegator; keyword/LLM matching gated behind a `UNIFIED_ROUTING` flag that can flip per-connection.
- **Visible blast radius** — once Distribution/Schedule pages become Coming Soon, anything a user was actively using there must have a clear landing spot. Mitigation: the Coming Soon page links to the specific Crews page where that work now lives; a one-time startup banner flags any unmigrated items.

### PR sequence

**Each PR is independently mergeable, behind feature flag where needed.**

| PR | Scope | Flag |
|---|---|---|
| 1 | Data model additions (connection_bindings, triggers, approval_required, capability flags) + migration script (dry-run capable) + extended CrewRun schema. Backend only; no UI change; existing flows keep working. | — (additive) |
| 2 | Unified `/api/v1/connections` aggregator + rewritten Connections page (capability toggles, Blog/Email/Slack new types). Old Distribution page still lives. | — |
| 3 | Crew builder: Trigger step + Direction chips + Approval toggle + "enable capability at connection level" modal. Backend: `inbound_router.py` + `scheduled_runner.py`. Runs tab displays trigger_type badge. | `UNIFIED_CREWS` env flag |
| 4 | Remove `/distribution` + `/schedule` from sidebar and route registry; nav E2E test 12 → 10. Flip `UNIFIED_CREWS` on by default. | Flag default → true |

### Follow-up TODOs (track after Phase 3 ships)

- [ ] FUTURE: Delete dead code one release cycle after PR 4 — `frontend/src/routes/distribution.tsx`, `frontend/src/routes/schedule.tsx`, `backend/routers/distribution.py`, the standalone scheduler backend. `backend/services/distribution_service.py` stays — its outbound adapters (LinkedIn/Twitter/IG/FB/Blog/Email/Slack publishers) are reused by `agent_runner.py`.
- [ ] FUTURE: Connection-level fallback crew for unmatched inbound messages (skipped in v1 per user decision).
- [ ] FUTURE: Global Activity/Runs view across all crews (skipped in v1 — per-crew Runs tab covers the need).
- [ ] FUTURE: Per-crew priority ordering for keyword-match ties (skipped — LLM disambiguation handles v1).

### Key files reference (for the implementer)

**Existing code to read first (understand before touching):**
- `frontend/src/routes/crews.tsx` — already has tabs (`Crews`/`Runs`) and manual Run button. Line 130 (tab state), 179 (filter logic), 481 (Run button), 498 (RunsList).
- `frontend/src/routes/connections.tsx` — current 7-platform grid with OAuth + token-paste flows.
- `frontend/src/routes/distribution.tsx` — current publish-focused page; patterns to preserve (multi-select, delivery log).
- `frontend/src/components/crews/crew-builder.tsx` — current 5-step wizard to extend.
- `backend/services/channels/channel_service.py` — current inbound `handle_message()` — the thing `inbound_router.py` delegates to initially.
- `backend/services/distribution_service.py` — existing outbound adapters (LinkedIn/Twitter/IG/FB/Blog/Email/Slack) — reuse, don't rewrite.
- `backend/services/workspace/agent_runner.py` — where outbound publishing hooks in after crew execution.

**Acceptance criteria**
- User flow: Connect Reddit once in Connections → enable Inbound + Outbound capabilities → create Crew A (reactive on Reddit with keywords `pricing, demo`) and Crew B (scheduled daily post to Reddit) → both work, same single Reddit auth, no duplicate configuration anywhere.
- Distribution and Schedule sidebar items click through to Coming Soon pages.
- Existing Crews from before migration continue to work (channel_bindings auto-converted to direction="both").
- Migrated distribution channels appear in Connections with Outbound enabled.
- Manual "Run" button still works on every crew.

---

## PHASE 4: REVISION — CONSOLIDATION + AUTOMATIONS + CODER MODE ⭐ HIGH PRIORITY
**Status:** [x] COMPLETE (2026-05-12, shipped in v1.0.0-11) — Phase 5 multi-agent Coder followed in v1.0.0-11 itself (PR 38)
**Added:** 2026-05-05
**Effort estimate:** ~7 PRs, 6–8 weeks end-to-end — actual: ~10 PRs landed across `feat/phase-4-integration` and `feat/phase-5-coder-multi-agent`

> Consolidates the four overlapping nouns (Agents, Personas, Crews, Workspace) into {Crews, Automations}. Adds a natural-language Automations surface ported from the enterprise repo. Introduces Coder as a co-equal product mode via a top-center toggle (Solo / Coder). Sidebar drops 10 → 8 in Solo mode (Models stays as a daily-use surface); Coder mode gets its own 5-item sidebar. Personas and Workspace collapse into **tabbed pickers/pages** rather than filter chips — tabs make categorical distinctions visible (Database vs Prompt agent; Crew vs Project) instead of flattening them into one filterable list.

### P4-1: Automations MVP ⭐ NEW SURFACE
**Status:** [x] COMPLETE (2026-05-05, PR 1 on `feat/phase-4-integration`)
**Effort:** 1 week → done in 1 PR
**Why:** Crews require a 7-step wizard for one-off work. Automations gives users a natural-language fast path: write `@agent`-mention prompts, pick output actions, run. Lowest-friction authoring path Solo has ever had.

- [ ] Port `services/automation_engine.py`, `automation_executor.py`, `automation_output_service.py` from `C:\Users\nagen\Projects\contextuai\backend` (replace Bedrock-specific bits with Solo's local-model service)
- [ ] Add `services/automation_parser.py` — `@mention` regex + optional model-based exec-mode inference
- [ ] `repositories/automation_repository.py`, `automation_execution_repository.py`
- [ ] `routers/automations.py` — CRUD + `/run` + `/validate` + `/executions` + `/executions/{id}/stream` (SSE)
- [ ] `models/automation_models.py` — adapt enterprise version, drop `user_id`
- [ ] PDF output via reportlab/weasyprint; PPTX via python-pptx; reuse existing Distribution adapters for channel outputs
- [ ] Frontend `/solo/automations` route — list + builder + run history
- [ ] `solo/components/automations/automation-builder.tsx` + `output-action-picker.tsx`
- [ ] `solo/lib/api/automations-client.ts`
- [ ] "Promote to Crew" button — converts Automation into a scheduled Crew
- [ ] Sidebar entry "Automations" added

### P4-2: Personas → Agent types (tabbed picker)
**Status:** [x] COMPLETE (2026-05-05, PR 2 on `feat/phase-4-integration`)
**Effort:** 3 days → done in 1 PR
**Why tabs not filters:** a Postgres connection and a system-prompt agent are *categorically* different things. A tab makes the mode-of-operation visible per kind; a filter chip flattens them into "narrow this list."
- [ ] Migration `backend/migrations/0003_personas_to_agent_types.py` — idempotent, dry-run, version-marked
- [ ] Add `kind: "prompt" | "database" | "web" | "mcp" | "api" | "file"` to `workspace_agents`
- [ ] Backfill existing personas as workspace_agents with the right kind
- [ ] Agent library picker is **tabbed by kind**: `Prompt | Database | Web | MCP | API | File`. Each tab = its own catalog (kind-specific empty state, "Add new" CTA, list columns).
- [ ] Selected tab persists in localStorage per builder context; default = `Prompt` on first open
- [ ] "Add Agent" opens directly into the active tab's kind (no separate kind-selector step)
- [ ] Coming Soon stub on `/solo/personas` for one release; redirect to `/solo/agents?kind=...`
- [ ] Delete `frontend/src/routes/personas.tsx` after one release

### P4-3: Workspace → Crews tabbed page
**Status:** [x] COMPLETE (2026-05-05, PR 3 on `feat/phase-4-integration`)
**Effort:** 3 days → done in 1 PR
**Why tabs not filters:** a Crew (recurring, channel-bound, scheduled) and a Project (one-shot, manual) have different mental models, list columns, empty states, and "New" CTAs. Tab signals "different mode of this module"; chip suggests "same thing, narrowed."
- [ ] Migration `backend/migrations/0004_workspace_to_crew_runs.py` — idempotent, dry-run, version-marked
- [ ] Add `kind: "crew" | "project"` to `crews` documents (default `"crew"`)
- [ ] `workspace_projects` → `crews` rows with `kind="project"`
- [ ] `workspace_jobs` → `crew_runs` rows with `trigger_type="manual"` default
- [ ] Crews page becomes **tabbed**: `Crews | Projects | Runs`
  - Each tab has its own toolbar: Crews/Projects tabs get "New" + blueprint picker; Runs tab gets status/date filters
  - Runs tab spans both kinds and shows `kind` badge per row
  - Selected tab persists in localStorage; deep-link via `?tab=crews|projects|runs`
- [ ] Coming Soon on `/solo/workspace` for one release; redirect to `/solo/crews?tab=projects`; delete after

### P4-4: Dead-code cleanup (Models stays in sidebar)
**Status:** [x] PARTIAL (2026-05-05, PR 4 sidebar trim done) — final dead-code deletions still pending (`distribution.tsx`, `schedule.tsx`, `personas.tsx`, `workspace.tsx`)
**Effort:** 1 day
**Decision (2026-05-05):** Models is a daily-use surface — keep at `/solo/models`, do not collapse into Settings.
- [ ] Models stays at `/solo/models`, sidebar entry retained
- [ ] Delete `frontend/src/routes/distribution.tsx`, `schedule.tsx` (Phase 3 cleanup carryover)
- [ ] Delete `frontend/src/routes/agents.tsx` (replaced by tabbed picker inside Crew/Automation builders — see P4-2)
- [ ] Update navigation E2E test → **8 sidebar items** in Solo mode (Chat, Knowledge, Automations, Crews, Approvals, Distributions, Models, Settings)
- [ ] **Library hub deferred** — tabbed pickers in P4-2 / P4-3 cover discoverability; revisit if usage data shows browsing pain

### P4-5: App-shell mode toggle ⭐ FOUNDATION
**Status:** [x] COMPLETE (2026-05-05, PR 5 on `feat/phase-4-integration`)
**Effort:** 1 week → done in 1 PR
**Why:** Solo + Solo Coder is the headline story. Toggle is the foundation everything in PRs 6–7 hangs on. Ships *before* Coder content so we can land Solo consolidation cleanly first.

- [ ] `frontend/src/shell/ModeToggle.tsx` — segmented pill, top-center title bar, ~140px wide
- [ ] `frontend/src/shell/ModeProvider.tsx` — context provider, persists in localStorage (`solo.app.mode`)
- [ ] `frontend/src/shell/window-title.ts` — Tauri `setTitle` per mode
- [ ] Restructure routes: `frontend/src/solo/*` and `frontend/src/coder/*`
- [ ] Top-level `App.tsx` becomes thin mode-router; lazy-loads each mode's bundle
- [ ] `Cmd+Shift+M` / `Ctrl+Shift+M` keyboard shortcut for toggle
- [ ] Native menu adapts per mode (File menu items differ)
- [ ] Coder mode v1 = "Coming soon" splash + working toggle
- [ ] Settings → Coder → "Disable Coder mode" kill switch (hides toggle)
- [ ] macOS title-bar fallback: pill in workspace area if title bar customization is constrained
- [ ] E2E test for mode toggle (toggle visible, persists across reload)

### P4-6: Coder MVP ⭐⭐ FLAGSHIP
**Status:** [x] COMPLETE (2026-05-08, PR 6 on `feat/phase-4-integration`); multi-agent extension shipped in Phase 5 (PRs 13–19, v1.0.0-11)
**Effort:** 2–3 weeks → MVP done in one PR; multi-agent in 7 follow-up PRs
**Why:** Local, free Codex/Claude Desktop Code equivalent for business users. Sharpest competitive wedge Solo has — every cloud alternative is $20/mo and uploads your code.

**Backend:**
- [ ] `models/coder_models.py` — CoderProject, CoderRun, CoderTemplate
- [ ] `repositories/coder_project_repository.py`, `coder_run_repository.py`
- [ ] `services/coder_project_service.py` — project CRUD, trust state, allowlist enforcement
- [ ] `services/coder_run_service.py` — process lifecycle, stdout SSE
- [ ] `services/coder_template_service.py` — scaffold from template
- [ ] `routers/coder_projects.py` — CRUD + `/{id}/files` (read/write/diff) + `/{id}/run` + `/{id}/stop`
- [ ] `routers/coder_run.py` — SSE stdout stream, kill, list-running

**Tauri:**
- [ ] Extend `frontend/src-tauri/capabilities/` with Coder capability — allowlisted shell exec, scoped FS
- [ ] Default binary allowlist: `node, npm, npx, pnpm, bun, python, python3, pip, pipx, pytest, git, cargo, rustc, go`
- [ ] Settings-extensible allowlist
- [ ] CWD scoping enforced — no `..`, no symlink escape

**Templates** (4 starters):
- [ ] `coder-templates/web-app/` — Vite + React + TS, `npm run dev` → :5173
- [ ] `coder-templates/telegram-bot/` — Node.js + grammy, reads `.env`
- [ ] `coder-templates/cli-tool/` — Python + click
- [ ] `coder-templates/static-site/` — plain HTML/CSS/JS landing page, served via `python -m http.server` or `npx serve` → :8080. Lowest-skill template; the "I just want a webpage" entry point.

**Coder-companion agents** (5 NEW — none exist today, BL-2 carryover):
- [ ] `agent-library/coder-companion/code-reviewer.md`
- [ ] `agent-library/coder-companion/bug-analyzer.md`
- [ ] `agent-library/coder-companion/test-writer.md`
- [ ] `agent-library/coder-companion/doc-generator.md`
- [ ] `agent-library/coder-companion/refactor-advisor.md`
- [ ] Add `kind="coder"` so they only surface in Coder mode

**Frontend:**
- [ ] `coder/routes/projects.tsx` — list + new project modal
- [ ] `coder/routes/project.tsx` — main workspace (chat + files + run + preview)
- [ ] `coder/routes/running.tsx` — live process list across all projects
- [ ] `coder/routes/templates.tsx` — template browse + scaffold
- [ ] `coder/components/project/file-diff-card.tsx` — apply/undo per file
- [ ] `coder/components/project/run-pane.tsx` — stdout stream + run/stop controls
- [ ] `coder/components/project/preview-pane.tsx` — embedded iframe of `localhost:PORT`
- [ ] `coder/components/project/trust-prompt.tsx` — first-run trust grant modal
- [ ] `coder/lib/api/coder-projects-client.ts`
- [ ] Right-click file → "Review with code-reviewer" / "Add tests with test-writer" / etc.

**Settings:**
- [ ] Settings → Coder tab (allowlist editor, network policy, default model, kill switch)

**Acceptance:**
- [ ] User can scaffold Web App template, "build a counter component," see edits applied, click Run, see preview iframe
- [ ] User can scaffold Telegram Bot, paste token in `.env`, run, see bot stdout
- [ ] User can scaffold Static Site, "make me a portfolio page about X," see preview iframe
- [ ] Trust prompt appears once per project, not per command
- [ ] Allowlist enforcement — `rm -rf` or other off-allowlist commands rejected with clear error
- [ ] Settings → Disable Coder routes `/coder/*` to Solo with a notice
- [ ] All four templates work end-to-end on Windows + macOS

### P4-7: Cross-mode handoffs
**Status:** [x] COMPLETE (2026-05-10, PR 7 on `feat/phase-4-integration`; crew coder step in PR 9; saved cloud keys in PR 8)
**Effort:** 4 days → done across PRs 7–9
**Why:** The integration story is the moat — cloud competitors can't compose Coder + Assistant because they're separate products. Solo can.
**Scope discipline:** ship the high-leverage handoffs only; defer error→Crew bridge to avoid feature overload.

- [ ] `OutputActionType.RUN_CODER_PROJECT` in automation models — invoke Coder project headlessly, return artifacts
- [ ] `services/coder_run_service.py::run_headless()` — no-UI execution path
- [ ] New crew step type `coder_project` referencing project by ID
- [ ] Coder project menu: "Index as KB" — reuses existing Personal Docs folder-mapping pipeline; no new ingestion path, just a one-click wrapper around `services/personal_docs_service.py`
- [ ] Coder project menu: "Distribute artifact" (output → Distributions picker)
- [ ] Coder error → "Diagnose with @bug-analyzer" deep-link into Solo chat (chat-only)
- [ ] Solo Automation builder gets the new output type
- [ ] Solo Crew builder Step 3 gets the new step type
- [ ] **Deferred:** error → Crew bridge. Adds picker friction and overlaps with the chat bridge. Asymmetry with Crew → Coder direction is acceptable for v1.

### Risks & non-goals (cross-cutting)
- **Non-goals:** No third mode in v1. No LSP/debugger/file-tree-rail/multi-tab editor in Coder. No cloud sync between machines. No mobile companion.
- **Risk: Coder MVP scope creep into IDE territory** — hard line written into the spec. Pointer to OpenAI-compat (P0-1) + VS Code for users wanting that path.
- **Risk: Tauri shell exec security** — per-project trust, allowlist, scoped paths, kill switch, default-block-network toggle.
- **Risk: Local code-model quality lag** — recommend Qwen 2.5 Coder 32B / DeepSeek R1 14B (already in catalog); cloud opt-in via Anthropic/Bedrock keys; honest UI labels.
- **Risk: Confusion vs enterprise ContextuAI** — marketing line: Solo Coder = "build your own software locally for free." Enterprise = engineering team platform. Different audiences, different repos.

---

## PHASE 5: CODER MULTI-AGENT ⭐ FLAGSHIP EXTENSION
**Status:** [x] COMPLETE (2026-05-15, shipped in v1.0.0-11 / PR 38 merge)
**Added:** 2026-05-08
**Effort estimate:** 7 PRs across `feat/phase-5-coder-multi-agent`

Took the Coder MVP (PR 6) from a solo-agent loop to a multi-agent workflow with roles, presets, parallel execution, and explicit per-project model picking. Also generalised model dispatch and overhauled provider onboarding.

- [x] **PR 13: Universal `/v1/*` dispatcher** — `services/model_dispatcher.py` routes `anthropic:` / `openai:` / `google:` / `bedrock:` / `ollama:` / bare-name model IDs through one path, used by `routers/openai_compat.py` and the workflow engine. Adds direct services for OpenAI, Anthropic, Google, Ollama; Bedrock keeps `UniversalModelAdapter`.
- [x] **PR 14: Agent roles, presets, workflow config** — `coder_models.py` adds `CoderAgentRole`, `coder_agent_role_repository.py` + `coder_role_preset_service.py` seed planner / coder / reviewer / etc. presets. `routers/coder_roles.py` exposes CRUD; `coder_workflow_mode_migration.py` adds `workflow_mode` to existing projects.
- [x] **PR 15: Multi-agent workflow execution engine** — `services/coder_workflow_service.py` implements solo / sequential / parallel / custom modes. Tested via `test_coder_workflow_{sequential,parallel,custom,solo,run_preview,mode,unconfigured}.py` (full coverage).
- [x] **PR 16: Team panel + multi-agent chat** — `components/coder/team-panel.tsx`, `role-card.tsx`. Chat surface now shows which role authored each turn; supports parallel role outputs.
- [x] **PR 17: Mode-toggle redirect + presets + fail-fast model checks** — toggling Solo↔Coder lands the user on the right home route; missing-model errors surface up to the UI instead of silently falling back.
- [x] **PR 18: Pick models at project creation** — `components/coder/model-picker.tsx`, `new-project-dialog.tsx`. No silent fallbacks: project creation refuses to proceed unless every required role has a resolvable model.
- [x] **PR 19: AI Providers onboarding cards** — Settings → AI Providers tab rebuilt as Distributions-style cards (`provider-card.tsx`, `cloud-provider-card.tsx`, `cloud-providers-tab.tsx`, `data/provider-guides.ts`). Per-provider paste-key + test-connection + setup-guide modal.

**Cleanup carried into v1.0.0-12:**
- [ ] Delete `frontend/src/routes/distribution.tsx`, `schedule.tsx`, `personas.tsx` (banner-only), `workspace.tsx` — all routes still mounted in `App.tsx` for the one-release deprecation window.
- [ ] Re-enable KB e2e + Personal Docs folder e2e in CI by bundling the all-MiniLM-L6-v2 ONNX weights into the GitHub Actions runner.

---

*This document is excluded from git. For internal planning only.*
