# SPEC-04 — Atomic `update_one` in SQLite Adapter

- **Links:** GAPS REL-2, SEC-6 · FEATURES B4
- **Priority:** P1 · **Effort:** M (small diff, large test surface)
- **Review status:** ⬜ pending review

## 1. Goal

Two concurrent `update_one` calls on the same document never silently lose one writer's changes. Concurrent crew runs stop corrupting shared state.

## 2. Context (verify before coding)

- `backend/adapters/sqlite_adapter.py:166-189` (location approximate): `update_one` = `find_one` → apply Mongo operators in Python (`_apply_update_operators`) → `UPDATE ... SET data = ?`. Between read and write another coroutine can commit, and its write is overwritten.
- All writes go through one aiosqlite connection; callers rely on Motor-compatible semantics via `adapters/motor_compat.py`.
- Hot callers: `services/workspace/orchestrator.py` job state, crew/trigger state updates, checkpoint service.

## 3. Plan — optimistic CAS (keeps the operator engine in Python)

Rewriting every Mongo operator in SQL (`json_set`) is high-risk; instead keep the Python operator application and make the write conditional:

1. Read row including a hidden `_rev` integer (add column or store inside `data` — prefer a real column `rev INTEGER NOT NULL DEFAULT 0`; `_ensure_table` must add it via `ALTER TABLE` migration for existing tables).
2. Apply operators in Python as today.
3. `UPDATE ... SET data = ?, rev = rev + 1, updated_at = ? WHERE _id = ? AND rev = ?` — if `rowcount == 0`, another writer won: retry the whole read-apply-write (max 5 attempts, tiny backoff). Raise after exhaustion.
4. Same treatment for `update_many` (per-row), `find_one_and_update`, `replace_one` — enumerate what motor_compat actually exposes and cover all write-after-read paths.
5. **SEC-6 fold-in:** in the same file, validate field names used to build SQL (`create_index`, `_field_to_json_path` callers) against `^[A-Za-z_][A-Za-z0-9_.]*$`; raise `ValueError` otherwise.

## 4. Acceptance criteria

- New concurrency test: 50 parallel `update_one` `$inc`-style updates on one doc → final value is exactly 50 (today it's < 50).
- Full backend pytest suite passes unchanged (Motor-compat behavior preserved, incl. upsert path).
- Existing DBs migrate transparently (rev column auto-added; missing rev treated as 0).

## 5. Out of scope

True transactions across collections; WAL tuning; rewriting operators in SQL.

## 6. Test plan

- `pytest backend/tests -q` full run.
- New tests: concurrent increment, upsert race (two upserts on same filter → one insert + one update, not two rows), retry-exhaustion error path, field-name validation rejects `'); DROP`-style names.
