# SPEC-14 — Unified Memory Layer ("Solo Remembers")

- **Links:** ROADMAP F-1 (Q3 2026 flagship) · trend vector #2 (memory)
- **Priority:** P0 (roadmap) · **Effort:** L
- **Review status:** ⬜ pending review
- **Type:** roadmap spec (directional — implementing agent drafts a detailed design doc for review before coding)

## 1. Goal

Solo builds persistent, structured, user-visible memory from everything that flows through it — chats, crew runs, channel traffic — so agents stop being goldfish. The user can see, edit, delete, and export every memory. Local-first memory is the privacy moat cloud assistants can't copy.

## 2. v1 Scope

1. **Memory store** — new collections: `memory_facts` (atomic facts: "pricing is $49/mo", "client X prefers email", subject/predicate/value + source ref + confidence + timestamps), `memory_episodes` (summaries of notable sessions/runs). Embeddings via the bundled MiniLM model; store mirrors the kb_chunks pattern (JSON arrays in SQLite).
2. **Extraction** — post-session and post-crew-run background job: a small local model (or the session's model) extracts candidate facts with confidence; dedupe against existing facts (embedding similarity + subject match); low-confidence candidates go to a "review" state instead of auto-saving.
3. **Recall** — at prompt-build time (chat + `agent_runner`), retrieve top-k relevant facts (embedding + recency/confidence weighting) and prepend a compact "What I know" block, clearly separated from KB citations.
4. **Memory panel UI** — new route `/memory`: searchable list, edit/delete/pin, per-fact source link ("learned from chat on Jun 3"), review queue for low-confidence candidates, global on/off switch and per-scope toggles (chat / crews / channels), full JSON export.
5. **Scoping** — memory is global (one user) in v1, but every fact carries a `scope` field (`global` | `crew:<id>` | future `worker:<id>`) so Digital Workers (SPEC-18) can have private memory later. Existing `crew_memory_service` migrates in or federates — implementing agent proposes which.

## 3. Architecture sketch

`services/memory_service.py` (extract/dedupe/recall) + `repositories/memory_repository.py` + `routers/memory.py` + extraction job hooked where sessions close and crew runs finish. Extraction must be cancellable and never block the chat path (queue + background task, like the personal-docs jobs).

## 4. Enterprise port (one quarter later)

Per-user + per-team memory in Mongo; admin policy on what categories may be remembered (PII rules); retention windows; org "institutional memory" rollups. Governance events (SPEC-24) emitted on every memory write from day one.

## 5. Acceptance criteria (v1)

- Tell Solo a fact in chat; two sessions later, a different agent uses it correctly and the fact is visible in `/memory` with the source link.
- Deleting a fact removes it from all future recalls. Kill switch empties the prompt block entirely.
- Extraction adds < 0 ms to perceived chat latency (fully async) and works with local-only models.
- Memory off by default for channel traffic (privacy posture), on for chat/crews — confirm with reviewer.

## 6. Open questions

- Extraction model: always a small dedicated model (cheap, consistent) or the session model (better quality, variable cost)?
- Fact TTLs / aging: decay confidence over time, or keep until edited?
- Should facts be injected as system-prompt text (simple) or exposed as a recall tool the model calls (cleaner, needs tool-capable models)?
