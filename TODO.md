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

## PHASE 3: UNIFY CONNECTIONS + CREWS (IA Refactor) ⭐ HIGH PRIORITY
**Status:** [ ] NOT STARTED
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
3. **Distribution & Schedule stay in the sidebar** but route to a shared **"Coming Soon"** page. Sidebar remains at 12 items; nav E2E test (`frontend/tests/e2e/navigation/navigation.spec.ts`) does not need changing. Future phase removes them entirely.
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
- [ ] `backend/services/connection_service.py` — unified aggregator over existing stores. Exposes:
  - `list_connections() -> [ConnectionSummary]`
  - `get_capabilities(conn_id) -> {inbound, outbound}`
  - `set_capability(conn_id, direction, enabled)`
- [ ] `backend/services/inbound_router.py` — on inbound message:
  1. Find crews with reactive trigger on this connection.
  2. Keyword/hashtag/mention substring match.
  3. If >1 match, call an LLM (cheap model — Haiku or local Gemma) to pick best match.
  4. Dispatch the chosen crew via existing agent_runner.
  - Initially: thin wrapper over existing `channel_service.handle_message`; layer matching logic on top to avoid regression.
- [ ] `backend/services/scheduled_runner.py` — polls crews for `triggers[type=scheduled]`, fires at cron/run_at boundaries. **Replaces** the internals of the standalone scheduler — but the standalone Schedule page still shows Coming Soon.
- [ ] `backend/routers/connections.py` (new aggregator):
  - `GET /api/v1/connections` — unified list
  - `PATCH /api/v1/connections/{id}/capabilities` — toggle inbound/outbound
  - Existing per-platform credential endpoints (OAuth/token paste/Reddit) remain unchanged.

**Modified files**
- [ ] `backend/services/workspace/agent_runner.py` — after crew run completes, if any `connection_binding` has outbound enabled, publish the final agent output via the corresponding adapter. No more separate `distribution_service`. If `crew.approval_required`, create an approval record instead of sending directly.
- [ ] `backend/services/crew_service.py` — add trigger + approval fields; validate trigger configs.
- [ ] `backend/models/crew_models.py` — Pydantic additions for `connection_bindings`, `triggers`, `approval_required`.

**Deprecated (do NOT delete yet — user asked to keep Coming Soon)**
- `backend/routers/distribution.py` — leave wired but return `{status: "coming_soon"}` stub on routes called by the deprecated frontend page. Or mark the router unused once frontend stops calling it.
- `backend/services/distribution_service.py` — logic folded into agent_runner's outbound publishing. File can stay for the outbound adapters it owns (LinkedIn/Twitter/IG/FB/Blog/Email/Slack publishers) — reuse them from connection_service / agent_runner.
- Standalone scheduler service (if any — check `backend/routers/triggers.py` and `backend/services/` for cron impl) — disable once `scheduled_runner.py` handles crew-level scheduling. Keep code around until the Schedule page is retired.

### Frontend work

**Rewrite**
- [ ] `frontend/src/routes/connections.tsx` — one grid with all 10 types:
  - 7 socials: Telegram, Discord, Reddit, LinkedIn, Twitter/X, Instagram, Facebook
  - 3 new outbound-only: Blog, Email, Slack webhook
  - Each card: auth status, **Inbound toggle** (hidden for outbound-only types), **Outbound toggle**, Manage/Disconnect.
- [ ] `frontend/src/components/crews/crew-builder.tsx` — revise the 5-step wizard:
  - **Step 4 "Connections"** → **Connections & Directions**: pick connections, per-connection direction chip selector (`Inbound` / `Outbound` / `Both`). If user picks a direction that's disabled at the connection level, show inline modal:
    > "Outbound is disabled on Telegram. Enable it now so this crew can send?"
    > [Enable & continue] [Cancel]
  - **New Step 5 "Trigger"**: Reactive (+ `keywords`, `hashtags`, `mentions` multi-input) and/or Scheduled (cron field + one-shot date-picker). Both can be enabled; manual is implicit.
  - **New Step 6 "Approval"**: single toggle "Review outbound before sending."
  - Existing Review step becomes Step 7 — update summary to reflect new fields.

**New**
- [ ] `frontend/src/routes/coming-soon.tsx` — simple placeholder component:
  - Takes a `feature: string` prop.
  - Shows icon + "<Feature> is moving into Crews — coming soon" + link to Crews page + link to docs/TODO.md entry.
- [ ] Update `App.tsx` to route `/distribution` and `/schedule` to `ComingSoon` with the appropriate prop.

**Modified**
- [ ] `frontend/src/routes/crews.tsx` — **Crews tab**: add new filter chips alongside existing `statusFilter` and `modeFilter`: `Inbound`, `Outbound`, `Scheduled`, `Reactive`, `Approval-required`. Filter logic hooks into `filteredCrews` (line 179). **Runs tab**: render `trigger_type` badge on each row of `RunsList` (line 498).
- [ ] `frontend/src/lib/api/crews-client.ts` — extend `CrewRun` type with `trigger_type`, `trigger_source`.
- [ ] `frontend/src/lib/api/distribution-client.ts` — can stay but is no longer consumed by the active UI. Delete in the future-cleanup phase.

**Not changed**
- Sidebar (`frontend/src/components/navigation/desktop-sidebar.tsx`) — still 12 items.
- Nav E2E tests — still expect 12.

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
| 4 | Swap `/distribution` and `/schedule` routes to ComingSoon. Add TODO entries referencing this plan. Flip `UNIFIED_CREWS` on by default. | Flag default → true |

### Follow-up TODOs (track after Phase 3 ships)

- [ ] FUTURE: Re-retire Distribution page (delete `frontend/src/routes/distribution.tsx`, `backend/routers/distribution.py`, `backend/services/distribution_service.py` entirely) once Coming Soon has been live one release cycle.
- [ ] FUTURE: Re-retire Schedule page (delete `frontend/src/routes/schedule.tsx` + standalone scheduler backend).
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

*This document is excluded from git. For internal planning only.*
