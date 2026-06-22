# SPEC-18 — Digital Workers ("Hire, Don't Configure")

- **Links:** ROADMAP F-6 (Q4 2026 flagship) · trend: agentic workforce · depends on SPEC-16/17; synergizes with SPEC-14 (worker-scoped memory)
- **Priority:** P0 (roadmap) · **Effort:** L
- **Review status:** ⬜ pending review
- **Type:** roadmap spec

## 1. Goal

Reframe Solo from a catalog of 96 agents into a *workforce you hire*: a Digital Worker is a packaged role — agents + crew(s) + KBs + channels + schedule + watchers — with a name, an onboarding interview, a KPI card, and a weekly self-review. Same plumbing, radically better mental model for non-technical users.

## 2. v1 Scope

1. **Worker model** — `workers` collection: name, role template id, avatar, bound resources (crew ids, KB ids, connection ids, watcher ids, schedules), status (active/paused), hired_at. A worker is a *view + lifecycle wrapper* over existing objects — no new execution engine.
2. **5 built-in role templates:**
   - **Social Media Manager** (auto-reply crew + content crew + channel bindings + volume watcher)
   - **Research Analyst** (research crew + RSS/web watchers + weekly digest schedule)
   - **Support Rep** (FAQ crew + KB binding + inbound channels + approvals-always-on)
   - **Content Studio** (blueprint-based content pipeline + blog/social distribution)
   - **Ops Assistant** (Pulse curation + folder watchers + document summarization automations)
3. **Onboarding interview** — hiring a worker runs a short chat-driven setup (the worker "interviews you"): brand voice, which channels, which folders/KBs, approval strictness → fills the underlying configs. Skippable for power users (raw config still accessible).
4. **Worker page** — `/workers` (replaces or sits beside Crews in the sidebar — reviewer call): roster view with status; per-worker page: KPI card (runs, replies sent, approval rate, est. time saved), activity feed, bound resources, pause/fire (fire = archive bindings, never delete data).
5. **Weekly self-review** — scheduled automation per worker: "what I did, what I struggled with, what I suggest" → Pulse card. Honest by construction (built from run stats, not generated fluff).

## 3. Enterprise port (Q1 2027)

THE enterprise narrative ("agentic workforce"). Port = role templates + department assignment + per-worker identity for the governance pack (SPEC-24) + private org template registry (SPEC-22). Worker KPI rollups land in the existing analytics dashboard.

## 4. Acceptance criteria

- Hiring "Social Media Manager" via the interview yields a working auto-reply pipeline (Telegram in → drafted reply in Approvals) in < 5 minutes with zero crew-builder exposure.
- KPI card reflects real run/approval counts (reconcilable against Runs tab).
- Pausing a worker stops all its schedules/watchers/triggers in one click; firing archives cleanly; underlying crews remain usable standalone.
- A worker exported via SPEC-22 imports on another machine with placeholders for channels/keys.

## 5. Open questions

- Sidebar surgery: does Workers become the primary nav item with Crews demoted to "advanced"? (Marketing wants Workers; power users live in Crews.)
- "Time saved" estimate — honest methodology, or drop it from v1 KPI card?
- Do workers get their own memory scope at v1 (needs SPEC-14 shipped) or in a fast-follow?
