# Planning Docset

Created 2026-06-12 from a full review of the three repos (solo app, marketing site, enterprise — enterprise only surface-level). Owner: Nagendra. All content is **pending review** until marked otherwise.

## Contents

| File | Purpose |
|------|---------|
| `UNDERSTANDING.md` | Complete system understanding — architecture, data flow, build, conventions. Source of truth for sub-agents before they touch code. |
| `ROADMAP-2026H2-2027.md` | 12-month strategic roadmap (post-agents: memory → proactive → operator/interop → trust at scale), Solo-first with Enterprise port path per feature. |
| `GAPS.md` | Findings register — every issue found (security, reliability, product, marketing), with evidence, severity, and status. |
| `MARKET-PAINS-2026.md` | Community pain-point research (local-AI Reddit/HN) mapped to Solo responses. Source for the SPEC-27..30 cluster. |
| `specs/SPEC-*.md` | Implementation-ready specs, one per work item. Each links back to GAPS/FEATURES IDs. |
| `../../FEATURES.md` | Brainstorming doc for feature direction (repo root). Specs are only written for items that are shaped enough. |

## Workflow

1. **Review** — Nagendra reads each spec, edits inline, flips `Review status` to `✅ approved` (or `❌ rejected` / comments).
2. **Implement** — an approved spec is handed verbatim to a sub-agent. Specs are written to be self-contained: goal, context, files, plan, acceptance criteria, test plan, out-of-scope.
3. **Verify** — every spec has a test plan; the implementing agent must run it and report results.

## Rules for implementing sub-agents

- Read `UNDERSTANDING.md` first, then the spec. Verify any file:line references against current code before changing anything (they age).
- Branch per spec: `feat/<spec-slug>` or `fix/<spec-slug>` off `main`. Never commit to `main` (branch-protected).
- Conventional Commits. TypeScript strict / Python typed+async per `CLAUDE.md`.
- Stay inside the spec's scope. If the spec turns out to be wrong/stale, stop and report — don't improvise.

## Spec index

| Spec | Title | Links | Priority | Review status |
|------|-------|-------|----------|---------------|
| SPEC-01 | Sidecar auth token + CORS lockdown | SEC-1 / FEATURES B1 | P0 | ⬜ pending |
| SPEC-02 | Secrets at rest (DPAPI/keychain) | SEC-2 / FEATURES B2 | P1 | ⬜ pending |
| SPEC-03 | Sidecar lifecycle robustness | REL-1 / FEATURES B3 | P0 | ⬜ pending |
| SPEC-04 | Atomic update_one in SQLite adapter | REL-2 / FEATURES B4 | P1 | ⬜ pending |
| SPEC-05 | Always-on SSRF blocklist | SEC-5 / FEATURES B5 | P0 (XS) | ⬜ pending |
| SPEC-06 | Streaming message durability + Ollama abort parity | REL-3, REL-4 | P1 | ⬜ pending |
| SPEC-07 | Surface startup seed/migration failures | REL-5 | P2 | ⬜ pending |
| SPEC-08 | HF token setting for Model Hub | PROD-1 / FEATURES A7 | P1 (S) | ⬜ pending |
| SPEC-09 | Model preload & warmup | FEATURES A1 | P2 | ⬜ pending |
| SPEC-10 | Crew dry-run mode | FEATURES A2 | P2 | ⬜ pending |
| SPEC-11 | KB folder-mapping staleness badges | FEATURES A4 (badges only) | P2 | ⬜ pending |
| SPEC-12 | Tauri CSP | SEC-4 | P1 (S) | ⬜ pending |
| SPEC-13 | Marketing site quick wins | MKT-1..7 / FEATURES C | P1 | ⬜ pending |
| SPEC-27 | Hardware-aware model picker ("can my machine run this?") | MARKET-PAINS P-1, P-5 | P0 | ⬜ pending |
| SPEC-28 | Verifiable privacy (egress monitor + airplane lock) | MARKET-PAINS P-2 | P1 | ⬜ pending |
| SPEC-29 | Local tool-calling reliability layer | MARKET-PAINS P-3 | P1 | ⬜ pending |
| SPEC-30 | RAG ingestion quality (chunking/cleaning/diagnostics) | MARKET-PAINS P-4 / extends SPEC-11 | P1 | ⬜ pending |

> **New this pass (from MARKET-PAINS-2026):** SPEC-27..30 written; SPEC-08 gained a **BYOK data-classes addendum** (P-7). Still outstanding as a non-spec **chore**: per-model chat template/EOS + auto-`n_ctx` in the catalog (P-5, folded into SPEC-27's scope). **Read `00-START-HERE.md` for the recommended reading order.**

### Roadmap specs (SPEC-14+, from `ROADMAP-2026H2-2027.md`)

Directional product specs — bigger, less certain than gap specs. Flagship items require a detailed design doc before implementation.

| Spec | Title | Roadmap | Quarter | Review status |
|------|-------|---------|---------|---------------|
| SPEC-14 | Unified Memory Layer ("Solo remembers") | F-1 ⭐ | Q3 2026 | ⬜ pending |
| SPEC-15 | GPU acceleration + local-runtime plurality | F-2 | Q3 2026 | ⬜ pending |
| SPEC-16 | Pulse — proactive daily briefing | F-4 ⭐ | Q4 2026 | ⬜ pending |
| SPEC-17 | Signal watchers + always-on mode | F-5 | Q4 2026 | ⬜ pending |
| SPEC-18 | Digital Workers ("hire, don't configure") | F-6 ⭐ | Q4 2026 | ⬜ pending |
| SPEC-19 | Voice layer v1 (local STT/TTS) | F-7 | Q4 2026 | ⬜ pending |
| SPEC-20 | Operator mode (browser) | F-8 ⭐ | Q1 2027 | ⬜ pending |
| SPEC-21 | MCP / A2A server mode | F-9 | Q1 2027 | ⬜ pending |
| SPEC-22 | Crew & Worker marketplace | F-10 | Q1 2027 | ⬜ pending |
| SPEC-23 | Evals harness | F-11 ⭐ | Q2 2027 | ⬜ pending |
| SPEC-24 | Governance pack (ledger/budgets/policies) | F-12 ⭐ | Q2 2027 | ⬜ pending |
| SPEC-25 | Mobile companion | F-13 | Q2 2027 | ⬜ pending |
| SPEC-26 | Agentic commerce (watch-list) | F-14 | watch | ⬜ pending |

⭐ = quarter flagship. Cross-cutting requirement: SPEC-14..21 implementations must emit SPEC-24 ledger events from day one.

Other docs: `COMMUNITY-LAUNCH-KIT.md` — ready-to-post community content + posting playbook.

Already done (no spec needed): Model Hub download rewrite — branch `fix/model-hub-downloads`, commit `f987477`. See GAPS.md REL-0.
