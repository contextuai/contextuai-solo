# Personal Docs — Folder-mapped RAG (design spec)

**Date:** 2026-04-30
**Branch (target):** `feat/p2.5-3-personal-docs-folder-rag`
**Depends on:** P2.5-2 Knowledge Base / RAG (already shipped, commit `44ad87a`)
**Status:** Approved — ready for implementation plan

---

## 1. Goal

Let the user point ContextuAI Solo at one or more folders on their PC and have those folders auto-ingested into the existing Knowledge Base / RAG system. The user can then use that KB during chat **and** during agent / crew runs without having to manually upload files.

This is **not** a new parallel system. It extends the KB feature shipped in P2.5-2 with a new kind of source: a folder mapping.

## 2. Locked-in design choices

| Axis | Decision |
|---|---|
| Architecture | Folder mapping extends existing KBs (a KB has both uploaded files and mapped folders). |
| Sync model | Manual "Sync now" per folder + optional periodic background sync (off / 1 h / 6 h / 24 h). No live file watcher in v1. |
| File scope | `.pdf .docx .txt .md .html .htm .rtf .csv .json`. User-editable include/exclude globs per mapping. |
| Agentic access | Both crews and workspace agents gain `knowledge_base_ids: string[]`. Per-agent overrides crew default. |
| Scope guards | 10 MB / file, 5,000 files / mapping, recursion depth 10, friction-modal at > 1,000 candidate files. Caps overridable in advanced settings. |

## 3. Architecture

```
Tauri shell (Rust)
  └── dialog plugin → folder picker → returns absolute path to React
React frontend
  └── /knowledge/<kb_id> route gains a "Folders" tab
        ├── add folder mapping (path, globs, schedule)
        ├── per-folder Sync now / Pause / Edit / Delete
        └── live progress (SSE) for the active index job
FastAPI backend
  ├── routers/personal_docs.py        ← new (folder source + sync CRUD)
  ├── services/personal_docs_service.py ← new (walker + indexer)
  ├── services/rag_service.py         ← extended: ingest_from_path()
  ├── repositories/folder_source_repository.py ← new
  ├── repositories/index_job_repository.py     ← new
  ├── services/personal_docs_scheduler.py      ← new (periodic sync tick)
  └── services/agent_runner.py        ← extended: KB retrieval before each turn
SQLite (motor_compat)
  ├── kb_folder_sources    ← new collection
  ├── kb_index_jobs        ← new collection
  └── kb_documents         ← extended schema (source_type, source_id, abs_path, mtime, content_hash)
```

**Reused as-is:** `embedding_service`, `ChunkRepository`, `DocumentRepository`, `KnowledgeBaseRepository`, `RAGService.query`, `RAGService.format_context`, chat-injection path in `routers/ai_chat.py`, KB dropdown in chat UI.

**New surface:** Tauri folder-picker bridge, two collections, two repos, one router, one service, one scheduler, two UI tabs, one settings panel.

## 4. Data model

### 4.1 `kb_folder_sources`

```jsonc
{
  "_id": "<uuid>",
  "kb_id": "<uuid>",                 // FK → knowledge_bases
  "path": "C:\\Users\\nagen\\Documents\\Notes",  // absolute, OS-native
  "label": "Notes",                  // user-editable, defaults to basename(path)
  "include_globs": ["**/*"],         // applied first
  "exclude_globs": [                 // user-editable, prepopulated with defaults
    "**/.git/**", "**/node_modules/**", "**/__pycache__/**",
    "**/.venv/**", "**/venv/**", "**/dist/**", "**/build/**",
    "**/.next/**", "**/.turbo/**", "**/.cache/**", "**/.idea/**",
    "**/.vscode/**", "**/target/**", "**/out/**", "**/coverage/**",
    "**/Thumbs.db", "**/.DS_Store", "**/.*"
  ],
  "schedule": "manual",              // "manual" | "1h" | "6h" | "24h"
  "max_file_bytes": 10485760,        // 10 MB; per-mapping override of global default
  "max_files": 5000,
  "max_depth": 10,
  "status": "active",                // "active" | "paused" | "error"
  "last_sync_at": "2026-04-30T12:34:56Z",
  "last_sync_job_id": "<uuid>",
  "file_count": 142,
  "byte_count": 27_344_512,
  "error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

### 4.2 `kb_index_jobs`

```jsonc
{
  "_id": "<uuid>",
  "kb_id": "<uuid>",
  "source_id": "<uuid>",             // → kb_folder_sources
  "kind": "full_sync",               // "full_sync" | "incremental" | "delete_source"
  "status": "running",               // "queued" | "walking" | "awaiting_confirmation" | "running" | "done" | "error" | "cancelled"
  "files_total": 142,                // 0 until walk completes
  "files_done": 87,
  "files_added": 12,
  "files_updated": 3,
  "files_removed": 1,
  "files_skipped": 71,               // unchanged on incremental
  "bytes_total": 27_344_512,
  "bytes_done": 16_001_024,
  "started_at": "...",
  "finished_at": null,
  "error": null,
  "cancel_requested": false,
  "created_at": "..."
}
```

### 4.3 Extended `kb_documents`

Existing fields stay. New optional fields:

```jsonc
{
  // ...existing...
  "source_type": "folder",           // "upload" | "folder"  (existing rows = "upload")
  "source_id": "<folder_source_id>", // null for uploads
  "abs_path": "C:\\...\\file.pdf",   // null for uploads
  "mtime": 1714492800.123,           // POSIX float seconds; null for uploads
  "content_hash": "sha256:abc123..." // null for uploads
}
```

### 4.4 Extended `crews` and `workspace_agents`

```jsonc
{
  // ...existing...
  "knowledge_base_ids": ["<kb_id>", ...]   // optional, default []
}
```

Per-agent override semantics:
- If `agent.knowledge_base_ids` is non-empty → use those.
- Else → fall back to `crew.knowledge_base_ids`.
- Else → no KB injection.

## 5. Sync semantics

### 5.1 Walk → plan → execute

A sync runs in three phases:

1. **Walk.** Job status `walking`. Recurse `path` up to `max_depth`. Apply `include_globs`, then `exclude_globs`. Drop files whose extension isn't in the supported set. Drop files larger than `max_file_bytes`. If candidates ≥ `max_files`, abort the walk and finish the job with `status="error"`, `error="cap_reached"` — the friction-modal step does not run.
2. **Plan.** Compare candidates against existing `kb_documents` for this `source_id`:
   - **New** — `abs_path` not in existing set.
   - **Updated** — `abs_path` exists but `(mtime, size)` differ from the stored row. (Hash check is a fallback if mtime is unreliable; we trust mtime+size by default.)
   - **Removed** — existing `abs_path` no longer in candidates.
   - **Unchanged** — skip.
3. **Execute.** For new and updated files, read bytes, call `RAGService.ingest_from_path()` (new method that wraps existing `ingest_document`, accepting bytes + abs_path + mtime + hash). For removed files, delete the document row and its chunks (`chunk_repo.delete_for_document`). Update job counters as we go.

### 5.2 Concurrency

- One indexing job per `source_id` may run at a time. A second sync request returns `409 conflict` with the running job id.
- The indexer runs in a single background `asyncio.Task` per backend process (since embedding is CPU-bound and llama-cpp is already serialised on a lock). Sequential ingest is fine — file IO is not the bottleneck, embedding is.
- Cancellation: the API sets `cancel_requested = true` on the job; the indexer checks this between files.

### 5.3 Friction modal

When the **walk phase** completes and `files_total > 1000`, the job pauses in `status="awaiting_confirmation"` (additional status). The frontend polls (or SSE) and shows:

> "Indexing this folder will process ~3,200 files (~340 MB). Estimated embedding time: ~25 min. Continue?"

User confirms → `POST /api/v1/personal-docs/jobs/{job_id}/confirm` → job transitions to `running`. User cancels → job ends with `cancelled`. No work has been embedded yet.

Estimated time uses a rolling-average chunks-per-second from previous runs (default 30 chunks/sec on cold start).

### 5.4 Periodic background sync

A single `PersonalDocsScheduler` runs every 60 s as a backend task (mirrors `reddit_poller`). It scans `kb_folder_sources` where `status="active"` and `schedule != "manual"`, computes due time from `last_sync_at + interval`, and enqueues `incremental` jobs. The friction modal does **not** apply to scheduled runs (already trusted), but the per-mapping caps still do.

## 6. Backend API

All routes mounted under `/api/v1/personal-docs` (separate router file, but the data lives inside KBs).

| Method | Path | Purpose |
|---|---|---|
| `GET`    | `/kbs/{kb_id}/folders` | list folder mappings for a KB |
| `POST`   | `/kbs/{kb_id}/folders` | create a folder mapping (body: path, label, globs, schedule, caps); returns `{source, job_id}` immediately and the indexer starts walking. If the walk count > friction threshold, the job stops in `awaiting_confirmation` until the client posts to `/jobs/{job_id}/confirm`. |
| `GET`    | `/folders/{source_id}` | read a single mapping |
| `PUT`    | `/folders/{source_id}` | edit globs / schedule / label / caps / pause |
| `DELETE` | `/folders/{source_id}` | remove mapping; cascades to delete its documents + chunks |
| `POST`   | `/folders/{source_id}/sync` | trigger an incremental sync now |
| `GET`    | `/folders/{source_id}/jobs` | list recent jobs (paginated, latest 20) |
| `GET`    | `/jobs/{job_id}` | job detail (used by polling) |
| `GET`    | `/jobs/{job_id}/stream` | SSE stream of job progress events |
| `POST`   | `/jobs/{job_id}/confirm` | confirm a job that is in `awaiting_confirmation` |
| `POST`   | `/jobs/{job_id}/cancel`  | request cancellation |

The existing `/api/v1/knowledge-bases/{kb_id}/documents` already returns all docs in a KB. Extension: response items gain `source_type` and (when `folder`) `source_id`, `abs_path`, `label_of_source` so the UI can group them.

## 7. Frontend

### 7.1 `/knowledge/<kb_id>` becomes tabbed

```
┌─ KB header (name, edit, delete) ───────────────────┐
│  [ Documents ]  [ Folders ]  [ Settings ]          │
└────────────────────────────────────────────────────┘
```

- **Documents** — current list (unchanged), with a "Source" column showing either "Upload" or `<folder label>`.
- **Folders** — new. Lists folder mappings with: label, path (truncated, hover-full), schedule, status badge, last-sync time, file count, sync-now button, edit, delete. Above the list: "Add folder" button.
- **Settings** — KB name + description (existing PUT) and a new "Advanced" sub-section for global caps overrides used as defaults when adding new folders.

### 7.2 Add-folder modal

```
[ Choose folder… ]                     ← Tauri folder picker
Label: [ Notes                       ]
Schedule: ( ) Manual  ( ) 1h  ( ) 6h  ( ) 24h
Include globs: [ **/*                ]
Exclude globs: [ default list, editable as a textarea ]
[ Advanced ▾ ]
   Max file size: [ 10 ] MB
   Max files:     [ 5000 ]
   Max depth:     [ 10 ]
                                    [ Cancel ] [ Add ]
```

After "Add", the modal becomes a progress panel that polls `/jobs/{job_id}` (or subscribes to its SSE stream). When `awaiting_confirmation` it shows the friction modal with file count + ETA.

### 7.3 Tauri folder picker

Use `tauri-plugin-dialog`. The first implementation step verifies whether it's already in `Cargo.toml` (the working tree currently shows `Cargo.toml` and `Cargo.lock` modified — that change might already be the dialog plugin) and adds it if not. Expose a wrapper in `lib/tauri.ts`:

```ts
export async function pickFolder(): Promise<string | null>
```

In dev mode (no Tauri), fall back to a free-text input with a warning: "Native folder picker unavailable in dev — type the absolute path."

Tauri capability config (`frontend/src-tauri/capabilities/default.json`) must allow:
- `dialog:allow-open` (folder picker)
- nothing else changes — backend reads files itself, frontend never reads filesystem content.

### 7.4 Chat KB dropdown — unchanged

It already lists all KBs. Folder-fed KBs just appear with a higher chunk count.

### 7.5 Crew + agent KB binding UI

In **crew builder** (existing 7-step wizard):
- Step 1 "Details" already has model selection. Add a **"Knowledge"** subsection: multi-select dropdown of KBs. Optional. Stored as `crew.knowledge_base_ids`.

In **agent details panel** (workspace agent view):
- New "Knowledge" section: same multi-select. Optional. Stored as `agent.knowledge_base_ids`. Help text: "Overrides crew-level knowledge if set."

## 8. Agent runner integration

In `backend/services/workspace/agent_runner.py`, at the point where the per-turn system prompt is composed (just before the LLM call), inject KB context:

```python
kb_ids = agent.get("knowledge_base_ids") or crew.get("knowledge_base_ids") or []
if kb_ids:
    citations = []
    for kb_id in kb_ids:
        citations.extend(await rag.query(kb_id, task_prompt, top_k=3))
    # de-dupe by (doc_id, chunk_index), keep top 8 by score
    citations = top_unique(citations, k=8)
    system_prompt = RAGService.format_context(citations) + "\n\n" + system_prompt
```

The same hook applies in chat already (`routers/ai_chat.py`); for agents, this is the only new line of retrieval logic. Existing `format_context()` instructs the model to cite `[1]`, `[2]`, ... — keep that behavior.

## 9. Error handling

| Scenario | Behavior |
|---|---|
| Folder path doesn't exist at sync time | Job error `path_missing`. Mapping marked `status=error`. UI shows red badge with "Re-locate folder" affordance. |
| Permission denied on subdirectory | Skip that subtree, log to job warnings. Job continues. |
| File read error (locked / corrupted) | Skip file, increment `files_skipped`, add to job warnings. |
| Embedding failure | Mark document `status=error`; job continues. |
| Walk exceeds `max_files` | Stop walking; job error `cap_reached` with current count. User can raise cap or narrow globs. |
| Backend crash mid-job | On startup, mark `running` jobs `error="interrupted"`. User triggers re-sync; incremental skip handles already-embedded files. |
| Two sync requests for the same source | 2nd returns `409 conflict` with running `job_id`. |
| KB deleted while folder mapping active | Cascade: delete folder mappings, cancel running jobs, delete documents + chunks (already in `delete_kb`). |

## 10. Settings & defaults

Add to `backend/settings.py`:

```python
PERSONAL_DOCS_MAX_FILE_BYTES = int(os.getenv("PERSONAL_DOCS_MAX_FILE_BYTES", 10 * 1024 * 1024))
PERSONAL_DOCS_MAX_FILES = int(os.getenv("PERSONAL_DOCS_MAX_FILES", 5000))
PERSONAL_DOCS_MAX_DEPTH = int(os.getenv("PERSONAL_DOCS_MAX_DEPTH", 10))
PERSONAL_DOCS_FRICTION_THRESHOLD = int(os.getenv("PERSONAL_DOCS_FRICTION_THRESHOLD", 1000))
PERSONAL_DOCS_SCHEDULER_TICK_SECONDS = int(os.getenv("PERSONAL_DOCS_SCHEDULER_TICK_SECONDS", 60))
```

Per-mapping fields in `kb_folder_sources` override these. The frontend "Advanced" panel writes into per-mapping caps; nothing writes into env.

## 11. Privacy & security

- All file IO happens on the user's machine; nothing is uploaded.
- The folder picker is the **only** path to add a mapping; users can't type arbitrary paths via a free-text field except in dev fallback (clearly labeled).
- The default exclude list strips dotfiles and dot-folders, so `~/.ssh`, `~/.aws`, `%APPDATA%/...` content is excluded by default. (Mac/Linux dotfiles, Windows hidden attribute also respected.)
- No telemetry on indexed content.
- KB documents already live in `~/.contextuai-solo/data/contextuai.db`; folder-source documents store **chunked text** in that DB, same as uploads. We do not duplicate the original file — only the embedded chunks. (Original file is read from disk on demand if we ever need to re-display; for v1 we don't open the source again after embedding.)

## 12. Testing

### 12.1 Backend (pytest)

- `test_folder_walker.py` — globs, depth limits, ignore patterns, max_files cap, large-file skip, hidden-file skip.
- `test_personal_docs_service.py` — full sync ingests N files; incremental sync correctly classifies new / updated / removed / unchanged using temp dirs and mtime manipulation.
- `test_index_jobs.py` — friction-modal pause/confirm flow; cancel flow; concurrent-sync 409.
- `test_kb_query_with_folder_docs.py` — KB query returns chunks regardless of `source_type`; citation format unchanged.
- `test_agent_runner_kb.py` — per-agent override beats crew default; empty list means no injection.

### 12.2 Frontend (Playwright e2e)

- `personal-docs-folder.spec.ts` — Add a folder mapping using the dev fallback path input (since Playwright can't drive a Tauri picker); confirm friction modal renders for a synthesised >1k count; verify documents appear in the Documents tab tagged with the source label.
- Existing `knowledge-base.spec.ts` — extend to verify the new "Folders" tab renders empty state.

### 12.3 Manual test checklist

- Map `~/Documents` (or a real folder); confirm friction modal correctness.
- Edit a `.md` file inside; "Sync now" reflects the change as `files_updated=1`.
- Delete a file; "Sync now" removes it from chunks.
- Pause a folder; scheduled sync skips it.
- Bind a KB to a crew; run the crew on a question whose answer is in a folder doc; verify the model output cites it.
- Bind a different KB to one agent in the crew; verify only that agent sees the override.

## 13. Out of scope (explicit non-goals for v1)

- Live file watcher (Rust `notify`).
- Code-aware chunking for `.py / .ts / .go / ...` (not in v1 scope set).
- OCR for image-only PDFs.
- Re-indexing on embedding-model change (we'd need a migration; deferred).
- Cross-device sync of `kb_folder_sources` (this is a single-user desktop app — no sync needed).
- MMR / hybrid retrieval improvements (orthogonal; tracked separately).
- Showing source-file previews in the Documents tab.

## 14. Migration

No DB schema migration is strictly required because documents store JSON. Existing rows read with `source_type=None` are treated as `"upload"` by a default-coalescing read path. New rows get explicit fields. Two new collections (`kb_folder_sources`, `kb_index_jobs`) are created on first use.

Crew + agent docs gain `knowledge_base_ids: []` lazily (read defaults to `[]` if absent).

## 15. Rollout

This is a feature branch (`feat/p2.5-3-personal-docs-folder-rag`) cut from `main` after `feat/p2.5-2-knowledge-base-rag` lands. Standard PR review → merge → release flow per the user's `/release` skill. No feature flag — once shipped, the "Folders" tab is visible in every KB.

Targeted release: bundled with the next `1.0.0-beta.x` cut after KB ships.

---

## Appendix A — File / module checklist

**New backend files:**
- `backend/routers/personal_docs.py`
- `backend/services/personal_docs_service.py`
- `backend/services/personal_docs_scheduler.py`
- `backend/repositories/folder_source_repository.py`
- `backend/repositories/index_job_repository.py`
- `backend/models/personal_docs_models.py`
- `backend/tests/test_folder_walker.py`
- `backend/tests/test_personal_docs_service.py`
- `backend/tests/test_index_jobs.py`
- `backend/tests/test_agent_runner_kb.py`

**Modified backend files:**
- `backend/services/rag_service.py` — add `ingest_from_path()`, `delete_for_source()`.
- `backend/repositories/document_repository.py` — query helpers for `source_id`, `abs_path`.
- `backend/services/workspace/agent_runner.py` — KB retrieval injection.
- `backend/routers/knowledge_base.py` — extend documents response with source fields.
- `backend/app.py` — register new router; start `PersonalDocsScheduler` lifecycle.
- `backend/settings.py` — new env-var defaults.
- `backend/models/crew_models.py`, `backend/models/workspace_agent_models.py` — `knowledge_base_ids: list[str] = []`.

**New frontend files:**
- `frontend/src/components/knowledge/folders-tab.tsx`
- `frontend/src/components/knowledge/add-folder-modal.tsx`
- `frontend/src/components/knowledge/folder-row.tsx`
- `frontend/src/components/knowledge/sync-progress-panel.tsx`
- `frontend/src/lib/api/personal-docs-client.ts`
- `frontend/src/lib/tauri.ts` — `pickFolder()` helper (or extend an existing tauri.ts).
- `frontend/tests/e2e/personal-docs-folder.spec.ts`

**Modified frontend files:**
- `frontend/src/routes/knowledge.tsx` — restructure into tabs.
- `frontend/src/components/crews/crew-builder.tsx` — Knowledge multi-select on Details step.
- `frontend/src/components/workspace/agent-details.tsx` — Knowledge multi-select.
- `frontend/src-tauri/capabilities/default.json` — `dialog:allow-open` if not present.
- `frontend/src-tauri/Cargo.toml` — `tauri-plugin-dialog` if not present.

## Appendix B — Open implementation questions (to resolve in next session)

1. Is `tauri-plugin-dialog` already wired in (Cargo.lock currently dirty)? If yes, no Rust changes needed; if no, add it.
2. Confirm exact agent-runner module name (`agent_runner.py` referenced in `CLAUDE.md`); identify the single point where the system prompt is composed for an agent turn.
3. Decide between polling and SSE for job progress — SSE matches existing patterns (model download), recommend SSE.
4. Confirm whether `.html`/`.htm` parsing should strip tags (using `beautifulsoup4` — already a transitive dep?) or treat as plain text. Recommend tag-strip via `bs4` for cleaner chunks.
5. Confirm whether `.csv` and `.json` are chunked as raw text (current proposal) or row/object-aware. Recommend raw text in v1.
