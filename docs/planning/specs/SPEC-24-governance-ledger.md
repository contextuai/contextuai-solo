# SPEC-24 — Governance Pack: Action Ledger, Budgets, Policies

- **Links:** ROADMAP F-12 (Q2 2027 flagship) · trend vector #5 (governance is the enterprise bottleneck) · consumes events from SPEC-14/16/17/18/20/21
- **Priority:** P0 (roadmap) · **Effort:** L
- **Review status:** ⬜ pending review
- **Type:** roadmap spec
- **Note:** earlier roadmap features must emit ledger events from day one (cheap structured logging now, full product later). If this spec is approved in principle, add the event-emission requirement to SPEC-14..21 implementations.

## 1. Goal

Every consequential action Solo takes — tool call, outbound send, operator step, memory write, external (MCP) invocation — is recorded in one searchable, exportable ledger, governed by budgets and simple policy rules, with undo where undo is possible. Solo gets the lite version; Enterprise gets the compliance product the website already promises.

## 2. v1 Scope (Solo)

1. **Action ledger** — append-only `action_ledger` collection: timestamp, actor (worker/crew/agent/user/external-caller), action type, target, payload digest (not full content for chat; full for outbound), outcome, cost estimate, correlation id (run). Write path = lightweight `ledger.emit()` helper used by services; must add near-zero latency (fire-and-forget queue).
2. **Ledger UI** — `/activity` view: filter by actor/type/date, full-text search, detail drawer, CSV/JSON export. Retention setting (default 90 days, prunable).
3. **Budgets & quotas** — per-worker and global: tokens/day (estimated), outbound messages/day per channel, operator sessions/day. Soft limit → Pulse warning card; hard limit → actions queue with "budget exceeded" state until user releases.
4. **Policy rules v1** — small set of declarative, UI-edited rules (not a DSL): "always require approval for {channel} on {days/hours}", "never auto-send to {platform}", "operator only between 9–18h", "worker X max N runs/day". Evaluated at the same choke points that emit ledger events.
5. **Undo** — where feasible: delete sent Telegram/Discord messages, delete Reddit comment, unpublish blog draft. Ledger rows show an Undo button when the adapter supports it; honest "cannot undo" label otherwise (email, tweets after edit-window).

## 3. Enterprise port (the compliance product)

Per-agent identity (zero-trust framing), RBAC on ledger access, tamper-evident storage (hash chain), SIEM export, retention policies per regulation, PII detection on outbound (ties to the PII promise on the website), eval evidence bundling (SPEC-23). This + registry (SPEC-21 port) is the governance suite the research says CIOs are shopping for.

## 4. Acceptance criteria

- One crew run with an outbound send produces a correlated ledger trail (trigger → agent steps summary → approval → send) findable by searching the channel name.
- Hitting an outbound/day quota holds further sends in a visible queue; releasing works; Pulse card appeared at 80%.
- A weekend-approval policy forces approval on Saturday for a crew that auto-sends on Wednesday.
- Undo deletes a real Telegram message and marks the ledger row "undone".
- Ledger writes add < 5ms p95 to instrumented paths (measured).

## 5. Open questions

- Should chat (non-action) turns be ledgered at all in Solo? (Proposed: no — actions only; enterprise may differ.)
- Hash-chain integrity in Solo v1 or enterprise-only? (Proposed: enterprise-only; Solo keeps it simple.)
- Policy conflicts (two rules disagree) — strictest-wins is the obvious v1 rule; confirm.
