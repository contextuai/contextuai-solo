# SPEC-20 — Operator Mode (Browser) v1

- **Links:** ROADMAP F-8 (Q1 2027 flagship) · trend vector #3 (computer use) · HARD prerequisites: SPEC-01, SPEC-05, SPEC-12 shipped
- **Priority:** P0 (roadmap) · **Effort:** XL
- **Review status:** ⬜ pending review
- **Type:** roadmap spec (requires a full design doc before implementation)

## 1. Goal

Agents get hands: a browser-automation runner that can research, compare, extract, and fill forms on **allowlisted sites**, driven by a vision-capable model — with the Coder-mode trust pattern (explicit trust, visible execution, recording) extended to the web. Desktop-wide OS control is explicitly **out of scope for v1**.

## 2. v1 Scope

1. **Runner** — Playwright (Chromium) managed by the sidecar; one session at a time in v1. Agent loop: observe (DOM accessibility tree + screenshot) → decide (model picks action: navigate/click/type/extract/scroll/done) → act → repeat, with step budget and per-step timeout. Evaluate reusing the Browser-Use OSS loop vs building on Playwright directly — decision in design doc.
2. **Model** — vision-capable local model (Qwen 3.5 VL class via the existing stack — test pipeline in Q4 per roadmap) or BYO cloud model. DOM-tree-first prompting (cheaper, more reliable), screenshots as fallback/verification.
3. **Trust model (the product, really):**
   - Per-task **site allowlist** — operator cannot navigate off-list (enforced at the runner, not the prompt).
   - **Risk gates** — form submissions, downloads, logins, anything POST-like pauses for approval (in-app prompt with screenshot). Read-only actions run free.
   - **Session recording** — every step logged (action, URL, screenshot thumbnail) → replayable timeline in the run view; recordings stored locally, prunable.
   - **Credential policy v1: none** — operator never gets passwords; sites needing login use a persistent profile the user logs into manually first ("operator profile" browser window).
4. **Surfaces** — new agent kind `operator` usable as a crew step + an "Operate" automation action; live run view (current screenshot + step log + STOP button).
5. **Starter tasks** shipped as templates: price/competitor comparison across N sites, structured extraction from a listing page, form fill on an allowlisted internal tool, "check these 5 pages and summarize changes."

## 3. Enterprise port (Q2 2027)

Headless browser pool in containers, policy engine (org-level site allowlists), full session audit into SPEC-24 ledger, per-worker operator identities. The audit trail is the differentiator vs. RPA/SaaS automation.

## 4. Acceptance criteria

- "Compare pricing on these 3 (allowlisted) sites and produce a table" completes end-to-end with local VL model on a 16 GB machine; replayable recording exists.
- Navigation to a non-allowlisted domain is blocked at the runner level (test: model is prompted to "go to evil.com" — runner refuses).
- A form-submit pauses for approval; rejecting cancels the step but preserves the session.
- STOP kills the browser within 2s; no orphaned Chromium processes after app exit (ties into SPEC-03 patterns).

## 5. Open questions

- Bundle Chromium (+~150 MB) vs download-on-first-use (SPEC-15 optional-component pattern — preferred)?
- Headed vs headless default? (Headed builds trust — user *sees* the browser work; proposed: headed default, headless option.)
- Multi-step task persistence: resumable operator sessions or fail-and-retry-whole-task in v1? (Proposed: whole-task retry.)
