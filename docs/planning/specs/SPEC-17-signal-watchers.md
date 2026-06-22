# SPEC-17 — Signal Watchers + Always-On Mode

- **Links:** ROADMAP F-5 (Q4 2026) · feeds SPEC-16 (Pulse)
- **Priority:** P1 · **Effort:** M
- **Review status:** ⬜ pending review
- **Type:** roadmap spec

## 1. Goal

Generalize the Reddit-poller pattern into a pluggable watcher framework so Solo can notice things: folder changes, RSS/keyword hits, channel anomalies. Watchers produce *events*; events feed Pulse cards and (optionally) trigger crews — initiative without autonomy risk.

## 2. v1 Scope

1. **Watcher framework** — `services/watchers/base.py`: a watcher = config row (`watchers` collection: type, params, interval, enabled, last_run, last_error) + an async `poll()` returning events (`watcher_events` collection: type, payload, seen/handled state). Scheduler runs due watchers (reuse APScheduler/personal-docs scheduler infra). Refactor `reddit_poller` onto the framework as proof.
2. **v1 watcher types:**
   - **Folder watcher** — wraps the personal-docs classify-only diff (SPEC-11): emits `files_changed` events for any folder (not just KB-mapped).
   - **RSS/news watcher** — feed URL + keywords; emits `keyword_hit` with item link/summary.
   - **Web-page watcher** — URL + CSS selector or text snapshot diff; emits `page_changed` (competitor pricing pages, status pages). Respects SSRF guard (SPEC-05).
   - **Channel-volume watcher** — emits `volume_anomaly` when inbound rate deviates (crisis detection — MOONSHOT's Crisis Monitor, made real).
3. **Watcher → action binding** — each watcher optionally binds to: Pulse only (default), run a crew (reuse trigger plumbing), or run an automation. Anything outbound still hits Approvals.
4. **UI** — "Watchers" tab inside Automations route (avoid a new sidebar item): list, add (type picker + params form), event history, mute/enable, per-watcher last-error surface.
5. **Always-on mode** — Setting: "Keep Solo on duty in the tray" — close button minimizes to tray instead of exiting; tray menu (Open, Pulse, Pause watchers, Quit). Watchers and schedules keep running. Depends on SPEC-03 lifecycle work being solid.

## 3. Enterprise port (Q1 2027)

Watchers map onto the Agentic Event Bridge subscription model — unify rather than duplicate: enterprise watcher = bridge subscription with governance (who may watch what). Worth an explicit design alignment doc during the port.

## 4. Acceptance criteria

- Reddit poller runs unmodified-in-behavior on the new framework (existing tests pass).
- An RSS watcher on a real feed + keyword produces an event within one interval; bound crew fires; reply lands in Approvals.
- Folder watcher detects add/change/delete in a watched directory without indexing it.
- With the window closed to tray, watchers fire and a Pulse notification appears; Quit fully stops sidecar (no orphan).
- A failing watcher (bad URL) shows its error in the UI and never crashes the scheduler loop.

## 5. Open questions

- Poll intervals floor (avoid hammering feeds — 5 min minimum?), and do we need jitter/backoff per source?
- Web-page watcher: snapshot diffing can false-positive on dynamic pages — text-similarity threshold or selector-only in v1?
- Should watcher events be retained forever or rolling 30 days? (Proposed: 30 days, ledger-bound later via SPEC-24.)
