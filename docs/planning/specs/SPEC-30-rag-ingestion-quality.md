# SPEC-30 — RAG Ingestion Quality (Chunking / Cleaning / Diagnostics)

- **Links:** MARKET-PAINS-2026 P-4 · extends SPEC-11 (KB staleness) · relates to SPEC-23 (evals) · code: `services/rag_service.py`, `routers/knowledge_base.py`, `services/personal_docs_service.py`
- **Priority:** P1 · **Effort:** M
- **Review status:** ⬜ pending review
- **Type:** gap-driven product spec (community pain research) — upgrades an existing feature
- **Why ours is different:** "chat with my docs" is the recurring dream use case *and* the recurring disappointment. The fix is ingestion, not a bigger model — and we control the whole pipeline, so we can make messy real-world docs work without the user building a loader or tuning chunkers (the exact thing the DIY local-RAG crowd hates).

## 1. Problem

RAG demos work; pointed at a user's own messy files it collapses. Headers, footers, nav crumbs and table debris pollute the embedding space; naive fixed-size chunking glues half-sentences to figure captions; top-1 hit rate drops to 52-63%. The measured wins are lopsided: **chunking ≈ +35%, embedding choice ≈ +27%, swapping the LLM ≈ +6%.** Users blame "the AI," but Solo's current pipeline is exactly the naive case: ~500-token fixed chunks / 50 overlap, MiniLM-L6 embeddings, numpy dot-product, **no MMR**. The disappointment is invisible-until-checked, so users churn quietly.

## 2. v1 Scope

1. **Boilerplate stripping.** Before chunking, remove repeated headers/footers/page numbers/nav crumbs (detect lines that repeat across many pages/files) and normalize whitespace/table debris. Biggest cheap win for the cosine-pollution problem.
2. **Structure-aware chunking.** Replace blind fixed-size splitting with structure-respecting splits: break on headings/paragraphs/sentences, keep tables and list items intact, never sever a sentence mid-way. Keep a token ceiling but make boundaries semantic. Preserve existing page-tracking for citations.
3. **MMR retrieval.** Add maximal-marginal-relevance re-ranking on top of the dot-product top-k so results are relevant *and* diverse (kills near-duplicate chunk spam). CLAUDE.md already flags "top-k MMR not yet implemented" — this closes it.
4. **Retrieval inspector ("show me what was retrieved").** In the KB "Test Query" tab, show the actual chunks returned for a query with scores + source + page, so the user (and we) can *see* why an answer was good or bad. This converts invisible failure into visible, fixable signal — the single most valuable debugging affordance for RAG.
5. **Better-embeddings option (optional, gated).** Allow a larger/better embedding model than MiniLM-L6 as an opt-in for users who want quality over footprint (re-index required). Keep MiniLM as the zero-config default. Coordinate with SPEC-27 (it's a downloadable model with its own hardware cost).

## 3. Architecture sketch

- **Pipeline seam:** the chunk→embed→store path lives in `services/rag_service.py` and is shared by document upload (`routers/knowledge_base.py`) and folder mappings (`services/personal_docs_service.py`). Insert cleaning + structure-aware chunking *before* embedding so both ingestion routes benefit. Keep chunk schema backward-compatible (page, source, offsets).
- **Re-index path:** changing chunking/embeddings invalidates existing vectors. Provide a per-KB "re-index" action (reuse the `kb_index_jobs` progress plumbing from personal docs) and version the chunking config on each KB so we know what's stale. Don't silently mix old/new chunks.
- **MMR:** pure post-processing on retrieved candidates in the query path — cheap, no storage change. Add a `lambda` (relevance vs diversity) with a sane default.
- **Inspector:** the query endpoint already returns chunks; surface them in the existing Test Query UI with scores. Minimal backend change.
- **Evals tie-in:** expose a small retrieval-quality check (hit-rate on a labelled mini-set) so SPEC-23 can regression-test ingestion changes — and so we can *prove* the +35% rather than assert it.

## 4. Enterprise port

Same pipeline, larger corpora; ingestion quality + the retrieval inspector become a support/QA tool ("why didn't the bot find this doc"). Embedding-model choice maps to a per-workspace policy.

## 5. Acceptance criteria

- On a deliberately messy test corpus (PDFs with running headers/footers, a doc with tables), boilerplate no longer appears in retrieved chunks, and no retrieved chunk starts/ends mid-sentence.
- MMR measurably reduces near-duplicate chunks in top-k vs. the current pipeline on a sample query (assert via a diversity check in tests).
- Retrieval inspector shows, for a given query, the exact chunks + scores + source/page returned.
- A measured hit-rate improvement on a small labelled set vs. the current naive pipeline (record the number; target a meaningful jump, not a specific magic figure).
- Re-index is explicit, shows progress, and never mixes chunking-config versions within one KB.
- Existing citations (`[1]`, `[2]`) still resolve to correct source+page.

## 6. Out of scope (v1)

Hybrid keyword+vector (BM25) search; query rewriting/HyDE; cross-encoder reranking; multi-modal (image) ingestion. Note them as v2 candidates — v1 is "stop polluting the index and let the user see retrieval," which captures most of the measured gain.

## 7. Open questions

- Default embedding model: keep MiniLM-L6 for zero-config and offer an upgrade, vs. bump the default (re-index cost for existing users). Proposed: keep default, offer opt-in.
- Boilerplate detection heuristic (repeated-line frequency) vs. a library — start heuristic, measure, only add a dep if it clearly wins.
- Auto-reindex on upgrade vs. prompt the user. Proposed: prompt (re-indexing a large folder mapping is expensive and should be consented to — consistent with the personal-docs friction threshold).
