# SPEC-16 — Pulse: Proactive Daily Briefing

- **Links:** ROADMAP F-4 (Q4 2026 flagship) · trend vector #1 (proactive AI) · depends on SPEC-17 (watchers), SPEC-14 (memory, soft)
- **Priority:** P0 (roadmap) · **Effort:** L
- **Review status:** ⬜ pending review
- **Type:** roadmap spec

## 1. Goal

Solo opens the day for the user instead of waiting for a prompt: one briefing — "3 things need you, 2 things I did, 1 thing I noticed" — assembled from channels, watchers, crew runs, and calendar. Proactive, but every *action* still flows through the existing Approvals queue. This is the next viral demo.

## 2. v1 Scope

1. **Pulse engine** — a scheduled system crew (configurable time, default 8:30 local) that aggregates since-last-pulse: inbound channel messages (triaged: needs-reply / FYI / spam), pending approvals, completed crew/automation runs, watcher events (SPEC-17), KB folder changes, optional ICS calendar feed (read-only URL paste — no OAuth in v1).
2. **Card stack UI** — new `/pulse` route + badge on app icon/tray. Card types: `needs_you` (with inline approve/edit for drafted replies), `done_for_you` (links to run output), `noticed` (watcher signal + suggested action button that pre-fills an Automation). Dismiss/snooze per card; "mute this source" affordance on every card.
3. **Delivery** — in-app stack + Windows tray notification ("Your Pulse is ready — 3 items need you"). Optional local TTS read-out (SPEC-19). Optional send-to-channel (email yourself the Pulse) via existing distribution adapters.
4. **Pulse settings** — time, sources on/off, quiet days, "only when there's something" toggle (no empty briefings).
5. **Model policy** — triage/summarize with a small fast local model by default (0.8–2B class); user can pick. Never block on a 30s 70B generation for a briefing.

## 3. Architecture sketch

`services/pulse_service.py` (aggregate → triage → compose) on the existing scheduler infra; `pulse_items` collection; cards reference source objects rather than copying them. Composition itself is a crew (visible in Runs, debuggable, dry-runnable via SPEC-10) — eat our own dogfood.

## 4. Enterprise port (Q1 2027)

Team Pulse: per-user digests + org/department rollups; delivery via Slack/Teams/email; admin source policy. Strong DAU driver in both products.

## 5. Acceptance criteria

- Overnight: 5 Telegram messages, one crew run, 2 changed KB files → morning Pulse shows correct triage, one tap approves a drafted reply, dismissed cards stay dismissed.
- Zero activity + "only when something" → no Pulse, no notification.
- Pulse generation works fully offline with local models; total generation < 60s on an 8 GB machine.
- Nothing is ever *sent* anywhere by Pulse without going through Approvals.

## 6. Open questions

- Is `/pulse` a new sidebar item (9th — sidebar cost) or does it replace/absorb the current home/dashboard?
- Should "I noticed" suggestions learn from dismissals (down-rank muted patterns) in v1 or defer to memory layer integration?
- Calendar: ICS-paste only, or is Google Calendar OAuth worth the scope creep? (Proposed: ICS only in v1.)
