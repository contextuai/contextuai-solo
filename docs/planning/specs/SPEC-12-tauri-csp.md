# SPEC-12 — Tauri Content Security Policy

- **Links:** GAPS SEC-4
- **Priority:** P1 (S effort) · **Review status:** ⬜ pending review

## 1. Goal

`tauri.conf.json` ships a real CSP so an XSS in the React app can't trivially script against Tauri IPC.

## 2. Context (verify before coding)

- `frontend/src-tauri/tauri.conf.json` → `app.security.csp: null` (audit-sourced — verify key path for Tauri v2).
- The app loads: bundled Vite assets, Tailwind inline styles, data: images (icons/screenshots?), SSE/fetch to `http://127.0.0.1:18741` (and fallback ports per SPEC-03). No remote scripts expected — verify by grepping `index.html` and checking for CDN/font/analytics loads.

## 3. Plan

1. Inventory actual asset origins (grep for `http`-prefixed URLs in `frontend/src` + `index.html`; check fonts/images).
2. Set CSP, starting point (tighten/loosen per inventory):
   ```
   default-src 'self';
   script-src 'self';
   style-src 'self' 'unsafe-inline';
   img-src 'self' data: blob:;
   font-src 'self' data:;
   connect-src 'self' ipc: http://ipc.localhost http://127.0.0.1:* http://localhost:*;
   ```
   Notes: Tauri v2 IPC needs `ipc:`/`http://ipc.localhost` in `connect-src` on Windows; `127.0.0.1:*` covers sidecar + fallback ports; `'unsafe-inline'` for styles is required by Tailwind's runtime-injected styles only if actually used — test without it first.
3. Tauri dev mode (Vite HMR on 1420, websockets) — confirm Tauri applies `devCsp` or that dev still works; use `app.security.devCsp` for a looser dev policy if needed.
4. Full manual regression of the heavy webview surfaces: chat streaming, model download progress, PDF/file uploads, image rendering in chat, Coder mode preview (embedded preview may iframe a local server — needs `frame-src`; verify).

## 4. Acceptance criteria

- Packaged build: all major flows work with CSP enforced (chat stream, downloads SSE, KB upload, Coder preview, charts).
- An injected remote `<script>` tag (manual devtools test) is blocked by CSP.
- `npm run tauri dev` still works.

## 5. Out of scope

SEC-1 token work (SPEC-01). Separately worth a later pass (not this spec): audit how chat markdown is rendered and confirm any raw-HTML rendering path sanitizes untrusted content (e.g., with DOMPurify).
