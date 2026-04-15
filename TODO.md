# TODO — ContextuAI Solo Moonshot

> Master task list. Prioritized by phases. Check off as completed.
> **Created:** 2026-03-19 | **Last synced with code:** 2026-04-14

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

### P2.5-1: Reddit Connection ⭐ NEXT
**Status:** [ ] Not Started
**Effort:** 2-3 days
**Why:** r/LocalLLaMA + r/selfhosted are the exact ICP. Same trigger+approval pipeline as Telegram/Discord. Highest-signal inbound channel for a local-AI product.

- [ ] Reddit OAuth2 integration (script-type app → refresh token)
- [ ] Add to `backend/routers/desktop_oauth.py` providers dict
- [ ] Add to Connections UI (`frontend/src/routes/connections.tsx`)
- [ ] Inbound: `backend/services/reddit_poller.py` — background poll subreddits + keyword mentions + inbox DMs every 60s
- [ ] Store `last_seen_id` per subreddit to dedupe
- [ ] Outbound: `POST /api/comment`, `POST /api/compose` for DMs
- [ ] Wire into trigger system (`channel_service.handle_message()`)
- [ ] Trigger example: "When someone mentions 'local LLM' in r/LocalLLaMA → run Crew"
- [ ] Distribution service: outbound post/comment publishing
- [ ] Respect Reddit rate limits (60 req/min OAuth)

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
**Status:** [ ] Not Started
**Effort:** 1 day
- [ ] `backend/services/twitter_poller.py` — background polling `GET /2/users/:id/mentions` every 60s
- [ ] Store `last_seen_id` to avoid duplicate processing
- [ ] Feed new mentions into trigger system
- [ ] Also poll `GET /2/dm_events` for DM auto-reply

### P2-2: Fix Instagram Publishing (GAP 4)
**Status:** [ ] Not Started
**Effort:** 0.5 day
- [ ] After Facebook OAuth, call Instagram Graph API to get `instagram_business_account`
- [ ] Store correct `instagram_user_id` (not `profile_id`) — currently still reads profile_id in `distribution_service.py:443`
- [ ] File: `backend/routers/desktop_oauth.py`

### P2-3: Fix Facebook Publishing (GAP 4)
**Status:** [ ] Not Started
**Effort:** 0.5 day
- [ ] Auto-populate `page_id` from OAuth token (no population currently in `desktop_oauth.py`)
- [ ] Or add page selection step in connection flow

### P2-4: Distribution UI (GAP 5)
**Status:** [ ] Not Started
**Effort:** 1 day
- [ ] New frontend route `/distribution` (no route exists yet)
- [ ] List distribution channels, manual publish button
- [ ] Publish history view
- [ ] Backend API already exists: `POST /api/v1/distribution/publish`

### P2-5: Add 15 Social Media Agents
**Status:** [~] 12/15 DONE (folder: `agent-library/social-engagement/`)
**Effort:** 0.2 day remaining

**Already present:** social-media-responder, sentiment-analyzer, triage-agent, brand-voice-guardian, troll-detector, lead-qualifier, faq-auto-responder, engagement-strategist, content-repurposer, crisis-monitor, competitor-watcher, hashtag-optimizer

**Missing (add these):**
- [ ] `thread-composer.md`
- [ ] `dm-closer.md`
- [ ] `community-manager.md`

### P2-6: Pre-built Crew Templates
**Status:** [ ] Not Started (only a frontend helper exists at `frontend/src/lib/crews/marketing-crew-template.ts` — no DB seeding)
**Effort:** 0.5 day
- [ ] Seed 4 crew templates on startup (like agent seeding)
- [ ] Auto-Reply Crew (3 agents, sequential)
- [ ] Sales DM Crew (3 agents, sequential)
- [ ] Content Distribution Crew (2 agents, sequential)
- [ ] Crisis Response Crew (3 agents, sequential)

---

## BACKLOG — Post-Launch

### BL-2: Coding Agents (Agent Library)
**Status:** [ ] Not Started
**Effort:** 1 day
- [ ] Code Reviewer, Bug Analyzer, Test Writer, Doc Generator, Refactoring Advisor
- [ ] Crew template: Code Review Crew (sequential)

### BL-3: Scheduled Crews (Cron-style)
**Status:** [ ] Not Started
**Effort:** 2-3 days
- [ ] `crew_scheduler_service.py` with APScheduler
- [ ] UI: cron picker in crew config
- [ ] "Run this crew every morning at 9am"

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

**Total models in catalog:** 37 (6 families: Qwen 2.5, Qwen 3, Qwen 3.5, Gemma, Llama, Mistral, Phi, DeepSeek)
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
1. Merge `feat/crew-channel-wiring` → main + cut `v1.0.0-beta.4` (8 commits unreleased)
2. P2.5-1 Reddit Connection
3. P2.5-2 Knowledge Base (RAG) — reuse existing `embedding_service.py`
4. Phase 2 remainder: Twitter inbound poller, IG/FB publishing fixes, Distribution UI, 3 missing social agents, crew template seeding
5. Phase 3 Launch

---

*This document is excluded from git. For internal planning only.*
