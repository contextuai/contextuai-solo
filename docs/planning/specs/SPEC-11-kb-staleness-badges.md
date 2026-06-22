# SPEC-11 — KB Folder-Mapping Staleness Badges

- **Links:** GAPS PROD-4 · FEATURES A4 (badges half only — auto-suggest deliberately split out)
- **Priority:** P2 · **Effort:** S
- **Review status:** ⬜ pending review

## 1. Goal

Users always know whether a folder-mapped knowledge base reflects the current state of the folder — in the Knowledge page and in the chat KB selector.

## 2. Context (verify before coding)

- Folder mappings: `kb_folder_sources` rows; sync runs recorded in `kb_index_jobs` (progress + error fields); walker classifies new/updated/removed by `(abs_path, size, mtime)` (`services/folder_walker.py`, `personal_docs_service.py`); schedules manual/1h/6h/24h via `personal_docs_scheduler.py`.
- Knowledge UI: `/knowledge/<kb_id>` with Folders tab; chat input has a Knowledge dropdown.

## 3. Plan

1. **Staleness check endpoint:** `GET /api/v1/personal-docs/folders/{mapping_id}/staleness` → `{last_synced_at, changed_files, removed_files, stale: bool}`. Implementation: re-walk the folder with the existing walker in **classify-only** mode (no reads/embedding) and diff against indexed docs — the classification logic already exists; expose it without side effects. Respect the existing file caps; for huge folders return `{stale: "unknown"}` past the friction threshold instead of walking forever.
2. **Cheap aggregate:** `GET /api/v1/knowledge-bases/{id}` response gains `freshness: {last_synced_at, stale_mappings: n}` computed on demand (bounded: only when the KB has folder sources).
3. **UI — Knowledge page:** per-mapping badge: `Synced 2h ago` / `⚠ 5 changed, 1 removed` / `Sync failed` (from last `kb_index_jobs` error) + existing "Sync now" button next to it.
4. **UI — chat KB dropdown:** small `⚠ stale` suffix when `freshness.stale_mappings > 0`. Don't block usage; tooltip explains.
5. **No polling loops:** staleness computed when the Knowledge page opens a KB and when the chat dropdown opens (debounced/cached ~60s in the client).

## 4. Acceptance criteria

- Add/modify/delete files in a mapped folder → badge reflects counts on next page open without running a sync.
- Last-job error surfaces as `Sync failed` with the error text on hover/click.
- Folders past the friction threshold show `staleness unknown` rather than hanging.
- Suite green; unit tests for classify-only diff + endpoint.

## 5. Out of scope

KB auto-suggest in chat (FEATURES A4b — separate spec after this ships); filesystem watchers (mtime diff on open is enough for v1); document-upload KBs (no folder = no staleness concept).
