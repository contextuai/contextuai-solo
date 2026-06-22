# SPEC-10 — Crew Dry-Run Mode

- **Links:** GAPS PROD-3 · FEATURES A2
- **Priority:** P2 · **Effort:** M
- **Review status:** ⬜ pending review
- **Open decisions for reviewer:** (a) persist dry-runs as `crew_runs` rows with `kind="dry_run"`? (proposed: yes — gives history + reuses the runs UI) (b) also expose dry-run from the crew list for existing crews? (proposed: yes, same endpoint)

## 1. Goal

Users can execute a crew against a sample input with all outbound delivery disabled, and inspect the would-be output, before (or after) the crew goes live.

## 2. Context (verify before coding)

- Crew execution: `services/workspace/orchestrator.py` polls a job queue; `agent_runner.py` runs agents; outbound goes through Distribution adapters bound via `connection_bindings[]`; `approval_required` can hold messages in the Approvals queue.
- Crew builder: `frontend/src/components/crews/crew-builder.tsx`, step 7 = Review & Create.
- There is headless-run plumbing already (`run_headless()` in coder; crews run via job queue) — find how a manual crew run is triggered today (the Crews page has a run action) and piggyback on it.

## 3. Plan

1. **Backend flag:** add `dry_run: bool = False` to the crew-run trigger endpoint/job payload. When set:
   - All outbound adapter sends are replaced by a **capture sink** that records `{platform, connection_id, would_send: payload}` onto the run record. Implement at the single choke point where adapters are invoked (locate it — likely `channel_service` or the runner's output step). Do not monkeypatch per-adapter.
   - Approval queue is bypassed (capture instead).
   - Run record gets `kind="dry_run"` (decision a).
2. **Sample input:** request body accepts `sample_input: str`. Optional helper endpoint: `GET /api/v1/crews/{id}/sample-inputs` returning the last N inbound messages from bound channels (if any) for one-click selection.
3. **Frontend:** "Dry run" button in builder step 7 (works on the in-progress config — requires creating the crew first as `draft` or serializing config to the endpoint; **simplest correct path: save crew, then dry-run it; builder already creates at step 7**) and on each crew card menu. Result modal: per-step agent outputs (if available from the run record) + final captured outbound payloads, clearly badged "NOT SENT".
4. **Runs tab:** dry-runs appear with a distinct badge; filterable.

## 4. Acceptance criteria

- Dry-running a crew bound to a real Telegram connection sends **nothing** (assert adapter send not called in tests) and the modal shows the captured payload.
- Reactive/scheduled triggers are unaffected by dry-runs (no state mutation on trigger bookkeeping — verify what normal runs mutate and exclude it).
- A dry-run of a crew with `approval_required` shows output directly, queues nothing.
- Suite green; new tests for the capture sink and the `kind="dry_run"` row.

## 5. Out of scope

Step-by-step interactive debugging; diffing two dry-runs; dry-run of Automations (separate, smaller — note as follow-up).
