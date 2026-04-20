# TODO — ContextuAI Solo Moonshot

> Master task list. Prioritized by phases. Check off as completed.
> **Created:** 2026-03-19 | **Last synced with code:** 2026-04-15

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
**Status:** [ ] Not Started
**Effort:** 3-4 days
**Why:** Every prospect asks "can I use it with my PDFs/docs?" Fine-tuning is wrong answer (needs GPU, loses facts, can't update). RAG is right: CPU-friendly, citeable, incremental. Directly sells the "local + private" story.

**Backend:**
- [x] Embedding infra already exists: `backend/services/embedding_service.py` (ONNX MiniLM-L6-v2, 384-dim, bundled with installer) — **reuse this, don't rebuild**
- [ ] `backend/services/rag_service.py` — ingest, chunk, retrieve (uses existing embedding_service)
- [ ] PDF parsing via `pypdf`; docx via `python-docx`; txt/md direct
- [ ] Chunking: 500 tokens, 50 overlap, preserve page numbers
- [ ] Vector store: **sqlite-vec** extension (keeps single-file DB story) — fallback `chromadb` if sqlite-vec too fragile on Windows
- [ ] `backend/repositories/knowledge_base_repository.py` + `document_repository.py`
- [ ] `backend/routers/knowledge_base.py` — CRUD KBs, upload docs (multipart), delete, reindex, query
- [ ] Retrieval: top-k (default 5) with MMR dedupe; return chunks + `{filename, page, score}` citations

**Frontend:**
- [ ] New route `/knowledge` — list KBs, create/delete
- [ ] Drag-drop PDF upload with progress bar
- [ ] Doc list per KB with size, page count, indexed status
- [ ] Attach KB to chat session (dropdown in chat header)
- [ ] Attach KB to crew/agent config
- [ ] Citation rendering in message bubbles: `[1]` chip → hover shows filename p.N excerpt

**Integration:**
- [ ] New persona type: "Knowledge Base" — persona = KB + system prompt
- [ ] Chat: when KB attached, prepend retrieved chunks to system prompt with `[source: filename p.N]`
- [ ] Works with both local (Gemma/Qwen) and cloud models
- [ ] Crew agents can reference a shared KB

**Stretch:**
- [ ] URL ingestion (scrape + chunk web pages)
- [ ] Obsidian vault import
- [ ] Incremental re-index on file change

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
**Status:** [ ] Not Started
**Effort:** 1 day
- [ ] Code Reviewer, Bug Analyzer, Test Writer, Doc Generator, Refactoring Advisor
- [ ] Crew template: Code Review Crew (sequential)

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

### BL-6: Mobile Companion App
**Status:** [ ] Not Started
**Effort:** 2-4 weeks
- [ ] Approval queue on phone
- [ ] Push notifications for pending approvals
- [ ] React Native or Flutter

### BL-7: LinkedIn Inbound Polling
**Status:** [ ] Not Started
**Effort:** 1-2 days
- [ ] Poll `GET /socialActions/{activityId}/comments` for comment replies
- [ ] LinkedIn messaging API is restricted — comments only

---

## QUICK REFERENCE

**Total models in catalog:** 41 (8 families: Qwen 2.5, Qwen 3, Qwen 3.5, Gemma 3, Gemma 4, Llama, Mistral, Phi, DeepSeek)
**Total agents:** 105 markdown files across 13 categories (incl. 12/15 social in `social-engagement/`)
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
5. Phase 3 Launch

---

*This document is excluded from git. For internal planning only.*
