# SPEC-23 — Evals Harness

- **Links:** ROADMAP F-11 (Q2 2027 flagship) · trend vector #5 (evals → ~6x more production deployments) · pairs with SPEC-10 (dry-run)
- **Priority:** P0 (roadmap) · **Effort:** L
- **Review status:** ⬜ pending review
- **Type:** roadmap spec

## 1. Goal

Crews, agents, and workers become *testable*: golden-task suites with scored runs, history across edits and model swaps. Solo gets confidence badges ("9/10 on brand voice"); Enterprise gets CI-for-agents — the proven sales wedge.

## 2. v1 Scope

1. **Eval model** — `eval_suites` (target: agent/crew/worker; list of cases) + `eval_cases` (input, optional reference output, scoring spec) + `eval_runs` (per-case scores, aggregate, model used, config hash of the target at run time).
2. **Scoring methods (v1):**
   - **Checklist judge** — an LLM judge scores against explicit criteria ("mentions pricing accurately", "matches brand voice", "under 280 chars"), binary per criterion → aggregate %. Judge model selectable; local-friendly.
   - **Assertion checks** — deterministic: contains/regex/JSON-shape/length/no-PII-pattern. Free and fast.
   - (Similarity-to-reference scoring is v2 — embedding similarity is too noisy to badge on.)
3. **Authoring UX** — "Add eval" from any crew/worker page; **"promote run to eval case"** (take a real good run, freeze input + criteria) — this is how non-technical users build suites without writing tests.
4. **Execution** — eval runs reuse dry-run plumbing (SPEC-10: outbound captured, never sent). Run on demand + prompted nudge before activating an edited crew ("config changed — re-run 12 eval cases?"). Score history chart per suite; config hash links score changes to edits/model swaps.
5. **Shipped eval packs** — each built-in Digital Worker (SPEC-18) ships with a starter suite (5–8 cases) — both quality floor and teaching-by-example.

## 3. Enterprise port (the product)

CI gates: worker can't deploy to a department below threshold X; scheduled regression runs; score dashboards per org; eval evidence attached to compliance exports (SPEC-24). Sales line: "you wouldn't deploy code without tests — same for agents."

## 4. Acceptance criteria

- Author a 5-case suite on a crew in < 10 minutes via promote-run + checklist criteria; run it; get a scored report with per-criterion breakdown.
- Swap the crew's model, re-run: history shows both runs with config hashes and a delta.
- Eval runs never send outbound (inherits dry-run guarantee, asserted in tests).
- A worker's badge ("passing 9/10") shows on its page and updates after each run.

## 5. Open questions

- Judge reliability with small local models — minimum recommended judge size? (Bench during design; may need to recommend a cloud judge for serious suites and say so honestly.)
- Nondeterminism: run each case N=3 and report variance, or single-shot in v1? (Variance is honest but triples cost.)
- Do eval scores feed worker KPI cards (SPEC-18), or stay a separate surface to avoid gamified noise?
