# SPEC-26 — Agentic Commerce: Watch → Enterprise Pilot

- **Links:** ROADMAP F-14 (Q2 2027, enterprise-first) · trend vector #4 (AP2/UCP; live agentic payments)
- **Priority:** P3 (watch) · **Effort:** M (pilot, enterprise repo)
- **Review status:** ⬜ pending review
- **Type:** watch-list spec — intentionally thin; expands only when triggers fire

## 1. Position

Agentic payments are real (Alipay: 120M agent-initiated transactions/week; DBS×Mastercard live agentic payment; AP2/UCP standardizing) but protocol churn is high and the trust bar is extreme. We do **not** build payment execution in 2026. We prepare the rails and run an enterprise-only pilot where the agent *prepares* transactions and a human *releases* them — which is exactly our approvals model, so we're structurally early, not late.

## 2. Watch triggers (review quarterly, next: Sep 2026)

Expand this spec into a build spec when **two or more** hold:
- AP2 or UCP reaches a stable 1.0 with at least two major PSPs in production.
- A customer/prospect asks for procurement-agent capability unprompted.
- A2A + payments reference implementations interoperate publicly (not demos).

## 3. Pilot scope (when triggered; enterprise repo)

1. **Procurement Researcher worker** — operator (SPEC-20 port) + research crew compares suppliers/prices, assembles a purchase proposal (item, vendor, price, justification, links).
2. **Transaction preparation** — proposal rendered as a structured purchase order; if AP2/UCP mandate objects are mature, generate the mandate **unsigned/unreleased**.
3. **Human release** — approvals queue with elevated friction (2-step confirm, amount limits, ledger entry with full evidence bundle: eval scores of the worker, sources, operator session recording).
4. **Hard lines (v1):** no autonomous release under any setting; no stored payment credentials in Solo (enterprise vault only); spend limits enforced server-side.

## 4. What Solo gets (and when)

Nothing until the enterprise pilot proves out. Earliest Solo surface: "prepare a purchase for me" producing a checkout-ready cart via operator mode — still human-completed. Revisit after pilot.

## 5. Why keep this spec at all

So the architecture decisions made in SPEC-18/20/24 (worker identity, operator recording, ledger evidence, elevated-friction approvals) are made *knowing* commerce is a likely consumer — the pieces compose into this without rework.
