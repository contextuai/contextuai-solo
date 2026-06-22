# SPEC-03 — Sidecar Lifecycle Robustness

- **Links:** GAPS REL-1 · FEATURES B3
- **Priority:** P0 · **Effort:** M
- **Review status:** ⬜ pending review

## 1. Goal

The app never silently hangs because of a dead, orphaned, or port-blocked sidecar. Failures show an actionable error UI; orphans from a previous crash are cleaned up automatically.

## 2. Context (verify before coding — audit-sourced, re-read the Rust)

- `frontend/src-tauri/src/sidecar.rs`: spawns the PyInstaller sidecar, health-checks (reported: 60s timeout), `stop_sidecar()` guards double-stop but nothing handles a *pre-existing* process on 18741.
- `frontend/src-tauri/src/main.rs`: setup spawns sidecar startup as a background task; errors don't reach the UI.
- If the Tauri process crashes, the sidecar survives; next launch can't bind 18741 and times out → blank app.

## 3. Plan

1. **Startup probe:** before spawning, GET `http://127.0.0.1:18741/health` (or the actual health route — verify).
   - If it responds **and identifies as contextuai** (add `"app": "contextuai-solo", "pid": <pid>, "version": <v>` to the health payload): it's an orphan → kill it (Windows: `taskkill /PID <pid> /F` via the pid from health; fallback `netstat`-free approach: store sidecar PID in `~/.contextuai-solo/sidecar.pid` on spawn and use that), then spawn fresh.
   - If it responds but is **not** ours: pick a fallback port (try 18742-18751), pass it to the sidecar via env/arg; `get_sidecar_port` IPC already exists and the frontend already asks for the port — verify nothing else hardcodes 18741.
2. **PID file:** write on spawn, remove on clean shutdown; startup also kills a stale PID-file process if alive and unresponsive.
3. **Surface failure:** if the sidecar isn't healthy after the timeout, emit a Tauri event; frontend shows a blocking error screen ("Backend failed to start") with the last 50 lines of sidecar stderr (capture to `~/.contextuai-solo/logs/sidecar.log`) and a Retry button. There may be an existing `useBackendStatus` hook (seen in `routes/models.tsx`) — build on it.
4. **Shutdown:** ensure window-close and tray-quit both run `stop_sidecar`; on Windows also use a Job Object or `taskkill /T` so child processes die with the app (verify what Tauri sidecar API already provides before adding code).

## 4. Acceptance criteria

- Kill the Tauri process (Task Manager) while running → relaunch works without manual cleanup.
- Occupy 18741 with a foreign process → app starts on a fallback port and works end-to-end (chat + streaming).
- Break the sidecar exe (rename) → user sees the error screen with log excerpt, not a blank window.

## 5. Out of scope

Auto-restart of a sidecar that dies mid-session (nice-to-have; note if trivial), macOS/Linux parity beyond best effort.

## 6. Test plan

Manual matrix on Windows (the three acceptance scenarios) + existing Playwright suite still green in dev mode.
