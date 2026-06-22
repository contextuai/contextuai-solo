# SPEC-07 — Surface Startup Seed/Migration Failures

- **Links:** GAPS REL-5
- **Priority:** P2 · **Effort:** S
- **Review status:** ⬜ pending review

## 1. Goal

When agent-library seeding, blueprint seeding, or a migration fails at startup, the user sees what broke (and the app says so via API) instead of a mysteriously empty page.

## 2. Context (verify before coding)

- `backend/app.py` startup event (~472-610): seeds persona types, agent library, blueprints, crew templates, local/cloud models, then runs migrations like `run_unify_connections_migration` — several wrapped in `except Exception: logger.exception(...); # continue`.
- A failed agent-library seed leaves `/agents` empty with no explanation; a skipped migration can silently leave data in a half-migrated shape.

## 3. Plan

1. Collect failures during startup into `app.state.startup_issues: list[dict]` — `{"step": "...", "error": str(exc), "fatal": bool}`. Keep log-and-continue behavior (don't make startup brittle), but record everything that was swallowed.
2. Extend the health/status endpoint (find the existing one the frontend's `useBackendStatus` hook polls) to include `startup_issues`.
3. Frontend: if `startup_issues` is non-empty, show a dismissible warning banner in the shell ("Some components failed to initialize — details") with the step names and a copyable error text. One banner, not per-issue toasts.
4. **Migrations specifically:** record per-migration status rows in a `_migrations` collection (`name`, `applied_at`, `error`) so a failed migration is retried on next startup rather than assumed done. Verify current migrations are idempotent before enabling retry (read each `backend/migrations/*.py` — they're written as one-shot backfills; most look idempotent by construction, confirm per file).

## 4. Acceptance criteria

- Corrupt one agent markdown file (or point `AGENT_LIBRARY_PATH` at nowhere) → app starts, banner appears naming the agent-library step, `/agents` page shows an inline "library failed to load" state instead of empty grid.
- Failed migration is re-attempted next startup and recorded in `_migrations`.
- Clean startup → no banner, `startup_issues: []`.

## 5. Out of scope

Redesigning the seeding pipeline; auto-repair of corrupted files.

## 6. Test plan

pytest: startup with broken library path produces `startup_issues`; migration ledger written/retried. Playwright: banner renders when status endpoint returns issues (mock).
