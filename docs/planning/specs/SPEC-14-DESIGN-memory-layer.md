# SPEC-14 — Unified Memory Layer · Detailed Design (for review before coding)

- **Parent spec:** `SPEC-14-unified-memory-layer.md` (roadmap F-1, Q3 2026 flagship)
- **Status:** ✅ reviewed 2026-07-08 — decisions confirmed (all 5 recommendations accepted). Building PR-A.
- **Author:** implementing agent, grounded in a code map of `crew_memory_service`, `rag_service`/`embedding_service`, and the `personal_docs` job pattern.

---

## 1. What we're building (one paragraph)

A local, structured, user-visible memory that Solo builds automatically from chats and crew runs. Atomic **facts** ("pricing is $49/mo", "client X prefers email") and session **episodes** are extracted in the background, embedded with the bundled MiniLM model, and stored as JSON rows in SQLite — mirroring the KB/RAG pattern exactly. At prompt-build time we retrieve the top-k relevant facts and prepend a compact **"What I know"** block, clearly separated from KB citations. A new `/memory` route lets the user search, edit, pin, delete, review low-confidence candidates, toggle scopes, and export everything. Nothing leaves the machine.

## 2. How it reuses what already exists (no new infra)

The three research passes confirm the memory layer is a **copy of patterns already in the repo** — no new dependencies, no ANN index, no migration framework, no schema files (tables auto-create on first write via the SQLite adapter).

| Concern | Existing template we copy | Where |
|---|---|---|
| Embedding | `embedding_service.embed()/embed_batch()` — 384-dim, L2-normalized singleton | `services/embedding_service.py` |
| Vector store + retrieval | inline `"embedding": list[float]` in the doc; `embeddings @ q`; `argsort(-scores)[:k]` | `services/rag_service.py` |
| Repository | thin `BaseRepository` subclass, hard-coded collection name, auto-created table | `repositories/chunk_repository.py` |
| Background job | `asyncio.create_task` + `self._tasks` dict + DB `cancel_requested` flag polled between units | `services/personal_docs_service.py` |
| Job states + SSE | `queued→running→done/error/cancelled`, DB-poll SSE generator | `index_job_repository.py`, `routers/personal_docs.py` |
| Router + DI | `Depends(get_database)` factory functions; register in `app.py` | `routers/knowledge_base.py` |

## 3. Data model

Two new collections (tables auto-create on first write):

**`memory_facts`**
```
_id            str (uuid4)
scope          "global" | "crew:<id>"        # forward-compat for worker:<id> (SPEC-18)
subject        str        # "pricing", "client Acme", "the user"
predicate      str        # "is", "prefers", "decided"
value          str        # "$49/mo", "email over calls"
text           str        # canonical rendered sentence — what we embed & show
embedding      list[float]  # 384-dim, inline JSON array (kb_chunks pattern)
confidence     float 0..1
status         "active" | "review"           # < threshold → review queue, not auto-recalled
pinned         bool                          # user-pinned facts always eligible for recall
source_kind    "chat" | "crew"
source_id      str        # session_id or crew_run/execution id
source_label   str        # "chat on Jul 3", "Sales crew run"
origin         "extracted" | "user"          # user-added facts skip extraction/dedupe
created_at, updated_at, last_used_at   ISO strings
```

**`memory_episodes`** — same envelope, but `text` is a 1–3 sentence summary of a notable session/run, `subject/predicate/value` omitted. Used for "remind me what that Reddit thread was about" style recall. **Phaseable** (see §8).

**Extraction job** (`memory_jobs`, copy of `kb_index_jobs`): `_id, source_kind, source_id, status, cand_total/saved/review/deduped, error, cancel_requested, started_at, finished_at`.

## 4. The three flows

### 4a. Extraction (background, never blocks chat)
- **Chat hook:** after the assistant reply is stored (`ai_chat.py` — after each `update_session_stats`, all five model paths). Enqueue a **debounced** job keyed on `session_id`: if a job is already running/queued for that session, skip — coalesce so at most one extraction per session is in flight. Plus a final flush on `archive_session`/`delete_session`.
- **Crew hook:** `orchestrator.py::finalize_execution` success branch (~line 745), keyed on `execution_id`.
- **The job:** pull the recent transcript → ask the extraction model for candidate facts as JSON (`subject/predicate/value/confidence`) → embed each `text` → **dedupe** (cosine ≥ 0.92 against existing same-`subject` facts → update/skip; else insert) → below the confidence threshold → `status="review"`. Cancellable via the `cancel_requested` flag polled between candidates. Adds **0 ms** to perceived chat latency.

### 4b. Recall (at prompt-build)
- **Chat:** `ai_chat.py:282–306`, right where KB context is built. Embed the user prompt, load candidate facts for `scope in {global}` (+ crew scope in crew path), score `cosine·w₁ + confidence·w₂ + recency·w₃`, take top-k active/pinned, render a `## What I know` block, prepend to `effective_prompt` (separate from and above KB citations). Bump `last_used_at` on recalled facts.
- **Crew:** `agent_runner.py:244–254`, mirroring the KB prepend into `system_prompt` (scope = `global` + `crew:<id>`).
- **Kill switch / scope-off** ⇒ the block is empty; recall is skipped entirely.

### 4c. Memory panel (`/memory`)
Searchable list (semantic + text), edit/delete/pin, per-fact **source link** ("learned from chat on Jul 3"), a **review queue** for low-confidence candidates (approve → active, reject → delete), global on/off + per-scope toggles (chat / crews / channels), and **full JSON export**. New route + sidebar entry; `lib/api/memory-client.ts`; components mirror the KB page.

## 5. Files (all additive)

**Backend:** `models/memory_models.py`, `repositories/memory_repository.py` (+ `memory_episode_repository.py`, `memory_job_repository.py`), `services/memory_service.py` (extract/dedupe/recall/CRUD), `routers/memory.py`; hooks edited in `ai_chat.py`, `chat_sessions.py`, `workspace/orchestrator.py`, `workspace/agent_runner.py`; register router + startup orphan-reset in `app.py`. Tests mirror `test_knowledge_base.py` / `test_personal_docs_service.py`.
**Frontend:** `routes/memory.tsx`, `lib/api/memory-client.ts`, `components/memory/*`, sidebar entry, Settings → Memory toggles.

## 6. Recommended calls on the open questions

| # | Question | Recommendation | Why |
|---|---|---|---|
| Q1 | Extraction model | **Reuse the session/run's own model** (Settings override to force a small dedicated one) | Local model stays RAM-resident; a *different* model forces a costly reload/swap every extraction. Reusing the loaded model = zero swap, consistent quality. Cloud sessions reuse their own cheap model. |
| Q2 | Fact aging / TTL | **Keep until edited/deleted; no auto-decay.** Use `last_used_at`/recency only as a *ranking* signal | Surprising auto-deletions erode the "visible memory = trust" moat. Aging can rank stale facts down without removing them. |
| Q3 | Injection mechanism | **System-prompt text block in v1** (recall-as-tool deferred) | Must work with local non-tool-capable models; SPEC-29 exists precisely because local tool-calling is unreliable. Tool-based recall is a v2/enterprise option. |
| Q4 | Crew memory (migrate vs federate) | **Federate in v1** — leave `crew_memory_service` in place; new layer owns global + semantic facts and can also read crew-scoped facts | `crew_memories` is a shipped, battle-tested, self-contained plain-text store with its own orchestrator injection. Migrating risks regressing a live path for no v1 user benefit. Consolidate in the enterprise port. |
| Q5 | Channel traffic default | **Off by default** for channels; on for chat + crews | Privacy posture (spec §5). User can opt channels in per-scope. |

## 7. Acceptance criteria (from spec §5)

- Tell Solo a fact in chat; two sessions later a different agent uses it, and it's visible in `/memory` with a source link.
- Deleting a fact removes it from all future recalls; kill switch empties the block.
- Extraction is fully async — no added perceived chat latency — and works local-only.
- Channel memory off by default; chat/crews on.

## 8. Suggested build phasing (each independently shippable behind additive changes)

1. **PR-A — Store + panel + manual facts.** Models, repos, `memory_service` CRUD, `routers/memory.py`, `/memory` UI, export, kill switch. User can add/see/edit/delete facts manually. *No extraction yet — safe, visible, testable.*
2. **PR-B — Recall.** Wire the "What I know" block into chat + crew prompt-build. Now manual facts influence answers.
3. **PR-C — Extraction (facts).** Background job on chat + crew hooks, dedupe, review queue.
4. **PR-D — Episodes** (optional / can fold into a later release).

Phasing lets you review the moat-critical, low-risk pieces (visible store + user control) before the higher-variance extraction lands.
