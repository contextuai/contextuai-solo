# SPEC-08 — HuggingFace Token Setting for Model Hub

- **Links:** GAPS PROD-1, REL-7 · FEATURES A7
- **Priority:** P1 (S effort) · **Review status:** ⬜ pending review
- **Depends on:** branch `fix/model-hub-downloads` being merged (the downloader this configures).

## 1. Goal

Users can paste a (free) HuggingFace token in Settings so Model Hub downloads stop failing with anonymous 429 rate limits, and gated custom repos become downloadable. No env vars required.

## 2. Context

- `backend/services/model_manager.py` `_download_files` already reads `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` env vars and sends `Authorization: Bearer`.
- Settings → AI Providers tab renders provider cards from `components/cloud-providers/` + `data/provider-guides.ts`; keys go to the `cloud_provider_keys` collection via `routers/cloud_providers.py` / `services/cloud_provider_service.py`.
- HuggingFace is *not* an inference provider here — don't seed models for it (`cloud_model_seeder` must skip it).

## 3. Plan

1. **Storage:** add provider id `huggingface` to the cloud-provider key store (reuse existing CRUD; ensure `cloud_model_seeder.py` ignores it; if SPEC-02 lands first, it's encrypted for free).
2. **Backend use:** in `ModelManager._download_files`, resolve token as: stored `huggingface` key → else env vars. `model_manager` is a module singleton without DB access — fetch the token in `routers/local_models.py` (async, has `get_database`) and pass it as a parameter through `download_model`/`download_custom` → `_run_and_stream` → `_download_files`.
3. **Test-connection:** "Test" button calls `GET https://huggingface.co/api/whoami-v2` with the token; 200 → show username.
4. **UI:** a provider card "HuggingFace (model downloads)" in Settings → AI Providers with paste-key + test, copy matching the others; guide text: "Free account token. Fixes rate-limit (429) errors and enables gated models."
5. **Error-message tie-in:** the 401/403 and 429 friendly errors in `model_manager._friendly_http_error` currently say "set the HF_TOKEN environment variable" — change to "add a HuggingFace token in Settings → AI Providers".
6. **REL-7 fold-in:** pin `huggingface-hub` in `requirements.txt` to the version in the venv (`==1.8.0`) — it's still imported elsewhere; downloads no longer depend on it but source installs shouldn't drift majors silently.

## 4. Acceptance criteria

- Token saved in Settings → downloads send the Authorization header (assert via a unit test on `_download_files` with a mock session/httpserver).
- Without a token everything still works as today.
- Test button validates a real token shape (mock whoami in tests).
- Catalog/model tests still pass (`pytest -k "model or catalog or download"`).

## 5. Out of scope

Per-download token prompts; OAuth device flow; surfacing gated-repo license acceptance in-app.

---

## Addendum (2026-06-17) — BYOK data classes / privacy router

> Added from MARKET-PAINS-2026 **P-7** (capability-gap honesty + hybrid). Distinct from the HF-token work above but lives here because it's the same "user-supplied cloud credential" surface (`cloud_provider_keys`, `model_dispatcher`). Could be split into its own SPEC if it grows — flag for review.

### Why

Users expect a local 8B to match Claude/GPT, feel let down, and the mature answer is hybrid: local for private/repetitive, cloud for hard reasoning. The risk is that turning on BYOK silently sends private content (KB docs, memory, personal files) to a cloud provider — which destroys the privacy promise the whole product rests on. The fix is to make "private by default, frontier when *you* choose" a *structural* guarantee, not a hope.

### Scope

1. **Data classes.** Tag content with a sensitivity class: `local-only` (KB chunks, SPEC-14 memory, personal-docs folder content) vs `routine` (a normal chat prompt the user typed). Tagging happens where content enters a prompt (KB citation injection in `ai_chat.py` / `agent_runner.py`; memory recall).
2. **Router enforcement.** In `model_dispatcher`, when a request targets a cloud provider (`anthropic:`/`openai:`/`google:`/`bedrock:`) and the assembled prompt contains `local-only` content, **block or strip** it by policy — never silently send it. Local model targets are unrestricted.
3. **User control + honesty.** A clear setting: "Allow my private documents/memory to be sent to cloud models? (default: No)." When off and a user asks a cloud model a question that needs local-only context, surface the choice explicitly ("this needs your private docs — keep it local, or allow this one to go to <provider>?") rather than degrading silently.
4. **Ties to SPEC-28.** The egress monitor shows when local-only data was (with consent) sent to a provider; the airplane lock overrides everything.

### Acceptance criteria (addendum)

- With the default (private stays local), a cloud-model chat that pulls KB context does **not** transmit KB chunk text to the provider — asserted by a test inspecting the outbound payload via the SPEC-28 net-guard.
- Flipping the allow-toggle permits it, and the action is logged (SPEC-24 ledger + SPEC-28 panel).
- Local-model paths are unchanged.

### Open question

Block-vs-strip when local-only content is present and consent is off: hard-block the request with an explanation, or strip the sensitive context and proceed degraded? (Proposed: ask once, inline, then remember per-conversation — never silently strip or silently send.)
