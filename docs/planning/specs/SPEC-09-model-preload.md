# SPEC-09 — Model Preload & Warmup

- **Links:** GAPS PROD-2 · FEATURES A1
- **Priority:** P2 · **Effort:** S–M
- **Review status:** ⬜ pending review
- **Open decisions for reviewer:** auto-preload last-used model on app start? (proposed: yes, behind a Settings toggle, default ON when system RAM ≥ 16 GB)

## 1. Goal

First message to a local model doesn't feel like a hang. Users can warm a model explicitly and see load state everywhere models are picked.

## 2. Context (verify before coding)

- `backend/services/local_model_service.py`: singleton holding one loaded Llama instance (`_ensure_model`, `unload_model`, `_inference_lock`, idle tracking via `get_status()`).
- `GET /api/v1/local-models/loaded` already exposes loaded state (`routers/local_models.py:206-211`).
- Models page: `frontend/src/routes/models.tsx`; chat model dropdown lives in the chat route/components (find the picker; it pulls from the models collection / `/v1/models`).
- REL-8 (double-finalize in `unload_model`, n_ctx not persisted) lives in the same file — fix opportunistically here.

## 3. Plan

1. **Endpoint:** `POST /api/v1/local-models/{model_id}/preload` → resolves path via `model_manager.get_model_path`, calls `local_model_service` load in a thread, returns when loaded (or streams `loading/done/error` via SSE if load > a few seconds — preferred, reuse the download SSE pattern). Add `POST /api/v1/local-models/unload`.
2. **Keep it one warm model** (matches current memory model; LRU-of-2 explicitly rejected for v1 — 8–16 GB machines).
3. **UI — Models page (installed tab):** per-model "Load"/"Loaded ●"/"Unload" affordance + load time estimate (`size_gb / ~1.5 GB/s` disk read heuristic is fine; label it an estimate).
4. **UI — chat dropdown:** show `● Ready` next to the loaded local model (poll `/loaded` or include in models list response).
5. **Auto-preload (if approved):** on backend startup, after seeding, load the last-used local model (persist `last_used_local_model` in a settings/kv collection on each chat) when RAM allows; never block startup on it.
6. **REL-8 fold-in:** in `unload_model`, call `.close()` only (drop the explicit `__del__`), and persist per-model `n_ctx` override if one was applied so reloads keep it.

## 4. Acceptance criteria

- Preload endpoint loads the model; subsequent first chat token latency drops to near warm-path (manual check).
- Loaded badge appears in Models page + chat dropdown and updates after unload.
- Preloading model B while A is loaded swaps cleanly (A unloaded, no crash, memory released — observe RSS roughly).
- Suite green.

## 5. Out of scope

Multi-model concurrency, GPU offload tuning, RAM-pressure eviction.
