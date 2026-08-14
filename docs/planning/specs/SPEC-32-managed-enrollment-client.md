# SPEC-32 — Managed Enrollment Client (SSO, Device Key, Policy)

- **Links:** Enterprise SPEC-46 (device scope) · SPEC-47 (enrollment + policy) · SPEC-48 (model mirror + local-usage) · Solo SPEC-31
- **Priority:** P1 (gated: starts only after a written customer ask — the evaluation's demand gate — and after Enterprise SPEC-46/47 merge)
- **Effort:** L
- **Review status:** ⬜ pending review
- **Prereqs:** SPEC-01 (sidecar auth token) and SPEC-02 (secrets in OS keychain) — **both are hard prerequisites**: this spec puts an enterprise credential on the laptop, which is indefensible over an unauthenticated sidecar with plaintext SQLite. SPEC-31 (the card this flow upgrades).

## 1. Goal

Turn SPEC-31's paste-a-key card into real enrollment: employee enters the org URL (or MDM provides it) → SSO in the **system browser** (OIDC + PKCE against the org's IdP) → the Enterprise server mints a device-scoped `ctx_` key → key lands in the OS keychain, org policy lands in the sidecar, org models and personas appear. Revocation on the server signs the device out. The employee never sees a key.

## 2. Context (verify before coding)

- Loopback OAuth precedent in this repo: `backend/routers/desktop_oauth.py` (localhost callback listener for social OAuth) — reuse the pattern, not the code path.
- SPEC-02 defines the keychain layer (keyring + Fernet, master key in Windows Credential Manager / macOS Keychain); the device key is stored through it, never in `cloud_providers.config`.
- Enterprise contract (verify against the merged SPEC-47, not this summary): `GET /api/v1/desktop/config` (deployment name, Cognito authority + public client id, enrollment path) · `POST /desktop/enroll` (Cognito access token + `{device_id, hostname, os, app_version}` → device key once + policy + `policy_version`) · `GET /desktop/policy` (ETag) · `POST /desktop/rotate`. Re-enrolling the same `device_id` replaces the key server-side.
- Enterprise SPEC-46 surface (what the device key can reach): `/v1/*`, `POST /api/v1/ai-chat/`, persona listing, own chat sessions/messages, the SPEC-47/48 desktop endpoints. Nothing else — the client must not attempt other routes.
- Persona chat passthrough: sidecar forwards persona-tagged chats to Enterprise `POST /api/v1/ai-chat/` with the device key; **SSE frame format matches ours** (`data: {"chunk": ...}` … `[DONE]`) because Solo inherited it — verify with a captured stream before relying on it.
- Policy knobs (SPEC-47): `local_models`, `server_small_models`, `mcp: managed-only|allowlist|personal-allowed` (+ allowlist), `byok_after_enroll`.
- Model mirror + local-usage (SPEC-48): `GET /desktop/models`, ranged `GET /desktop/models/{id}/download` (sha256 to verify), `POST /desktop/local-usage` (content-free schema).

## 3. Plan

1. **Enrollment flow** (upgrades the SPEC-31 card): fetch `/desktop/config` → open system browser to the IdP authorize URL (PKCE, S256, random state) with loopback redirect (`http://127.0.0.1:<ephemeral>/callback`) → exchange code in the sidecar → `POST /enroll` with device info → store device key via SPEC-02 keychain, store policy + version in SQLite (policy is not a secret). `device_id`: generate a UUID once, persist outside the DB (alongside the keychain entry) so reinstall behavior is deliberate, not accidental.
2. **Managed session state**: enrolled server URL + org display name shown on the card with "Disconnect" (deletes local key + calls nothing — server-side revoke is the admin's) and "Re-enroll". Any 401 from the enrolled server ⇒ signed-out-pending state banner ("Your device's access was revoked or expired — sign in again"), never a retry loop.
3. **Provider wiring**: enrollment writes/updates the `contextuai_managed` provider row (base_url from enrollment; credential = keychain reference, not the key itself) and triggers model seeding as in SPEC-31.
4. **Persona passthrough**: enrolled mode fetches the org persona list (SPEC-46 listing surface) and shows them in the persona picker labeled with the org name; a chat with an org persona routes sidecar → Enterprise `/api/v1/ai-chat` (device key from keychain), re-emitting the SSE stream to the UI. Local personas remain local.
5. **Policy enforcement (client side, honest)**: `local_models: blocked` hides/disables local-model UI while enrolled; `mcp` knob filters which MCP personas are usable (`managed-only` = org registry only; `allowlist` = match patterns; `personal-allowed` = today's behavior); `byok_after_enroll: blocked` disables adding/using personal cloud providers while enrolled. Policy refresh on app start + interval (ETag).
   **Feature-visibility flags (founder decision 2026-08-14 — runtime layer ships here, build-time layer is SPEC-33):** a `features` map in the policy object (crews, blueprints, automations, coder_mode, publishing, workspace) hides those surfaces on an enrolled full-Solo install at runtime — nav + routes gated through one shared flag module that SPEC-33 later evaluates at build time with the same names. This makes an enrolled Solo present the lite experience *before* the lite binary exists (the interim product for non-regulated orgs); it is governance UX, not a security boundary, and the docs must say so.
6. **Model ladder UX**: rung-2 models (server-local tag from `/v1/models` metadata) labeled "runs on your company's server"; local catalog can install from the org mirror when present (ranged download, sha256 verify, resume) instead of HuggingFace.
7. **Local-turn events**: when enrolled and `local_models: allowed`, each local completion posts the SPEC-48 content-free event (fire-and-forget, batched, never blocks the turn, drops silently offline).
8. **Key rotation**: call `/desktop/rotate` when the key's age crosses the server-advertised threshold; on failure fall back to the signed-out-pending state.

## 4. Acceptance criteria

- Fresh app + org URL → SSO in system browser → org models and personas appear; no key or base URL was ever displayed.
- Admin revokes the device in Enterprise Control Center → next request 401s → app shows the signed-out banner within one interaction; local-only features keep working.
- Org persona chat streams through Enterprise; the Enterprise audit trail attributes it to this user + device (asserted against a live stack in E2E).
- `local_models: blocked` policy removes local-model UI on next refresh; mirror-installed model passes sha256; a corrupted download is rejected and re-fetchable.
- The device key never appears in SQLite, logs, or the provider config API response (grep-level assertion in tests).
- Unenrolled behavior (Tiers 1–2, SPEC-31 manual mode) is byte-identical to before this spec.

## 5. Decision needed

- Loopback port strategy (fixed range vs ephemeral) and whether the callback page is a static "return to the app" HTML — decide with a look at `desktop_oauth.py`'s current choice.
- Where `device_id` persists (file next to keychain entry vs registry/plist) — align with Enterprise SPEC-47 Open question 1 naming.

## 6. Out of scope

Lite build target and compile-outs (SPEC-33); tool-calling parity on the compat path (separate spec if standalone MCP demands it); mobile; VDI-specific device identity (Enterprise gap — do not improvise here).

## 7. Test plan

- Backend (sidecar) unit: PKCE exchange, enroll happy/sad paths, 401-state machine, policy gating logic, mirror checksum verify, local-usage schema (content-free — a test asserts prompt text cannot be sent).
- E2E (Playwright, per the founder's UI-driven preference): full enrollment against a live Enterprise dev stack, revoke-from-Control-Center round trip, persona chat stream.
- Manual: packaged Windows build behind a proxy (the corporate-network failure mode the evaluation flagged).
