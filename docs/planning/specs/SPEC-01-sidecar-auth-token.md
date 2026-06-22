# SPEC-01 — Sidecar Auth Token + CORS Lockdown

- **Links:** GAPS SEC-1 · FEATURES B1
- **Priority:** P0 · **Effort:** M
- **Review status:** ⬜ pending review
- **Open decision for reviewer:** what to do with the OpenAI-compat `/v1/*` surface (see §5).

## 1. Goal

Stop arbitrary local processes and drive-by webpages from using the backend at `127.0.0.1:18741`. After this change, every `/api/v1/*` request must carry a per-session shared secret known only to the Tauri shell and the sidecar.

## 2. Context (verify before coding)

- `backend/app.py:69-76`: CORS `allow_origins=["*"]`, no auth middleware. Desktop user is injected via dependency overrides.
- `frontend/src-tauri/src/sidecar.rs`: spawns the sidecar, owns its env.
- `frontend/src-tauri/src/commands.rs`: `api_request` IPC handler proxies HTTP to the sidecar.
- `frontend/src/lib/transport.ts`: IPC for normal requests, **raw fetch for all SSE streams** (`streamRequest`, `getApiBaseUrl`) and `lib/api/local-models-client.ts` `downloadModel`. These fetches originate from the webview origin (`http://tauri.localhost` on Windows, `tauri://localhost` on macOS, `http://localhost:1420` in dev) — they must keep working.

## 3. Plan

1. **Token generation (Rust):** in `sidecar.rs`, generate a 32-byte random hex token at app start. Pass to the sidecar via env var `CONTEXTUAI_SIDECAR_TOKEN`. Store in Tauri state.
2. **Expose to webview:** add IPC command `get_sidecar_token` (like `get_sidecar_port`). The `api_request` IPC handler attaches `Authorization: Bearer <token>` itself.
3. **Backend middleware (`backend/app.py`):** if `CONTEXTUAI_SIDECAR_TOKEN` is set, reject `/api/v1/*` requests without `Authorization: Bearer <token>` with 401. When env var is absent (dev mode `uvicorn --reload`, docker, pytest), middleware is a no-op — zero friction for development and CI.
4. **Frontend fetch paths:** `transport.ts` `streamRequest` + `getApiBaseUrl` consumers and `local-models-client.ts` `downloadModel` add the header (fetch token once via IPC, cache it; dev mode → no header).
5. **CORS:** replace `allow_origins=["*"]` with `["http://tauri.localhost", "tauri://localhost", "http://localhost:1420", "http://127.0.0.1:1420"]`, `allow_credentials=False`, methods `GET,POST,PUT,PATCH,DELETE`, headers `Content-Type, Authorization`.
6. **Health endpoint** stays unauthenticated (sidecar health-check uses it).

## 4. Acceptance criteria

- With the packaged app (or env var set manually): `curl http://127.0.0.1:18741/api/v1/chat/sessions` → 401; with the header → 200.
- Chat streaming, model download SSE, personal-docs job SSE all work in Tauri prod build and in dev mode.
- pytest suite passes with no token set.
- A browser page on a random origin gets CORS-blocked for non-allowed origins.

## 5. Decision needed: `/v1/*` (OpenAI-compat)

Aider/Continue/Cursor users point external tools at `localhost:18741/v1` — they can't send our token. Options:
- **(a)** Leave `/v1/*` unauthenticated (current behavior, documented risk: local processes can spend cloud keys).
- **(b)** Settings toggle "Enable local API server" (default ON or OFF?) + optional user-set API key shown in Settings.
- **Recommendation:** (b), default ON with auto-generated key displayed in Settings → AI Providers; OpenAI clients all support custom API keys.

## 6. Out of scope

Encrypting keys at rest (SPEC-02), rate limiting, CSP (SPEC-12).

## 7. Test plan

- New backend tests: 401 without header, 200 with, no-op when env unset.
- Manual: `npm run tauri dev` + packaged build smoke test of chat stream + model download.
