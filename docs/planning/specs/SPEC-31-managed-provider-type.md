# SPEC-31 — Managed Provider Type + "Connect to Your Organization" Card

- **Links:** Enterprise Desktop track (Enterprise SPEC-46/47/48) · evaluation of 2026-08-12
- **Priority:** P1 · **Effort:** S
- **Review status:** ⬜ pending review
- **Prereqs:** none (this is the P1 demo spec; SPEC-01/02 are prereqs for SPEC-32, not for this)

## 1. Goal

Make the already-proven gateway connection presentable: a dedicated `contextuai_managed` provider type (so the org gateway can never collide with a user's own `openai_compat` endpoint) and a "Connect to your organization" settings card that replaces the raw base-URL form for this use. Smoke test 2026-08-12 proved the pipe with zero code changes — Enterprise `/v1` + `ctx_` key pasted as `openai_compat` streamed chat and auto-discovered all 13 org models; it also **overwrote the user's existing `openai_compat` row** (created 2026-06-30), which is the bug this spec exists to prevent.

## 2. Context (verify before coding)

- `backend/services/cloud_provider_service.py:79` (and repository `get_by_type`): **upsert one row per `provider_type`** — the collision.
- `backend/models/cloud_provider_models.py:22-29`: `CloudProviderType` enum; `:84-105` `CloudProviderCreate` validation (`openai_compat` requires `base_url`).
- `backend/services/cloud_provider_service.py:218/:272-296`: `_probe_openai(cfg, require_key=False)` reused for compat probing — reuse for the new type.
- `backend/services/cloud_model_seeder.py:88/:286-330`: dynamic model discovery from the server's `/v1/models`, rows prefixed `openai_compat:<id>`; save triggers reseed (`cloud_provider_service.py:108-111`).
- `backend/services/model_dispatcher.py:181-187`: `openai_compat` dispatch branch; `:294` `stream_chat` entry.
- Frontend: `src/data/provider-guides.ts:164` (compat form def), `src/routes/settings.tsx` AI Providers tab (save/test `:292-340`).

## 3. Plan

1. **New enum value `contextuai_managed`** in `CloudProviderType`; validation identical to `openai_compat` (`base_url` required, `api_key` required — the gateway always needs a key). Dispatch, probe, and seeding all route through the existing `openai_compat` code paths (thin mapping, no logic fork); seeded model ids prefixed `contextuai_managed:<id>`.
2. **Own row**: because it is its own `provider_type`, the one-row-per-type upsert now *protects* it — a user's personal compat endpoint and the org gateway coexist. Add a regression test proving both rows survive a save of each.
3. **Settings card** "Connect to your organization" on the AI Providers tab, above the generic providers: fields = server URL + access key (v1 manual paste; SPEC-32 replaces the key paste with SSO enrollment and keeps this card as its surface). On save: normalize URL (append `/v1` if missing), probe, seed, show discovered-model count. If the server exposes `GET /api/v1/desktop/config` (Enterprise SPEC-47), display the org/deployment name on the card — silently skip if 404 (older servers).
4. **Model picker labeling**: discovered models grouped under the org's name (fallback "Your organization") instead of "OpenAI-compatible".
5. **Disconnect**: deleting the provider removes its seeded rows (existing `_sync_cloud_models_safe` delete path) — verify and test.

## 4. Acceptance criteria

- Registering the org gateway never touches an existing `openai_compat` row, and vice versa (regression test).
- Fresh install → paste URL + key → org models appear grouped under the org name → chat streams through the gateway (manual smoke on the packaged app).
- Bad URL/key shows the probe error on the card, saves nothing.
- `GET /desktop/config` present → org name on the card; absent → card still fully functional.

## 5. Decision needed

- Card copy for the key field in v1 ("access key from your administrator"?) — cosmetic, decide in review.

## 6. Out of scope

SSO/enrollment, keychain storage, policy (SPEC-32); build variants (SPEC-33); tool-calling on the compat path.

## 7. Test plan

- Backend: enum round-trip, validation, coexistence-of-rows regression, seeding prefix, delete-cleans-models.
- Manual: packaged-app smoke against a live Enterprise stack (the 2026-08-12 smoke-test checklist, now through the UI).
