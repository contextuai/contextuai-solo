# Personal Docs (Folder-mapped RAG) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing KB / RAG system so users can map any folder(s) on their PC into a Knowledge Base; the indexed corpus is then available to chat **and** to crew/agent runs.

**Architecture:** A new "folder source" attaches to an existing KB. A backend walker enumerates files, plans diffs vs. previously-indexed paths, and feeds new/changed files through the existing `RAGService` ingest pipeline. A periodic scheduler triggers incremental syncs. Crews and workspace agents gain a `knowledge_base_ids` field; the agent runner queries those KBs and prepends citations to the system prompt. UI: `/knowledge/<kb_id>` becomes a tabbed view (Documents / Folders / Settings) with a Tauri-backed folder picker.

**Tech Stack:** FastAPI · async SQLite (motor_compat) · Pydantic v2 · APScheduler · all-MiniLM-L6-v2 ONNX embeddings · React 19 · Tauri v2 (`tauri-plugin-dialog`) · Playwright e2e.

**Reference spec:** `docs/superpowers/specs/2026-04-30-personal-docs-folder-rag-design.md`

**Branch:** `feat/p2.5-3-personal-docs-folder-rag` — cut from `main` after the current `feat/p2.5-2-knowledge-base-rag` branch is merged.

---

## File Structure

**New backend files**

| Path | Purpose |
|---|---|
| `backend/models/personal_docs_models.py` | Pydantic v2 request/response models for folder sources, index jobs |
| `backend/repositories/folder_source_repository.py` | CRUD over `kb_folder_sources` collection |
| `backend/repositories/index_job_repository.py` | CRUD over `kb_index_jobs` collection |
| `backend/services/folder_walker.py` | Pure functions: walk a path, apply globs, classify diffs |
| `backend/services/personal_docs_service.py` | Orchestrator — walk → plan → friction-modal → execute |
| `backend/services/personal_docs_scheduler.py` | 60s tick that enqueues incremental jobs for due mappings |
| `backend/routers/personal_docs.py` | REST + SSE endpoints |
| `backend/tests/test_folder_walker.py` | Unit tests for walker |
| `backend/tests/test_personal_docs_service.py` | Unit tests for orchestrator (full + incremental + cancel) |
| `backend/tests/test_personal_docs_router.py` | API contract tests |
| `backend/tests/test_agent_runner_kb.py` | KB binding override semantics |

**Modified backend files**

| Path | Change |
|---|---|
| `backend/services/rag_service.py` | Add `ingest_from_path()` + `delete_for_source()` |
| `backend/repositories/document_repository.py` | Add `list_for_source`, `get_by_source_path`, `delete_for_source` |
| `backend/services/workspace/agent_runner.py` | KB retrieval injection into system prompt |
| `backend/routers/knowledge_base.py` | Documents response carries `source_type`, `source_id`, `abs_path`, `source_label` |
| `backend/routers/crews.py` + `backend/models/crew_models.py` | Add `knowledge_base_ids: list[str]` |
| `backend/repositories/workspace_agent_repository.py` (or model) | Add `knowledge_base_ids` field |
| `backend/app.py` | Register new router; start/stop `PersonalDocsScheduler` |
| `backend/settings.py` | New env defaults |

**New frontend files**

| Path | Purpose |
|---|---|
| `frontend/src/lib/api/personal-docs-client.ts` | Typed API client |
| `frontend/src/lib/tauri-fs.ts` | `pickFolder()` wrapper around `tauri-plugin-dialog` |
| `frontend/src/components/knowledge/folders-tab.tsx` | Folder list + actions |
| `frontend/src/components/knowledge/add-folder-modal.tsx` | Pick + configure + kick off |
| `frontend/src/components/knowledge/sync-progress-panel.tsx` | Live job progress + friction confirm |
| `frontend/src/components/knowledge/folder-row.tsx` | One mapping in the list |
| `frontend/src/components/shared/kb-multi-select.tsx` | Reusable for crew + agent forms |
| `frontend/tests/e2e/personal-docs-folder.spec.ts` | E2E covering add → confirm → query |

**Modified frontend files**

| Path | Change |
|---|---|
| `frontend/src/routes/knowledge.tsx` | Restructure detail view into tabs |
| `frontend/src/components/crews/crew-builder.tsx` | Knowledge multi-select on Details step |
| `frontend/src/components/workspace/agent-details.tsx` | Knowledge multi-select |
| `frontend/src-tauri/Cargo.toml`, `frontend/src-tauri/Cargo.lock` | `tauri-plugin-dialog` if not already present |
| `frontend/src-tauri/capabilities/default.json` | `dialog:allow-open` |
| `frontend/src-tauri/src/main.rs` | `tauri::Builder::default().plugin(tauri_plugin_dialog::init())` |

**Docs**

| Path | Change |
|---|---|
| `CLAUDE.md` | One-paragraph addition under "Knowledge Base / RAG" describing folder mapping |
| `docs/user-guide/...` | New page on Personal Docs (linked from index) |
| `TODO.md` / `README.md` | Mention shipped feature |

---

## Task 1: Branch + Pydantic models

**Files:**
- Create: `backend/models/personal_docs_models.py`

- [ ] **Step 1: Cut the feature branch off `main` (or off the current feature branch if KB is not yet merged)**

```bash
git checkout main
git pull
git checkout -b feat/p2.5-3-personal-docs-folder-rag
```

If the user is still on `feat/p2.5-2-knowledge-base-rag` and has not merged it, cut off that branch instead so the new work stacks on KB.

- [ ] **Step 2: Create the models file**

```python
# backend/models/personal_docs_models.py
"""Pydantic v2 models for Personal Docs folder mappings + index jobs."""
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

DEFAULT_EXCLUDE_GLOBS: List[str] = [
    "**/.git/**", "**/node_modules/**", "**/__pycache__/**",
    "**/.venv/**", "**/venv/**", "**/dist/**", "**/build/**",
    "**/.next/**", "**/.turbo/**", "**/.cache/**", "**/.idea/**",
    "**/.vscode/**", "**/target/**", "**/out/**", "**/coverage/**",
    "**/Thumbs.db", "**/.DS_Store", "**/.*",
]

SUPPORTED_FOLDER_EXTS = {
    ".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".rtf", ".csv", ".json",
}

ScheduleLiteral = Literal["manual", "1h", "6h", "24h"]
JobStatusLiteral = Literal[
    "queued", "walking", "awaiting_confirmation",
    "running", "done", "error", "cancelled",
]
JobKindLiteral = Literal["full_sync", "incremental", "delete_source"]
SourceStatusLiteral = Literal["active", "paused", "error"]


class FolderSourceCreate(BaseModel):
    path: str
    label: Optional[str] = None
    include_globs: List[str] = Field(default_factory=lambda: ["**/*"])
    exclude_globs: List[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE_GLOBS))
    schedule: ScheduleLiteral = "manual"
    max_file_bytes: Optional[int] = None
    max_files: Optional[int] = None
    max_depth: Optional[int] = None


class FolderSourceUpdate(BaseModel):
    label: Optional[str] = None
    include_globs: Optional[List[str]] = None
    exclude_globs: Optional[List[str]] = None
    schedule: Optional[ScheduleLiteral] = None
    status: Optional[SourceStatusLiteral] = None
    max_file_bytes: Optional[int] = None
    max_files: Optional[int] = None
    max_depth: Optional[int] = None


class FolderSource(BaseModel):
    id: str
    kb_id: str
    path: str
    label: str
    include_globs: List[str]
    exclude_globs: List[str]
    schedule: ScheduleLiteral
    max_file_bytes: int
    max_files: int
    max_depth: int
    status: SourceStatusLiteral
    last_sync_at: Optional[str] = None
    last_sync_job_id: Optional[str] = None
    file_count: int = 0
    byte_count: int = 0
    error: Optional[str] = None
    created_at: str
    updated_at: str


class IndexJob(BaseModel):
    id: str
    kb_id: str
    source_id: str
    kind: JobKindLiteral
    status: JobStatusLiteral
    files_total: int = 0
    files_done: int = 0
    files_added: int = 0
    files_updated: int = 0
    files_removed: int = 0
    files_skipped: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    cancel_requested: bool = False
    created_at: str
```

- [ ] **Step 3: Commit**

```bash
git add backend/models/personal_docs_models.py
git commit -m "feat(personal-docs): pydantic models for folder sources + jobs"
```

---

## Task 2: Repositories (folder source + index job)

**Files:**
- Create: `backend/repositories/folder_source_repository.py`
- Create: `backend/repositories/index_job_repository.py`
- Create: `backend/tests/test_folder_source_repository.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_folder_source_repository.py
import pytest
from adapters.sqlite_adapter import SQLiteAdapter
from adapters.motor_compat import DatabaseProxy
from repositories.folder_source_repository import FolderSourceRepository


@pytest.mark.asyncio
async def test_create_then_list_for_kb(tmp_path):
    adapter = await SQLiteAdapter.connect(str(tmp_path / "t.db"))
    db = DatabaseProxy(adapter)
    repo = FolderSourceRepository(db)

    src = await repo.create_source(
        kb_id="kb1", path="C:/x", label="X",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual", max_file_bytes=1024, max_files=10, max_depth=5,
    )
    assert src["kb_id"] == "kb1"
    assert src["status"] == "active"
    items = await repo.list_for_kb("kb1")
    assert len(items) == 1 and items[0]["path"] == "C:/x"
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_due_for_schedule(tmp_path):
    adapter = await SQLiteAdapter.connect(str(tmp_path / "t.db"))
    db = DatabaseProxy(adapter)
    repo = FolderSourceRepository(db)
    s1 = await repo.create_source(kb_id="kb1", path="C:/a", label="a",
        include_globs=["**/*"], exclude_globs=[], schedule="1h",
        max_file_bytes=1, max_files=1, max_depth=1)
    s2 = await repo.create_source(kb_id="kb1", path="C:/b", label="b",
        include_globs=["**/*"], exclude_globs=[], schedule="manual",
        max_file_bytes=1, max_files=1, max_depth=1)
    due = await repo.list_due_for_sync()
    assert s1["_id"] in {d["_id"] for d in due}
    assert s2["_id"] not in {d["_id"] for d in due}
    await adapter.disconnect()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_folder_source_repository.py -v
```

Expected: FAIL — module `repositories.folder_source_repository` not found.

- [ ] **Step 3: Implement `FolderSourceRepository`**

```python
# backend/repositories/folder_source_repository.py
"""CRUD over kb_folder_sources."""
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository
from models.personal_docs_models import DEFAULT_EXCLUDE_GLOBS

_INTERVALS = {"1h": 3600, "6h": 6 * 3600, "24h": 24 * 3600}


class FolderSourceRepository(BaseRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "kb_folder_sources")

    async def create_source(
        self, *, kb_id: str, path: str, label: str,
        include_globs: List[str], exclude_globs: List[str],
        schedule: str, max_file_bytes: int, max_files: int, max_depth: int,
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        doc = {
            "_id": str(uuid.uuid4()),
            "kb_id": kb_id,
            "path": path,
            "label": label,
            "include_globs": include_globs,
            "exclude_globs": exclude_globs,
            "schedule": schedule,
            "max_file_bytes": max_file_bytes,
            "max_files": max_files,
            "max_depth": max_depth,
            "status": "active",
            "last_sync_at": None,
            "last_sync_job_id": None,
            "file_count": 0,
            "byte_count": 0,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(doc)
        return doc

    async def list_for_kb(self, kb_id: str) -> List[Dict[str, Any]]:
        return await self.get_all(filter={"kb_id": kb_id}, limit=200,
                                  sort=[("created_at", -1)])

    async def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"_id": source_id})

    async def update_source(self, source_id: str, update: Dict[str, Any]) -> None:
        update = {**update, "updated_at": datetime.utcnow().isoformat()}
        await self.collection.update_one({"_id": source_id}, {"$set": update})

    async def delete_source(self, source_id: str) -> None:
        await self.collection.delete_one({"_id": source_id})

    async def delete_for_kb(self, kb_id: str) -> int:
        return await self.delete_many({"kb_id": kb_id})

    async def list_due_for_sync(self) -> List[Dict[str, Any]]:
        """Return active mappings whose schedule != manual and are due."""
        now = datetime.utcnow()
        all_sources = await self.get_all(
            filter={"status": "active"}, limit=500
        )
        due: List[Dict[str, Any]] = []
        for s in all_sources:
            sched = s.get("schedule", "manual")
            if sched not in _INTERVALS:
                continue
            last = s.get("last_sync_at")
            if last is None:
                due.append(s)
                continue
            try:
                last_dt = datetime.fromisoformat(last)
            except Exception:
                due.append(s)
                continue
            if now - last_dt >= timedelta(seconds=_INTERVALS[sched]):
                due.append(s)
        return due
```

- [ ] **Step 4: Implement `IndexJobRepository`**

```python
# backend/repositories/index_job_repository.py
"""CRUD + status transitions over kb_index_jobs."""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class IndexJobRepository(BaseRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "kb_index_jobs")

    async def create_job(
        self, *, kb_id: str, source_id: str, kind: str
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        doc = {
            "_id": str(uuid.uuid4()),
            "kb_id": kb_id,
            "source_id": source_id,
            "kind": kind,
            "status": "queued",
            "files_total": 0,
            "files_done": 0,
            "files_added": 0,
            "files_updated": 0,
            "files_removed": 0,
            "files_skipped": 0,
            "bytes_total": 0,
            "bytes_done": 0,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "cancel_requested": False,
            "created_at": now,
        }
        await self.collection.insert_one(doc)
        return doc

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"_id": job_id})

    async def patch(self, job_id: str, update: Dict[str, Any]) -> None:
        await self.collection.update_one({"_id": job_id}, {"$set": update})

    async def request_cancel(self, job_id: str) -> None:
        await self.patch(job_id, {"cancel_requested": True})

    async def running_for_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one(
            {"source_id": source_id,
             "status": {"$in": ["queued", "walking", "awaiting_confirmation", "running"]}}
        )

    async def list_for_source(self, source_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return await self.get_all(filter={"source_id": source_id}, limit=limit,
                                  sort=[("created_at", -1)])

    async def reset_orphans(self) -> int:
        """Mark `running`/`walking` jobs as `error="interrupted"` (called on startup)."""
        return await self.collection.update_many(
            {"status": {"$in": ["walking", "running"]}},
            {"$set": {"status": "error", "error": "interrupted",
                      "finished_at": datetime.utcnow().isoformat()}},
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_folder_source_repository.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/repositories/folder_source_repository.py \
        backend/repositories/index_job_repository.py \
        backend/tests/test_folder_source_repository.py
git commit -m "feat(personal-docs): folder source + index job repositories"
```

---

## Task 3: Folder walker (pure functions)

**Files:**
- Create: `backend/services/folder_walker.py`
- Create: `backend/tests/test_folder_walker.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_folder_walker.py
from pathlib import Path
import pytest

from services.folder_walker import walk_folder, classify_diffs, FileCandidate


def _touch(p: Path, body: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_walk_respects_extension_filter(tmp_path):
    _touch(tmp_path / "doc.md", "# md")
    _touch(tmp_path / "image.png")
    _touch(tmp_path / "sub" / "note.txt", "n")
    out, capped = walk_folder(
        str(tmp_path),
        include_globs=["**/*"], exclude_globs=[],
        max_file_bytes=10_000, max_files=100, max_depth=10,
    )
    paths = sorted(c.abs_path for c in out)
    assert any(p.endswith("doc.md") for p in paths)
    assert any(p.endswith("note.txt") for p in paths)
    assert not any(p.endswith("image.png") for p in paths)
    assert not capped


def test_walk_respects_exclude_globs(tmp_path):
    _touch(tmp_path / "keep.md")
    _touch(tmp_path / "node_modules" / "lib" / "x.md")
    out, _ = walk_folder(
        str(tmp_path),
        include_globs=["**/*"], exclude_globs=["**/node_modules/**"],
        max_file_bytes=10_000, max_files=100, max_depth=10,
    )
    paths = [c.abs_path for c in out]
    assert any("keep.md" in p for p in paths)
    assert not any("node_modules" in p for p in paths)


def test_walk_respects_max_depth(tmp_path):
    _touch(tmp_path / "a.md")
    _touch(tmp_path / "x" / "y" / "z" / "deep.md")
    out, _ = walk_folder(
        str(tmp_path), include_globs=["**/*"], exclude_globs=[],
        max_file_bytes=10_000, max_files=100, max_depth=2,
    )
    paths = [c.abs_path for c in out]
    assert any("a.md" in p for p in paths)
    assert not any("deep.md" in p for p in paths)


def test_walk_skips_oversized_files(tmp_path):
    _touch(tmp_path / "big.txt", "x" * 5_000)
    _touch(tmp_path / "small.txt", "x")
    out, _ = walk_folder(
        str(tmp_path), include_globs=["**/*"], exclude_globs=[],
        max_file_bytes=1_000, max_files=100, max_depth=10,
    )
    paths = [c.abs_path for c in out]
    assert any("small.txt" in p for p in paths)
    assert not any("big.txt" in p for p in paths)


def test_walk_caps_at_max_files(tmp_path):
    for i in range(20):
        _touch(tmp_path / f"f{i}.txt", "y")
    out, capped = walk_folder(
        str(tmp_path), include_globs=["**/*"], exclude_globs=[],
        max_file_bytes=100, max_files=5, max_depth=10,
    )
    assert len(out) == 5
    assert capped is True


def test_classify_diffs_new_updated_removed_unchanged():
    cands = [
        FileCandidate(abs_path="/a.md", size=10, mtime=1.0, ext=".md"),
        FileCandidate(abs_path="/b.md", size=20, mtime=2.0, ext=".md"),
        FileCandidate(abs_path="/c.md", size=30, mtime=3.0, ext=".md"),
    ]
    existing = {
        "/a.md": {"size_bytes": 10, "mtime": 1.0, "_id": "doc-a"},
        "/c.md": {"size_bytes": 999, "mtime": 3.0, "_id": "doc-c"},  # size diff
        "/d.md": {"size_bytes": 1, "mtime": 1.0, "_id": "doc-d"},    # gone
    }
    plan = classify_diffs(cands, existing)
    assert {c.abs_path for c in plan.new} == {"/b.md"}
    assert {c.abs_path for c in plan.updated} == {"/c.md"}
    assert plan.removed_doc_ids == ["doc-d"]
    assert plan.unchanged_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_folder_walker.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement the walker**

```python
# backend/services/folder_walker.py
"""Pure functions: walk a folder, apply globs, classify diffs against
existing kb_documents. Synchronous — caller dispatches via asyncio.to_thread."""
import os
import fnmatch
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Dict, Iterable, List, Tuple

from models.personal_docs_models import SUPPORTED_FOLDER_EXTS


@dataclass
class FileCandidate:
    abs_path: str
    size: int
    mtime: float
    ext: str


@dataclass
class DiffPlan:
    new: List[FileCandidate] = field(default_factory=list)
    updated: List[FileCandidate] = field(default_factory=list)
    removed_doc_ids: List[str] = field(default_factory=list)
    unchanged_count: int = 0


def _matches_any(rel: str, patterns: Iterable[str]) -> bool:
    posix = rel.replace(os.sep, "/")
    for p in patterns:
        if fnmatch.fnmatch(posix, p):
            return True
        # fnmatch doesn't expand `**`; collapse for the common case
        if "**" in p and fnmatch.fnmatch(posix, p.replace("**/", "")):
            return True
    return False


def walk_folder(
    root: str,
    *, include_globs: List[str], exclude_globs: List[str],
    max_file_bytes: int, max_files: int, max_depth: int,
) -> Tuple[List[FileCandidate], bool]:
    """Walk `root` and return (candidates, capped).

    `capped` is True if we stopped because `max_files` was reached.
    """
    root_p = os.path.abspath(root)
    out: List[FileCandidate] = []
    root_depth = root_p.count(os.sep)

    for dirpath, dirnames, filenames in os.walk(root_p, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root_p)
        depth = 0 if rel_dir in (".", "") else rel_dir.count(os.sep) + 1
        if depth > max_depth:
            dirnames[:] = []
            continue
        # Filter directories in-place to honour exclude_globs and skip hidden
        kept_dirs = []
        for d in dirnames:
            sub_rel = os.path.normpath(os.path.join(rel_dir, d))
            if d.startswith(".") or _matches_any(sub_rel + "/", exclude_globs) \
               or _matches_any(sub_rel, exclude_globs):
                continue
            kept_dirs.append(d)
        dirnames[:] = kept_dirs

        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED_FOLDER_EXTS:
                continue
            rel = os.path.normpath(os.path.join(rel_dir, name)) if rel_dir not in (".", "") else name
            if include_globs and not _matches_any(rel, include_globs):
                continue
            if _matches_any(rel, exclude_globs):
                continue
            abs_path = os.path.join(dirpath, name)
            try:
                st = os.stat(abs_path)
            except OSError:
                continue
            if st.st_size > max_file_bytes:
                continue
            out.append(FileCandidate(
                abs_path=abs_path, size=st.st_size,
                mtime=st.st_mtime, ext=ext,
            ))
            if len(out) >= max_files:
                return out, True
    return out, False


def classify_diffs(
    candidates: List[FileCandidate],
    existing_by_path: Dict[str, Dict],
) -> DiffPlan:
    """Compare a fresh walk vs. existing kb_documents (keyed by abs_path)."""
    plan = DiffPlan()
    seen: set = set()
    for c in candidates:
        seen.add(c.abs_path)
        prev = existing_by_path.get(c.abs_path)
        if prev is None:
            plan.new.append(c)
        elif (
            int(prev.get("size_bytes", 0)) != int(c.size)
            or float(prev.get("mtime", 0.0) or 0.0) != float(c.mtime)
        ):
            plan.updated.append(c)
        else:
            plan.unchanged_count += 1
    for path, doc in existing_by_path.items():
        if path not in seen:
            plan.removed_doc_ids.append(doc["_id"])
    return plan
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_folder_walker.py -v
```

Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/folder_walker.py backend/tests/test_folder_walker.py
git commit -m "feat(personal-docs): folder walker + diff classifier"
```

---

## Task 4: Extend RAGService + DocumentRepository for path-based ingest

**Files:**
- Modify: `backend/services/rag_service.py`
- Modify: `backend/repositories/document_repository.py`
- Create: `backend/tests/test_rag_ingest_from_path.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_rag_ingest_from_path.py
import os
import pytest
from adapters.sqlite_adapter import SQLiteAdapter
from adapters.motor_compat import DatabaseProxy
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from repositories.document_repository import DocumentRepository
from repositories.chunk_repository import ChunkRepository
from services.rag_service import RAGService


@pytest.mark.asyncio
async def test_ingest_from_path_stores_source_metadata(tmp_path):
    adapter = await SQLiteAdapter.connect(str(tmp_path / "t.db"))
    db = DatabaseProxy(adapter)
    kb_repo = KnowledgeBaseRepository(db); doc_repo = DocumentRepository(db)
    chunk_repo = ChunkRepository(db); rag = RAGService(kb_repo, doc_repo, chunk_repo)
    await db["knowledge_bases"].insert_one({"_id": "kb1", "name": "kb",
        "embedding_model": "all-MiniLM-L6-v2", "embedding_dim": 384,
        "doc_count": 0, "chunk_count": 0,
        "created_at": "2026-04-30T00:00:00", "updated_at": "2026-04-30T00:00:00"})

    file_path = tmp_path / "note.md"
    file_path.write_text("# Hello\nworld " * 50, encoding="utf-8")

    stats = await rag.ingest_from_path(
        kb_id="kb1", source_id="src1",
        abs_path=str(file_path), label_of_source="My Notes",
    )
    assert stats["chunks"] >= 1

    docs = await db["kb_documents"].find({"kb_id": "kb1"}).to_list(length=10)
    assert len(docs) == 1
    d = docs[0]
    assert d["source_type"] == "folder"
    assert d["source_id"] == "src1"
    assert d["abs_path"] == str(file_path)
    assert d["mtime"] is not None
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_delete_for_source_removes_docs_and_chunks(tmp_path):
    adapter = await SQLiteAdapter.connect(str(tmp_path / "t.db"))
    db = DatabaseProxy(adapter)
    kb_repo = KnowledgeBaseRepository(db); doc_repo = DocumentRepository(db)
    chunk_repo = ChunkRepository(db); rag = RAGService(kb_repo, doc_repo, chunk_repo)
    await db["knowledge_bases"].insert_one({"_id": "kb1", "name": "x",
        "embedding_model": "all-MiniLM-L6-v2", "embedding_dim": 384,
        "doc_count": 0, "chunk_count": 0,
        "created_at": "2026-04-30T00:00:00", "updated_at": "2026-04-30T00:00:00"})

    f = tmp_path / "n.md"; f.write_text("hi", encoding="utf-8")
    await rag.ingest_from_path(kb_id="kb1", source_id="src1",
        abs_path=str(f), label_of_source="X")
    deleted_chunks = await rag.delete_for_source("kb1", "src1")
    assert deleted_chunks >= 1
    remaining = await db["kb_documents"].find({"source_id": "src1"}).to_list(length=10)
    assert remaining == []
    await adapter.disconnect()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_rag_ingest_from_path.py -v
```

Expected: FAIL — `RAGService.ingest_from_path` and `delete_for_source` don't exist.

- [ ] **Step 3: Add `list_for_source`/`delete_for_source` helpers to DocumentRepository**

Append to `backend/repositories/document_repository.py`:

```python
    async def list_for_source(self, source_id: str) -> List[Dict[str, Any]]:
        return await self.get_all(
            filter={"source_id": source_id}, limit=10000,
            sort=[("abs_path", 1)],
        )

    async def list_paths_for_source(self, source_id: str) -> Dict[str, Dict[str, Any]]:
        items = await self.list_for_source(source_id)
        return {i["abs_path"]: i for i in items if i.get("abs_path")}

    async def delete_for_source(self, source_id: str) -> int:
        return await self.delete_many({"source_id": source_id})
```

- [ ] **Step 4: Add `ingest_from_path` + `delete_for_source` to `RAGService`**

In `backend/services/rag_service.py`, add at the bottom of the class (and add `import os, hashlib` to the imports):

```python
    async def ingest_from_path(
        self, *, kb_id: str, source_id: str, abs_path: str,
        label_of_source: str, existing_doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Read a file from disk and ingest. If `existing_doc_id` is set,
        replace its chunks (treat as updated)."""
        with open(abs_path, "rb") as fh:
            content = fh.read()
        st = os.stat(abs_path)
        content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        filename = os.path.basename(abs_path)

        if existing_doc_id:
            await self.chunk_repo.delete_for_document(existing_doc_id)
            await self.doc_repo.delete(existing_doc_id)

        now = datetime.utcnow().isoformat()
        doc_id = str(uuid.uuid4())
        doc = {
            "_id": doc_id, "kb_id": kb_id,
            "filename": filename,
            "mime_type": "application/octet-stream",
            "size_bytes": st.st_size,
            "page_count": 0, "chunk_count": 0,
            "status": "pending", "error": None,
            "source_type": "folder", "source_id": source_id,
            "source_label": label_of_source,
            "abs_path": abs_path, "mtime": st.st_mtime,
            "content_hash": content_hash,
            "created_at": now, "updated_at": now,
        }
        await self.doc_repo.collection.insert_one(doc)
        return await self.ingest_document(kb_id, doc_id, filename, content)

    async def delete_for_source(self, kb_id: str, source_id: str) -> int:
        docs = await self.doc_repo.list_for_source(source_id)
        chunks_deleted = 0
        for d in docs:
            chunks_deleted += await self.chunk_repo.delete_for_document(d["_id"])
        await self.doc_repo.delete_for_source(source_id)
        await self._refresh_kb_counts(kb_id)
        return chunks_deleted
```

Add `import hashlib, os` and `from typing import Optional` to the imports if missing.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_rag_ingest_from_path.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/rag_service.py \
        backend/repositories/document_repository.py \
        backend/tests/test_rag_ingest_from_path.py
git commit -m "feat(personal-docs): RAGService.ingest_from_path + delete_for_source"
```

---

## Task 5: PersonalDocsService (orchestrator)

**Files:**
- Create: `backend/services/personal_docs_service.py`
- Create: `backend/tests/test_personal_docs_service.py`

- [ ] **Step 1: Write failing tests covering full sync, friction confirm, incremental, cancel**

```python
# backend/tests/test_personal_docs_service.py
import asyncio
from pathlib import Path
import pytest

from adapters.sqlite_adapter import SQLiteAdapter
from adapters.motor_compat import DatabaseProxy
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from repositories.document_repository import DocumentRepository
from repositories.chunk_repository import ChunkRepository
from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from services.rag_service import RAGService
from services.personal_docs_service import PersonalDocsService


def _seed_kb(db, kb_id="kb1"):
    return db["knowledge_bases"].insert_one({"_id": kb_id, "name": "kb",
        "embedding_model": "all-MiniLM-L6-v2", "embedding_dim": 384,
        "doc_count": 0, "chunk_count": 0,
        "created_at": "2026-04-30T00:00:00",
        "updated_at": "2026-04-30T00:00:00"})


async def _wait_done(jobs, job_id, timeout=15.0):
    for _ in range(int(timeout * 10)):
        j = await jobs.get_job(job_id)
        if j and j["status"] in ("done", "error", "cancelled", "awaiting_confirmation"):
            return j
        await asyncio.sleep(0.1)
    raise AssertionError("job did not terminate in time")


@pytest.mark.asyncio
async def test_full_sync_indexes_files(tmp_path):
    adapter = await SQLiteAdapter.connect(str(tmp_path / "t.db"))
    db = DatabaseProxy(adapter)
    await _seed_kb(db)
    kb_repo = KnowledgeBaseRepository(db); doc_repo = DocumentRepository(db)
    chunk_repo = ChunkRepository(db); src_repo = FolderSourceRepository(db)
    job_repo = IndexJobRepository(db)
    rag = RAGService(kb_repo, doc_repo, chunk_repo)
    svc = PersonalDocsService(src_repo, job_repo, doc_repo, rag,
                              friction_threshold=10000)

    docs = tmp_path / "docs"
    (docs / "sub").mkdir(parents=True)
    (docs / "a.md").write_text("alpha")
    (docs / "sub" / "b.txt").write_text("bravo")

    src = await src_repo.create_source(kb_id="kb1", path=str(docs), label="docs",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual", max_file_bytes=10_000, max_files=100, max_depth=5)
    job = await svc.start_sync(source=src, kind="full_sync")
    final = await _wait_done(job_repo, job["_id"])
    assert final["status"] == "done"
    assert final["files_added"] == 2
    docs_in_kb = await doc_repo.list_for_kb("kb1")
    assert len(docs_in_kb) == 2
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_friction_modal_pauses_until_confirmed(tmp_path):
    adapter = await SQLiteAdapter.connect(str(tmp_path / "t.db"))
    db = DatabaseProxy(adapter); await _seed_kb(db)
    kb_repo = KnowledgeBaseRepository(db); doc_repo = DocumentRepository(db)
    chunk_repo = ChunkRepository(db); src_repo = FolderSourceRepository(db)
    job_repo = IndexJobRepository(db)
    rag = RAGService(kb_repo, doc_repo, chunk_repo)
    svc = PersonalDocsService(src_repo, job_repo, doc_repo, rag,
                              friction_threshold=1)  # trip on >1 file

    d = tmp_path / "d"; d.mkdir()
    for i in range(3): (d / f"f{i}.txt").write_text("x")
    src = await src_repo.create_source(kb_id="kb1", path=str(d), label="d",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual", max_file_bytes=1000, max_files=100, max_depth=5)

    job = await svc.start_sync(source=src, kind="full_sync")
    paused = await _wait_done(job_repo, job["_id"])
    assert paused["status"] == "awaiting_confirmation"
    assert paused["files_total"] == 3

    await svc.confirm(job_id=job["_id"])
    final = await _wait_done(job_repo, job["_id"])
    assert final["status"] == "done"
    assert final["files_added"] == 3
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_incremental_classifies_new_updated_removed(tmp_path):
    adapter = await SQLiteAdapter.connect(str(tmp_path / "t.db"))
    db = DatabaseProxy(adapter); await _seed_kb(db)
    kb_repo = KnowledgeBaseRepository(db); doc_repo = DocumentRepository(db)
    chunk_repo = ChunkRepository(db); src_repo = FolderSourceRepository(db)
    job_repo = IndexJobRepository(db)
    rag = RAGService(kb_repo, doc_repo, chunk_repo)
    svc = PersonalDocsService(src_repo, job_repo, doc_repo, rag,
                              friction_threshold=10000)

    d = tmp_path / "d"; d.mkdir()
    a = d / "a.md"; a.write_text("alpha"); b = d / "b.md"; b.write_text("bravo")
    src = await src_repo.create_source(kb_id="kb1", path=str(d), label="d",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual", max_file_bytes=1000, max_files=100, max_depth=5)
    job1 = await svc.start_sync(source=src, kind="full_sync")
    await _wait_done(job_repo, job1["_id"])

    a.write_text("alpha-edited-much-longer-content " * 5)
    (d / "c.md").write_text("charlie")
    b.unlink()

    refreshed = await src_repo.get_source(src["_id"])
    job2 = await svc.start_sync(source=refreshed, kind="incremental")
    final = await _wait_done(job_repo, job2["_id"])
    assert final["status"] == "done"
    assert final["files_added"] == 1
    assert final["files_updated"] == 1
    assert final["files_removed"] == 1
    await adapter.disconnect()


@pytest.mark.asyncio
async def test_concurrent_sync_returns_existing_running_job(tmp_path):
    adapter = await SQLiteAdapter.connect(str(tmp_path / "t.db"))
    db = DatabaseProxy(adapter); await _seed_kb(db)
    kb_repo = KnowledgeBaseRepository(db); doc_repo = DocumentRepository(db)
    chunk_repo = ChunkRepository(db); src_repo = FolderSourceRepository(db)
    job_repo = IndexJobRepository(db)
    rag = RAGService(kb_repo, doc_repo, chunk_repo)
    svc = PersonalDocsService(src_repo, job_repo, doc_repo, rag,
                              friction_threshold=1)

    d = tmp_path / "d"; d.mkdir()
    for i in range(3): (d / f"f{i}.txt").write_text("y")
    src = await src_repo.create_source(kb_id="kb1", path=str(d), label="d",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual", max_file_bytes=1000, max_files=100, max_depth=5)

    job = await svc.start_sync(source=src, kind="full_sync")
    again = await svc.start_sync(source=src, kind="full_sync")
    assert again["_id"] == job["_id"]
    await svc.confirm(job_id=job["_id"])
    await _wait_done(job_repo, job["_id"])
    await adapter.disconnect()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_personal_docs_service.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `PersonalDocsService`**

```python
# backend/services/personal_docs_service.py
"""Orchestrate folder-source sync: walk → plan → friction-pause → execute."""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from repositories.document_repository import DocumentRepository
from services.folder_walker import walk_folder, classify_diffs
from services.rag_service import RAGService

logger = logging.getLogger(__name__)


class PersonalDocsService:
    def __init__(
        self,
        src_repo: FolderSourceRepository,
        job_repo: IndexJobRepository,
        doc_repo: DocumentRepository,
        rag: RAGService,
        friction_threshold: int,
    ):
        self.src = src_repo
        self.jobs = job_repo
        self.docs = doc_repo
        self.rag = rag
        self.friction_threshold = friction_threshold
        # track in-flight asyncio.Tasks per job_id so cancel() can act
        self._tasks: Dict[str, asyncio.Task] = {}

    # ---- public API --------------------------------------------------------

    async def start_sync(self, *, source: Dict[str, Any], kind: str) -> Dict[str, Any]:
        existing = await self.jobs.running_for_source(source["_id"])
        if existing:
            return existing
        job = await self.jobs.create_job(
            kb_id=source["kb_id"], source_id=source["_id"], kind=kind,
        )
        task = asyncio.create_task(self._run(source, job))
        self._tasks[job["_id"]] = task
        return job

    async def confirm(self, *, job_id: str) -> None:
        await self.jobs.patch(job_id, {"status": "running"})

    async def cancel(self, *, job_id: str) -> None:
        await self.jobs.request_cancel(job_id)

    async def delete_source(self, *, source: Dict[str, Any]) -> None:
        # cancel any running job, drop docs+chunks, drop the source row
        running = await self.jobs.running_for_source(source["_id"])
        if running:
            await self.jobs.request_cancel(running["_id"])
            await asyncio.sleep(0.2)  # give the task a tick to exit
        await self.rag.delete_for_source(source["kb_id"], source["_id"])
        await self.src.delete_source(source["_id"])

    # ---- internal ---------------------------------------------------------

    async def _run(self, source: Dict[str, Any], job: Dict[str, Any]) -> None:
        job_id = job["_id"]
        try:
            await self.jobs.patch(job_id, {
                "status": "walking",
                "started_at": datetime.utcnow().isoformat(),
            })
            candidates, capped = await asyncio.to_thread(
                walk_folder,
                source["path"],
                include_globs=source["include_globs"],
                exclude_globs=source["exclude_globs"],
                max_file_bytes=source["max_file_bytes"],
                max_files=source["max_files"],
                max_depth=source["max_depth"],
            )
            if capped:
                await self._finish(job_id, status="error", error="cap_reached",
                                   files_total=len(candidates))
                return

            existing_by_path = await self.docs.list_paths_for_source(source["_id"])
            plan = classify_diffs(candidates, existing_by_path)
            total_work = len(plan.new) + len(plan.updated)
            files_total = len(candidates)
            await self.jobs.patch(job_id, {
                "files_total": files_total,
                "files_skipped": plan.unchanged_count,
                "bytes_total": sum(c.size for c in (plan.new + plan.updated)),
            })

            # Friction modal: only on full_sync above threshold
            if job["kind"] == "full_sync" and total_work > self.friction_threshold:
                await self.jobs.patch(job_id, {"status": "awaiting_confirmation"})
                if not await self._wait_for_confirm(job_id):
                    return  # cancelled

            if total_work == 0 and not plan.removed_doc_ids:
                await self._finish(job_id, status="done")
                await self._stamp_source(source, job_id, candidates)
                return

            await self.jobs.patch(job_id, {"status": "running"})

            files_added = files_updated = files_removed = 0
            bytes_done = 0
            for c in plan.new:
                if await self._cancel_check(job_id):
                    await self._finish(job_id, status="cancelled")
                    return
                try:
                    await self.rag.ingest_from_path(
                        kb_id=source["kb_id"], source_id=source["_id"],
                        abs_path=c.abs_path, label_of_source=source["label"],
                    )
                    files_added += 1
                    bytes_done += c.size
                except Exception:
                    logger.exception("ingest failed for %s", c.abs_path)
                await self._tick(job_id, files_done=files_added + files_updated,
                                 files_added=files_added,
                                 files_updated=files_updated,
                                 bytes_done=bytes_done)

            for c in plan.updated:
                if await self._cancel_check(job_id):
                    await self._finish(job_id, status="cancelled"); return
                prev = existing_by_path[c.abs_path]
                try:
                    await self.rag.ingest_from_path(
                        kb_id=source["kb_id"], source_id=source["_id"],
                        abs_path=c.abs_path, label_of_source=source["label"],
                        existing_doc_id=prev["_id"],
                    )
                    files_updated += 1
                    bytes_done += c.size
                except Exception:
                    logger.exception("re-ingest failed for %s", c.abs_path)
                await self._tick(job_id, files_done=files_added + files_updated,
                                 files_added=files_added,
                                 files_updated=files_updated,
                                 bytes_done=bytes_done)

            for doc_id in plan.removed_doc_ids:
                from repositories.chunk_repository import ChunkRepository
                # cleanest path: reuse rag pipeline
                docs_to_del = [doc_id]
                for did in docs_to_del:
                    await self.rag.chunk_repo.delete_for_document(did)
                    await self.docs.delete(did)
                files_removed += 1
                await self.jobs.patch(job_id, {"files_removed": files_removed})

            await self.rag._refresh_kb_counts(source["kb_id"])
            await self._stamp_source(source, job_id, candidates)
            await self._finish(job_id, status="done")
        except asyncio.CancelledError:
            await self._finish(job_id, status="cancelled"); raise
        except Exception as e:
            logger.exception("personal-docs sync failed for source %s", source.get("_id"))
            await self._finish(job_id, status="error", error=str(e))
        finally:
            self._tasks.pop(job_id, None)

    async def _wait_for_confirm(self, job_id: str) -> bool:
        while True:
            j = await self.jobs.get_job(job_id)
            if j is None: return False
            if j.get("cancel_requested"):
                await self._finish(job_id, status="cancelled"); return False
            if j["status"] == "running":
                return True
            await asyncio.sleep(0.2)

    async def _cancel_check(self, job_id: str) -> bool:
        j = await self.jobs.get_job(job_id)
        return bool(j and j.get("cancel_requested"))

    async def _tick(self, job_id: str, **fields) -> None:
        await self.jobs.patch(job_id, fields)

    async def _finish(self, job_id: str, *, status: str, error: Optional[str] = None,
                      **extra) -> None:
        update = {
            "status": status,
            "finished_at": datetime.utcnow().isoformat(),
        }
        if error is not None:
            update["error"] = error
        update.update(extra)
        await self.jobs.patch(job_id, update)

    async def _stamp_source(self, source, job_id, candidates) -> None:
        await self.src.update_source(source["_id"], {
            "last_sync_at": datetime.utcnow().isoformat(),
            "last_sync_job_id": job_id,
            "file_count": len(candidates),
            "byte_count": sum(c.size for c in candidates),
            "error": None,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_personal_docs_service.py -v
```

Expected: PASS (4 tests). Each takes 1–3 s because of real embeddings on tiny files.

- [ ] **Step 5: Commit**

```bash
git add backend/services/personal_docs_service.py \
        backend/tests/test_personal_docs_service.py
git commit -m "feat(personal-docs): orchestrator (walk → plan → friction → ingest)"
```

---

## Task 6: REST + SSE router

**Files:**
- Create: `backend/routers/personal_docs.py`
- Create: `backend/tests/test_personal_docs_router.py`
- Modify: `backend/settings.py`

- [ ] **Step 1: Add settings defaults**

Append to `backend/settings.py`:

```python
PERSONAL_DOCS_MAX_FILE_BYTES = int(os.getenv("PERSONAL_DOCS_MAX_FILE_BYTES", str(10 * 1024 * 1024)))
PERSONAL_DOCS_MAX_FILES = int(os.getenv("PERSONAL_DOCS_MAX_FILES", "5000"))
PERSONAL_DOCS_MAX_DEPTH = int(os.getenv("PERSONAL_DOCS_MAX_DEPTH", "10"))
PERSONAL_DOCS_FRICTION_THRESHOLD = int(os.getenv("PERSONAL_DOCS_FRICTION_THRESHOLD", "1000"))
PERSONAL_DOCS_SCHEDULER_TICK_SECONDS = int(os.getenv("PERSONAL_DOCS_SCHEDULER_TICK_SECONDS", "60"))
```

(If `import os` is not already at the top of `settings.py`, add it.)

- [ ] **Step 2: Implement the router**

```python
# backend/routers/personal_docs.py
"""REST + SSE for Personal Docs folder mappings."""
import asyncio
import json
import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from database import get_database
import settings
from models.personal_docs_models import (
    DEFAULT_EXCLUDE_GLOBS, FolderSourceCreate, FolderSourceUpdate,
)
from repositories.chunk_repository import ChunkRepository
from repositories.document_repository import DocumentRepository
from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services.personal_docs_service import PersonalDocsService
from services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/personal-docs", tags=["personal-docs"])


def _src_repo(db=Depends(get_database)) -> FolderSourceRepository:
    return FolderSourceRepository(db)


def _job_repo(db=Depends(get_database)) -> IndexJobRepository:
    return IndexJobRepository(db)


def _kb_repo(db=Depends(get_database)) -> KnowledgeBaseRepository:
    return KnowledgeBaseRepository(db)


def _doc_repo(db=Depends(get_database)) -> DocumentRepository:
    return DocumentRepository(db)


def _chunk_repo(db=Depends(get_database)) -> ChunkRepository:
    return ChunkRepository(db)


def _service(
    src=Depends(_src_repo), jobs=Depends(_job_repo),
    docs=Depends(_doc_repo), kb=Depends(_kb_repo), chunks=Depends(_chunk_repo),
) -> PersonalDocsService:
    rag = RAGService(kb, docs, chunks)
    return PersonalDocsService(
        src, jobs, docs, rag,
        friction_threshold=settings.PERSONAL_DOCS_FRICTION_THRESHOLD,
    )


# --------- Folder source CRUD --------------------------------------------

@router.get("/kbs/{kb_id}/folders")
async def list_folders(kb_id: str, src=Depends(_src_repo),
                       kb=Depends(_kb_repo)) -> Dict[str, Any]:
    if not await kb.exists_by_id(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    return {"items": await src.list_for_kb(kb_id)}


@router.post("/kbs/{kb_id}/folders")
async def create_folder(
    kb_id: str, payload: FolderSourceCreate,
    kb=Depends(_kb_repo), src=Depends(_src_repo),
    svc: PersonalDocsService = Depends(_service),
) -> Dict[str, Any]:
    if not await kb.exists_by_id(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    if not os.path.isdir(payload.path):
        raise HTTPException(400, f"Folder does not exist: {payload.path}")
    label = payload.label or os.path.basename(payload.path.rstrip("/\\")) or payload.path
    source = await src.create_source(
        kb_id=kb_id, path=payload.path, label=label,
        include_globs=payload.include_globs,
        exclude_globs=payload.exclude_globs or list(DEFAULT_EXCLUDE_GLOBS),
        schedule=payload.schedule,
        max_file_bytes=payload.max_file_bytes or settings.PERSONAL_DOCS_MAX_FILE_BYTES,
        max_files=payload.max_files or settings.PERSONAL_DOCS_MAX_FILES,
        max_depth=payload.max_depth or settings.PERSONAL_DOCS_MAX_DEPTH,
    )
    job = await svc.start_sync(source=source, kind="full_sync")
    return {"source": source, "job_id": job["_id"]}


@router.get("/folders/{source_id}")
async def get_folder(source_id: str, src=Depends(_src_repo)) -> Dict[str, Any]:
    s = await src.get_source(source_id)
    if not s:
        raise HTTPException(404, "Folder source not found")
    return {"item": s}


@router.put("/folders/{source_id}")
async def update_folder(source_id: str, payload: FolderSourceUpdate,
                        src=Depends(_src_repo)) -> Dict[str, Any]:
    s = await src.get_source(source_id)
    if not s:
        raise HTTPException(404, "Folder source not found")
    update = payload.model_dump(exclude_none=True)
    if not update:
        raise HTTPException(400, "Nothing to update")
    await src.update_source(source_id, update)
    return {"item": await src.get_source(source_id)}


@router.delete("/folders/{source_id}")
async def delete_folder(source_id: str,
                        src=Depends(_src_repo),
                        svc: PersonalDocsService = Depends(_service)) -> Dict[str, Any]:
    s = await src.get_source(source_id)
    if not s:
        raise HTTPException(404, "Folder source not found")
    await svc.delete_source(source=s)
    return {"deleted": True}


@router.post("/folders/{source_id}/sync")
async def sync_folder(source_id: str, src=Depends(_src_repo),
                      svc: PersonalDocsService = Depends(_service)) -> Dict[str, Any]:
    s = await src.get_source(source_id)
    if not s:
        raise HTTPException(404, "Folder source not found")
    job = await svc.start_sync(source=s, kind="incremental")
    return {"job_id": job["_id"], "status": job["status"]}


# --------- Jobs ----------------------------------------------------------

@router.get("/folders/{source_id}/jobs")
async def list_jobs(source_id: str, jobs=Depends(_job_repo)) -> Dict[str, Any]:
    return {"items": await jobs.list_for_source(source_id)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, jobs=Depends(_job_repo)) -> Dict[str, Any]:
    j = await jobs.get_job(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return {"item": j}


@router.post("/jobs/{job_id}/confirm")
async def confirm_job(job_id: str, jobs=Depends(_job_repo),
                      svc: PersonalDocsService = Depends(_service)) -> Dict[str, Any]:
    j = await jobs.get_job(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    if j["status"] != "awaiting_confirmation":
        raise HTTPException(409, f"Job is in status {j['status']}")
    await svc.confirm(job_id=job_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, svc: PersonalDocsService = Depends(_service),
                     jobs=Depends(_job_repo)) -> Dict[str, Any]:
    if not await jobs.get_job(job_id):
        raise HTTPException(404, "Job not found")
    await svc.cancel(job_id=job_id)
    return {"ok": True}


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str, jobs=Depends(_job_repo)) -> StreamingResponse:
    async def gen():
        last_payload = None
        for _ in range(60 * 60):  # cap stream at 1 hour of polling
            j = await jobs.get_job(job_id)
            if not j:
                yield f"event: error\ndata: {json.dumps({'error': 'not_found'})}\n\n"
                return
            payload = json.dumps({
                "id": j["_id"], "status": j["status"],
                "files_total": j.get("files_total", 0),
                "files_done": j.get("files_done", 0),
                "files_added": j.get("files_added", 0),
                "files_updated": j.get("files_updated", 0),
                "files_removed": j.get("files_removed", 0),
                "bytes_total": j.get("bytes_total", 0),
                "bytes_done": j.get("bytes_done", 0),
                "error": j.get("error"),
            })
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            if j["status"] in ("done", "error", "cancelled"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 3: Write a minimal contract test**

```python
# backend/tests/test_personal_docs_router.py
import pytest
from httpx import ASGITransport, AsyncClient

import app as app_module


@pytest.mark.asyncio
async def test_create_folder_404_for_unknown_kb(tmp_path, monkeypatch):
    # Boot app via TestClient lifespan; this hits real startup which seeds
    # SQLite under tmp data dir.
    monkeypatch.setenv("CONTEXTUAI_DB_PATH", str(tmp_path / "t.db"))
    async with AsyncClient(transport=ASGITransport(app=app_module.app),
                           base_url="http://test") as client:
        await app_module.startup_event()
        r = await client.post("/api/v1/personal-docs/kbs/missing/folders",
                              json={"path": str(tmp_path)})
        assert r.status_code == 404
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_personal_docs_router.py -v
```

Expected: PASS (after Task 7 wires the router into `app.py`).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/personal_docs.py backend/settings.py \
        backend/tests/test_personal_docs_router.py
git commit -m "feat(personal-docs): REST + SSE router"
```

---

## Task 7: Periodic scheduler + app.py wiring

**Files:**
- Create: `backend/services/personal_docs_scheduler.py`
- Modify: `backend/app.py`

- [ ] **Step 1: Implement the scheduler (mirrors `RedditPoller`)**

```python
# backend/services/personal_docs_scheduler.py
"""Tick every N seconds, enqueue incremental syncs for due folder mappings."""
import asyncio
import logging
from typing import Optional

import settings
from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from repositories.document_repository import DocumentRepository
from repositories.chunk_repository import ChunkRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services.personal_docs_service import PersonalDocsService
from services.rag_service import RAGService

logger = logging.getLogger(__name__)


class PersonalDocsScheduler:
    def __init__(self, db):
        self.db = db
        self._task: Optional[asyncio.Task] = None
        self._stopping = False
        self._tick = settings.PERSONAL_DOCS_SCHEDULER_TICK_SECONDS

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run())
        logger.info("PersonalDocsScheduler started (tick=%ss)", self._tick)

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
            self._task = None
        logger.info("PersonalDocsScheduler stopped")

    async def _run(self) -> None:
        src_repo = FolderSourceRepository(self.db)
        job_repo = IndexJobRepository(self.db)
        doc_repo = DocumentRepository(self.db)
        chunk_repo = ChunkRepository(self.db)
        kb_repo = KnowledgeBaseRepository(self.db)
        rag = RAGService(kb_repo, doc_repo, chunk_repo)
        svc = PersonalDocsService(
            src_repo, job_repo, doc_repo, rag,
            friction_threshold=settings.PERSONAL_DOCS_FRICTION_THRESHOLD,
        )

        while not self._stopping:
            try:
                due = await src_repo.list_due_for_sync()
                for src in due:
                    running = await job_repo.running_for_source(src["_id"])
                    if running:
                        continue
                    await svc.start_sync(source=src, kind="incremental")
            except Exception:
                logger.exception("PersonalDocsScheduler tick failed")
            await asyncio.sleep(self._tick)
```

- [ ] **Step 2: Wire into `app.py`**

Add to imports near the other router imports:

```python
from routers.personal_docs import router as personal_docs_router
```

Add after the existing `app.include_router(knowledge_base_router)`:

```python
app.include_router(personal_docs_router)
```

In the `startup_event()` function, after the existing `reddit_poller.start()` block, add:

```python
        from services.personal_docs_scheduler import PersonalDocsScheduler
        from repositories.index_job_repository import IndexJobRepository

        # Resurrect any "running"/"walking" jobs that were interrupted by a crash
        try:
            await IndexJobRepository(proxy).reset_orphans()
        except Exception:
            logger.exception("Failed to reset orphan index jobs")

        app.state.personal_docs_scheduler = PersonalDocsScheduler(proxy)
        await app.state.personal_docs_scheduler.start()
```

In `shutdown_event()`, add a stop block matching the Reddit one:

```python
    try:
        sched = getattr(app.state, "personal_docs_scheduler", None)
        if sched:
            await sched.stop()
    except Exception:
        logger.exception("Error stopping personal docs scheduler")
```

- [ ] **Step 3: Smoke-test backend boot**

```bash
cd backend && CONTEXTUAI_MODE=desktop python -c "import asyncio; import app as a; asyncio.run(a.startup_event()); print('ok')"
```

Expected: prints `ok` and the log shows `PersonalDocsScheduler started (tick=60s)`.

- [ ] **Step 4: Commit**

```bash
git add backend/services/personal_docs_scheduler.py backend/app.py
git commit -m "feat(personal-docs): periodic scheduler + app.py wiring"
```

---

## Task 8: Knowledge-base documents response carries source fields

**Files:**
- Modify: `backend/routers/knowledge_base.py`

- [ ] **Step 1: Update the documents endpoint to surface source metadata**

In `backend/routers/knowledge_base.py`, replace `list_documents` body so each item includes `source_type`, `source_id`, `source_label`, `abs_path` (defaulting `source_type` to `"upload"` for legacy rows):

```python
@router.get("/{kb_id}/documents")
async def list_documents(
    kb_id: str,
    kb_repo: KnowledgeBaseRepository = Depends(_kb_repo),
    doc_repo: DocumentRepository = Depends(_doc_repo),
) -> Dict[str, Any]:
    if not await kb_repo.exists_by_id(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    docs = await doc_repo.list_for_kb(kb_id)
    for d in docs:
        d.setdefault("source_type", "upload")
        d.setdefault("source_id", None)
        d.setdefault("source_label", None)
        d.setdefault("abs_path", None)
    return {"items": docs}
```

- [ ] **Step 2: Make sure delete cascades folder mappings**

In `delete_kb`, before deleting chunks/docs, also remove folder sources. Add at the top of the function:

```python
    from repositories.folder_source_repository import FolderSourceRepository
    src_repo = FolderSourceRepository(kb_repo.db)
    await src_repo.delete_for_kb(kb_id)
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/knowledge_base.py
git commit -m "feat(personal-docs): surface source fields on KB document list"
```

---

## Task 9: Crew + agent KB binding (model + agent runner)

**Files:**
- Modify: `backend/models/crew_models.py`
- Modify: `backend/repositories/workspace_agent_repository.py` (or `models/workspace_agent_models.py` — whichever exists)
- Modify: `backend/services/workspace/agent_runner.py`
- Create: `backend/tests/test_agent_runner_kb.py`

- [ ] **Step 1: Add `knowledge_base_ids` to crew + agent Pydantic models**

In `backend/models/crew_models.py`, add to the `Crew` / `CrewCreate` / `CrewUpdate` models (matching existing field style) — e.g. for each one:

```python
    knowledge_base_ids: List[str] = Field(default_factory=list)
```

(If the field is already optional in another shape, follow that pattern. The point is `knowledge_base_ids: list[str]` defaults to `[]` and round-trips through CRUD endpoints.)

For workspace agents: do the same in whichever Pydantic model represents an agent's persisted shape. Many of those already accept `extra = "allow"` — in that case the field doesn't need an explicit declaration to round-trip, but adding it makes the API contract explicit.

- [ ] **Step 2: Write failing test for agent runner injection**

```python
# backend/tests/test_agent_runner_kb.py
import pytest

from services.workspace.agent_runner import resolve_kb_ids


def test_agent_overrides_crew():
    assert resolve_kb_ids(
        agent={"knowledge_base_ids": ["a"]},
        crew={"knowledge_base_ids": ["b"]},
    ) == ["a"]


def test_agent_empty_falls_back_to_crew():
    assert resolve_kb_ids(
        agent={"knowledge_base_ids": []},
        crew={"knowledge_base_ids": ["c"]},
    ) == ["c"]


def test_both_empty_returns_empty():
    assert resolve_kb_ids(agent={}, crew={}) == []
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_agent_runner_kb.py -v
```

Expected: FAIL — `resolve_kb_ids` not defined.

- [ ] **Step 4: Add `resolve_kb_ids` and inject into the system prompt**

In `backend/services/workspace/agent_runner.py`, add at module scope:

```python
def resolve_kb_ids(*, agent: Dict[str, Any], crew: Dict[str, Any]) -> List[str]:
    """Per-agent KB binding overrides crew default. Empty == no injection."""
    a = list(agent.get("knowledge_base_ids") or [])
    if a:
        return a
    return list(crew.get("knowledge_base_ids") or [])
```

In `_run_agent_sdk`, between line ~186 (`system_prompt = agent_blueprint.get(...)`) and line ~225 (`options = ClaudeAgentOptions(...)`), add:

```python
            crew_doc = context.get("crew") or {}
            kb_ids = resolve_kb_ids(agent=agent_blueprint, crew=crew_doc)
            if kb_ids:
                from repositories.knowledge_base_repository import KnowledgeBaseRepository
                from repositories.document_repository import DocumentRepository
                from repositories.chunk_repository import ChunkRepository
                from services.rag_service import RAGService
                from database import get_database

                _db = await get_database()
                _rag = RAGService(KnowledgeBaseRepository(_db),
                                  DocumentRepository(_db), ChunkRepository(_db))
                citations: list = []
                for kb_id in kb_ids:
                    citations.extend(await _rag.query(kb_id, prompt, top_k=3))
                # de-dupe by (doc_id, chunk_index), keep top 8 by score
                seen, deduped = set(), []
                for c in sorted(citations, key=lambda x: -x["score"]):
                    key = (c["doc_id"], c["chunk_index"])
                    if key in seen: continue
                    seen.add(key); deduped.append(c)
                    if len(deduped) >= 8: break
                if deduped:
                    system_prompt = (RAGService.format_context(deduped)
                                     + "\n\n" + system_prompt)
```

(The `context` dict already exists in `_run_agent_sdk`; the orchestrator must pass `context["crew"] = crew_doc`. If it does not, also patch `services/workspace/orchestrator.py` at the point where it builds `context` for an agent run.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_agent_runner_kb.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/models/crew_models.py \
        backend/services/workspace/agent_runner.py \
        backend/tests/test_agent_runner_kb.py
git commit -m "feat(personal-docs): crew/agent KB binding + agent runner injection"
```

---

## Task 10: Tauri folder picker bridge

**Files:**
- Modify: `frontend/src-tauri/Cargo.toml`
- Modify: `frontend/src-tauri/src/main.rs`
- Modify: `frontend/src-tauri/capabilities/default.json`
- Create: `frontend/src/lib/tauri-fs.ts`

- [ ] **Step 1: Verify whether `tauri-plugin-dialog` is already a dependency**

```bash
grep -n "tauri-plugin-dialog" C:/Users/nagen/Projects/contextuai-solo/frontend/src-tauri/Cargo.toml || echo "not found"
```

If not found, add it:

```toml
# frontend/src-tauri/Cargo.toml — under [dependencies]
tauri-plugin-dialog = "2"
```

- [ ] **Step 2: Register the plugin in `main.rs`**

```rust
// frontend/src-tauri/src/main.rs — inside fn main(), in the Builder chain
tauri::Builder::default()
    .plugin(tauri_plugin_dialog::init())
    // ... rest of existing builder calls
```

(If the chain is already long, place `.plugin(tauri_plugin_dialog::init())` near the other `.plugin(...)` calls.)

- [ ] **Step 3: Allow the dialog open command in capabilities**

```jsonc
// frontend/src-tauri/capabilities/default.json — add to "permissions"
{
  // ...existing fields...
  "permissions": [
    // existing permissions
    "dialog:allow-open"
  ]
}
```

- [ ] **Step 4: Frontend wrapper**

```ts
// frontend/src/lib/tauri-fs.ts
import { open } from "@tauri-apps/plugin-dialog";

export function isTauri(): boolean {
  return Boolean((window as unknown as { __TAURI__?: unknown }).__TAURI__);
}

/** Open a native folder picker. Returns the selected absolute path or null. */
export async function pickFolder(): Promise<string | null> {
  if (!isTauri()) return null;
  const result = await open({ directory: true, multiple: false });
  if (!result) return null;
  return Array.isArray(result) ? (result[0] ?? null) : result;
}
```

- [ ] **Step 5: Install the JS plugin if not present**

```bash
cd frontend && npm i @tauri-apps/plugin-dialog
```

- [ ] **Step 6: Smoke-test the build**

```bash
cd frontend && npm run build
```

Expected: TypeScript compile clean, Vite build clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src-tauri/Cargo.toml frontend/src-tauri/Cargo.lock \
        frontend/src-tauri/src/main.rs \
        frontend/src-tauri/capabilities/default.json \
        frontend/src/lib/tauri-fs.ts \
        frontend/package.json frontend/package-lock.json
git commit -m "feat(personal-docs): tauri folder picker + JS wrapper"
```

---

## Task 11: Frontend API client

**Files:**
- Create: `frontend/src/lib/api/personal-docs-client.ts`

- [ ] **Step 1: Implement the typed client**

```ts
// frontend/src/lib/api/personal-docs-client.ts
import { api, getApiBaseUrl } from "@/lib/transport";

export type Schedule = "manual" | "1h" | "6h" | "24h";
export type SourceStatus = "active" | "paused" | "error";
export type JobStatus =
  | "queued" | "walking" | "awaiting_confirmation"
  | "running" | "done" | "error" | "cancelled";

export interface FolderSource {
  id: string;
  kb_id: string;
  path: string;
  label: string;
  include_globs: string[];
  exclude_globs: string[];
  schedule: Schedule;
  max_file_bytes: number;
  max_files: number;
  max_depth: number;
  status: SourceStatus;
  last_sync_at: string | null;
  last_sync_job_id: string | null;
  file_count: number;
  byte_count: number;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface IndexJob {
  id: string;
  kb_id: string;
  source_id: string;
  kind: "full_sync" | "incremental" | "delete_source";
  status: JobStatus;
  files_total: number;
  files_done: number;
  files_added: number;
  files_updated: number;
  files_removed: number;
  files_skipped: number;
  bytes_total: number;
  bytes_done: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

function normalizeSource(raw: Record<string, unknown>): FolderSource {
  return { ...(raw as unknown as FolderSource),
    id: (raw.id as string) || (raw._id as string) };
}

function normalizeJob(raw: Record<string, unknown>): IndexJob {
  return { ...(raw as unknown as IndexJob),
    id: (raw.id as string) || (raw._id as string) };
}

export async function listFolders(kbId: string): Promise<FolderSource[]> {
  const { data } = await api.get<{ items: Record<string, unknown>[] }>(
    `/personal-docs/kbs/${kbId}/folders`,
  );
  return (data.items || []).map(normalizeSource);
}

export async function createFolder(kbId: string, payload: {
  path: string; label?: string; schedule?: Schedule;
  include_globs?: string[]; exclude_globs?: string[];
  max_file_bytes?: number; max_files?: number; max_depth?: number;
}): Promise<{ source: FolderSource; jobId: string }> {
  const { data } = await api.post<{ source: Record<string, unknown>; job_id: string }>(
    `/personal-docs/kbs/${kbId}/folders`, payload);
  return { source: normalizeSource(data.source), jobId: data.job_id };
}

export async function updateFolder(
  sourceId: string, payload: Partial<Pick<FolderSource,
    "label" | "schedule" | "status" | "include_globs" | "exclude_globs"
    | "max_file_bytes" | "max_files" | "max_depth">>,
): Promise<FolderSource> {
  const { data } = await api.put<{ item: Record<string, unknown> }>(
    `/personal-docs/folders/${sourceId}`, payload);
  return normalizeSource(data.item);
}

export async function deleteFolder(sourceId: string): Promise<boolean> {
  const { ok } = await api.delete<{ deleted: boolean }>(
    `/personal-docs/folders/${sourceId}`);
  return ok;
}

export async function syncFolder(sourceId: string): Promise<{ jobId: string }> {
  const { data } = await api.post<{ job_id: string }>(
    `/personal-docs/folders/${sourceId}/sync`, {});
  return { jobId: data.job_id };
}

export async function getJob(jobId: string): Promise<IndexJob> {
  const { data } = await api.get<{ item: Record<string, unknown> }>(
    `/personal-docs/jobs/${jobId}`);
  return normalizeJob(data.item);
}

export async function confirmJob(jobId: string): Promise<void> {
  await api.post(`/personal-docs/jobs/${jobId}/confirm`, {});
}

export async function cancelJob(jobId: string): Promise<void> {
  await api.post(`/personal-docs/jobs/${jobId}/cancel`, {});
}

/** Subscribe to live job progress via SSE. Returns a cleanup fn. */
export async function subscribeJob(
  jobId: string, onUpdate: (j: IndexJob) => void,
): Promise<() => void> {
  const baseUrl = await getApiBaseUrl();
  const es = new EventSource(`${baseUrl}/personal-docs/jobs/${jobId}/stream`);
  es.onmessage = (e) => {
    try { onUpdate(JSON.parse(e.data) as IndexJob); } catch {/* skip */}
  };
  return () => es.close();
}
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api/personal-docs-client.ts
git commit -m "feat(personal-docs): frontend API client"
```

---

## Task 12: Folders tab + add-folder modal + sync progress panel

**Files:**
- Create: `frontend/src/components/knowledge/folders-tab.tsx`
- Create: `frontend/src/components/knowledge/add-folder-modal.tsx`
- Create: `frontend/src/components/knowledge/sync-progress-panel.tsx`
- Create: `frontend/src/components/knowledge/folder-row.tsx`
- Modify: `frontend/src/routes/knowledge.tsx`

- [ ] **Step 1: Restructure `/knowledge/<id>` detail view into tabs**

In `frontend/src/routes/knowledge.tsx`, where the right-pane currently renders documents directly, wrap it in a tab control. New tab keys: `documents` | `folders` | `settings`. Default `documents`. Render the existing document table inside `documents`, mount `<FoldersTab kbId={...} />` inside `folders`, and a stub for `settings` (KB rename + advanced caps later).

```tsx
type Tab = "documents" | "folders" | "settings";
const [tab, setTab] = useState<Tab>("documents");

// inside the right-pane JSX, above the existing list:
<div className="flex gap-2 border-b border-neutral-200 dark:border-neutral-800">
  <button onClick={() => setTab("documents")}
          className={cn("px-3 py-2 text-sm",
            tab === "documents" && "border-b-2 border-primary")}>Documents</button>
  <button onClick={() => setTab("folders")}
          className={cn("px-3 py-2 text-sm",
            tab === "folders" && "border-b-2 border-primary")}>Folders</button>
  <button onClick={() => setTab("settings")}
          className={cn("px-3 py-2 text-sm",
            tab === "settings" && "border-b-2 border-primary")}>Settings</button>
</div>
{tab === "documents" && <DocumentsList kbId={selectedId} ... />}
{tab === "folders" && <FoldersTab kbId={selectedId} />}
{tab === "settings" && <KbSettingsTab kbId={selectedId} />}
```

(If the existing inline JSX is too tangled to extract `DocumentsList`, leave the documents JSX inline guarded by `tab === "documents"`.)

- [ ] **Step 2: `folder-row.tsx`**

```tsx
// frontend/src/components/knowledge/folder-row.tsx
import { Folder, RefreshCw, Pause, Play, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { FolderSource } from "@/lib/api/personal-docs-client";

export function FolderRow({ source, onSync, onTogglePause, onDelete }: {
  source: FolderSource;
  onSync: () => void; onTogglePause: () => void; onDelete: () => void;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-neutral-200 dark:border-neutral-800">
      <div className="flex items-center gap-3 min-w-0">
        <Folder className="h-4 w-4 text-neutral-500 shrink-0" />
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{source.label}</div>
          <div className="text-xs text-neutral-500 truncate" title={source.path}>{source.path}</div>
          <div className="text-[11px] text-neutral-400">
            {source.file_count} files · {source.schedule}
            {source.last_sync_at && ` · synced ${new Date(source.last_sync_at).toLocaleString()}`}
            {source.status === "error" && ` · ⚠ ${source.error ?? "error"}`}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="sm" onClick={onSync} title="Sync now">
          <RefreshCw className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="sm" onClick={onTogglePause}
                title={source.status === "paused" ? "Resume" : "Pause"}>
          {source.status === "paused" ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
        </Button>
        <Button variant="ghost" size="sm" onClick={onDelete} title="Remove">
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: `sync-progress-panel.tsx`**

```tsx
// frontend/src/components/knowledge/sync-progress-panel.tsx
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  cancelJob, confirmJob, getJob, subscribeJob, type IndexJob,
} from "@/lib/api/personal-docs-client";

export function SyncProgressPanel({ jobId, onDone }: {
  jobId: string; onDone: (job: IndexJob) => void;
}) {
  const [job, setJob] = useState<IndexJob | null>(null);

  useEffect(() => {
    let cleanup: (() => void) | null = null;
    let cancelled = false;
    (async () => {
      setJob(await getJob(jobId));
      cleanup = await subscribeJob(jobId, (j) => {
        if (cancelled) return;
        setJob(j);
        if (j.status === "done" || j.status === "error" || j.status === "cancelled") {
          onDone(j);
        }
      });
    })();
    return () => { cancelled = true; cleanup?.(); };
  }, [jobId, onDone]);

  if (!job) return <div className="p-4 text-sm text-neutral-500">Starting…</div>;

  if (job.status === "awaiting_confirmation") {
    const mb = (job.bytes_total / (1024 * 1024)).toFixed(1);
    const eta = Math.ceil(job.files_total * 2 / 60); // ~30 chunks/sec rough
    return (
      <div className="p-4 space-y-3">
        <p className="text-sm">
          Indexing this folder will process <strong>{job.files_total}</strong> files
          (~{mb} MB). Estimated time: ~{eta} min.
        </p>
        <div className="flex gap-2">
          <Button onClick={() => confirmJob(jobId)}>Continue</Button>
          <Button variant="outline" onClick={() => cancelJob(jobId)}>Cancel</Button>
        </div>
      </div>
    );
  }

  const total = job.files_total || 1;
  const pct = Math.min(100, Math.round((job.files_done / total) * 100));
  const label = `${job.status} · ${job.files_done}/${job.files_total} files`;
  return (
    <div className="p-4 space-y-2">
      <div className="text-sm">{label}</div>
      <div className="w-full h-2 bg-neutral-200 dark:bg-neutral-800 rounded">
        <div className="h-2 bg-primary rounded" style={{ width: `${pct}%` }} />
      </div>
      {(job.status === "running" || job.status === "walking") && (
        <Button size="sm" variant="outline" onClick={() => cancelJob(jobId)}>Cancel</Button>
      )}
      {job.status === "error" && (
        <p className="text-sm text-red-500">Error: {job.error}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: `add-folder-modal.tsx`**

```tsx
// frontend/src/components/knowledge/add-folder-modal.tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { isTauri, pickFolder } from "@/lib/tauri-fs";
import {
  createFolder, type Schedule, type FolderSource,
} from "@/lib/api/personal-docs-client";
import { SyncProgressPanel } from "./sync-progress-panel";

export function AddFolderModal({ kbId, open, onClose, onAdded }: {
  kbId: string; open: boolean;
  onClose: () => void;
  onAdded: (source: FolderSource) => void;
}) {
  const [path, setPath] = useState("");
  const [label, setLabel] = useState("");
  const [schedule, setSchedule] = useState<Schedule>("manual");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const onPick = async () => {
    const p = await pickFolder();
    if (p) setPath(p);
  };

  const onSubmit = async () => {
    setSubmitting(true); setError(null);
    try {
      const { source, jobId } = await createFolder(kbId, {
        path, label: label || undefined, schedule,
      });
      setActiveJobId(jobId);
      onAdded(source);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <div className="p-5 w-[420px] space-y-4">
        {!activeJobId ? (
          <>
            <h3 className="text-base font-semibold">Add folder</h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-neutral-500">Folder</label>
                <div className="flex gap-2">
                  <Input value={path} onChange={(e) => setPath(e.target.value)}
                         placeholder="C:\\Users\\me\\Documents\\Notes"
                         readOnly={isTauri()} />
                  <Button onClick={onPick} type="button">Browse…</Button>
                </div>
                {!isTauri() && (
                  <p className="text-[11px] text-amber-600 mt-1">
                    Native folder picker only available in the desktop build — type the absolute path.
                  </p>
                )}
              </div>
              <div>
                <label className="text-xs text-neutral-500">Label</label>
                <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Notes" />
              </div>
              <div>
                <label className="text-xs text-neutral-500">Schedule</label>
                <div className="flex gap-2 mt-1">
                  {(["manual", "1h", "6h", "24h"] as Schedule[]).map((s) => (
                    <Button key={s} type="button"
                      variant={schedule === s ? "default" : "outline"}
                      size="sm" onClick={() => setSchedule(s)}>{s}</Button>
                  ))}
                </div>
              </div>
              {error && <p className="text-sm text-red-500">{error}</p>}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button disabled={!path || submitting} onClick={onSubmit}>
                {submitting ? "Adding…" : "Add"}
              </Button>
            </div>
          </>
        ) : (
          <SyncProgressPanel jobId={activeJobId} onDone={() => onClose()} />
        )}
      </div>
    </Dialog>
  );
}
```

- [ ] **Step 5: `folders-tab.tsx`**

```tsx
// frontend/src/components/knowledge/folders-tab.tsx
import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  deleteFolder, listFolders, syncFolder, updateFolder,
  type FolderSource,
} from "@/lib/api/personal-docs-client";
import { FolderRow } from "./folder-row";
import { AddFolderModal } from "./add-folder-modal";
import { SyncProgressPanel } from "./sync-progress-panel";

export function FoldersTab({ kbId }: { kbId: string }) {
  const [items, setItems] = useState<FolderSource[]>([]);
  const [adding, setAdding] = useState(false);
  const [activeSync, setActiveSync] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setItems(await listFolders(kbId));
  }, [kbId]);

  useEffect(() => { void reload(); }, [reload]);

  const onSync = async (s: FolderSource) => {
    const { jobId } = await syncFolder(s.id);
    setActiveSync(jobId);
  };
  const onTogglePause = async (s: FolderSource) => {
    await updateFolder(s.id, { status: s.status === "paused" ? "active" : "paused" });
    await reload();
  };
  const onDelete = async (s: FolderSource) => {
    if (!window.confirm(`Remove "${s.label}" and its indexed content?`)) return;
    await deleteFolder(s.id); await reload();
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between p-4">
        <p className="text-sm text-neutral-500">
          Map folders to auto-index supported files (PDF, DOCX, TXT, MD, HTML, CSV, JSON).
        </p>
        <Button onClick={() => setAdding(true)}>
          <Plus className="h-4 w-4 mr-1" /> Add folder
        </Button>
      </div>
      {items.length === 0 && (
        <div className="px-4 py-12 text-center text-sm text-neutral-500">
          No folder mappings yet. Click "Add folder" to start.
        </div>
      )}
      <div>
        {items.map((s) => (
          <FolderRow key={s.id} source={s}
            onSync={() => onSync(s)}
            onTogglePause={() => onTogglePause(s)}
            onDelete={() => onDelete(s)} />
        ))}
      </div>
      {activeSync && (
        <div className="border-t border-neutral-200 dark:border-neutral-800">
          <SyncProgressPanel jobId={activeSync}
            onDone={() => { setActiveSync(null); void reload(); }} />
        </div>
      )}
      <AddFolderModal kbId={kbId} open={adding}
        onClose={() => { setAdding(false); void reload(); }}
        onAdded={() => void reload()} />
    </div>
  );
}
```

- [ ] **Step 6: Type-check + dev build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/knowledge.tsx \
        frontend/src/components/knowledge/folders-tab.tsx \
        frontend/src/components/knowledge/folder-row.tsx \
        frontend/src/components/knowledge/add-folder-modal.tsx \
        frontend/src/components/knowledge/sync-progress-panel.tsx
git commit -m "feat(personal-docs): folders tab + add-folder modal + progress panel"
```

---

## Task 13: KB multi-select for crew + agent forms

**Files:**
- Create: `frontend/src/components/shared/kb-multi-select.tsx`
- Modify: `frontend/src/components/crews/crew-builder.tsx`
- Modify: `frontend/src/components/workspace/agent-details.tsx`

- [ ] **Step 1: Reusable multi-select component**

```tsx
// frontend/src/components/shared/kb-multi-select.tsx
import { useEffect, useState } from "react";
import { Check } from "lucide-react";

import { listKnowledgeBases, type KnowledgeBase } from "@/lib/api/knowledge-base-client";
import { cn } from "@/lib/utils";

export function KbMultiSelect({ value, onChange, placeholder = "Select knowledge bases" }: {
  value: string[]; onChange: (ids: string[]) => void; placeholder?: string;
}) {
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  useEffect(() => { void listKnowledgeBases().then(setKbs); }, []);
  const toggle = (id: string) =>
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  return (
    <div className="border border-neutral-200 dark:border-neutral-800 rounded">
      {kbs.length === 0 && (
        <p className="px-3 py-2 text-sm text-neutral-500">No knowledge bases yet.</p>
      )}
      {kbs.map((kb) => {
        const on = value.includes(kb.id);
        return (
          <button key={kb.id} type="button" onClick={() => toggle(kb.id)}
            className={cn("w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-neutral-50 dark:hover:bg-neutral-900",
              on && "bg-primary/5")}>
            <span>{kb.name}</span>
            {on && <Check className="h-4 w-4 text-primary" />}
          </button>
        );
      })}
      {kbs.length === 0 && <span className="sr-only">{placeholder}</span>}
    </div>
  );
}
```

- [ ] **Step 2: Wire into crew builder Step 1 (Details)**

In `crew-builder.tsx`, find the Details step's JSX (where `name`, `description`, `model` inputs live). Add a "Knowledge" section:

```tsx
import { KbMultiSelect } from "@/components/shared/kb-multi-select";
// ...inside the Details step's render:
<div className="space-y-1">
  <label className="text-sm font-medium">Knowledge</label>
  <p className="text-xs text-neutral-500">
    Optional. Selected KBs will be queried before each agent turn and citations injected.
  </p>
  <KbMultiSelect
    value={form.knowledge_base_ids ?? []}
    onChange={(ids) => setForm({ ...form, knowledge_base_ids: ids })}
  />
</div>
```

(Add `knowledge_base_ids: string[]` to whatever the form type alias is and ensure it's sent in the create/update payloads.)

- [ ] **Step 3: Wire into agent details panel**

In `agent-details.tsx`, add a "Knowledge" section below the existing model selector (or wherever per-agent settings live), using the same `<KbMultiSelect>` against an `agent.knowledge_base_ids` field, and PUT the agent on save.

- [ ] **Step 4: Type-check + build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/kb-multi-select.tsx \
        frontend/src/components/crews/crew-builder.tsx \
        frontend/src/components/workspace/agent-details.tsx
git commit -m "feat(personal-docs): crew + agent KB multi-select"
```

---

## Task 14: E2E test (Playwright)

**Files:**
- Create: `frontend/tests/e2e/personal-docs-folder.spec.ts`

- [ ] **Step 1: Author the test**

```ts
// frontend/tests/e2e/personal-docs-folder.spec.ts
import { test, expect } from "@playwright/test";
import { mkdtempSync, writeFileSync, mkdirSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

test.describe("Personal Docs — folder mapping", () => {
  test("add folder, sync indexes files, document appears", async ({ page }) => {
    const dir = mkdtempSync(join(tmpdir(), "ctxai-personal-"));
    writeFileSync(join(dir, "alpha.md"), "# Alpha\nThe quick brown fox.");
    mkdirSync(join(dir, "sub"));
    writeFileSync(join(dir, "sub", "bravo.txt"), "Bravo content for retrieval.");

    await page.goto("/knowledge");
    // Create a KB
    await page.getByRole("button", { name: /new knowledge base/i }).click();
    await page.getByLabel(/name/i).fill("Personal Test");
    await page.getByRole("button", { name: /^create$/i }).click();
    await expect(page.getByText("Personal Test")).toBeVisible();

    // Open Folders tab
    await page.getByRole("button", { name: /^folders$/i }).click();
    await page.getByRole("button", { name: /add folder/i }).click();

    // Dev-mode fallback path input (Tauri picker not driveable from Playwright)
    await page.getByPlaceholder(/Documents/).fill(dir);
    await page.getByRole("button", { name: /^add$/i }).click();

    // Wait for job to finish
    await expect(page.getByText(/done|2 files|files_added/i)).toBeVisible({ timeout: 30_000 });

    // Documents tab shows ingested files
    await page.getByRole("button", { name: /^documents$/i }).click();
    await expect(page.getByText("alpha.md")).toBeVisible();
    await expect(page.getByText("bravo.txt")).toBeVisible();
  });
});
```

- [ ] **Step 2: Run the test**

```bash
cd frontend && npx playwright test tests/e2e/personal-docs-folder.spec.ts
```

Expected: PASS. (If the dev fallback warning blocks `add` due to readOnly: in dev `isTauri()` returns false so the Input is editable.)

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/personal-docs-folder.spec.ts
git commit -m "test(personal-docs): e2e for folder mapping → ingest"
```

---

## Task 15: Documentation + final verify

**Files:**
- Modify: `CLAUDE.md`
- Create: `docs/user-guide/personal-docs.md`
- Modify: `docs/user-guide/index.md` (or whatever it's called)
- Modify: `README.md`
- Modify: `TODO.md`

- [ ] **Step 1: Add a paragraph to CLAUDE.md**

Under the "Knowledge Base / RAG" section, append:

```md
**Personal Docs (folder mappings).** A KB can also have folder sources: pick any folder via the Tauri folder picker, the backend walks it, classifies new/updated/removed files vs. existing docs, and re-uses the same chunk + embed + query pipeline. Manual "Sync now" or scheduled background sync (1h/6h/24h). Backed by `kb_folder_sources` + `kb_index_jobs` collections; orchestrated by `services/personal_docs_service.py`. Crews and agents bind to KBs via `knowledge_base_ids: string[]` (per-agent overrides crew default); the agent runner queries those KBs and prepends citations to the system prompt.
```

- [ ] **Step 2: Write user-guide page**

`docs/user-guide/personal-docs.md`: how to add a folder, supported extensions, schedule options, friction-modal explanation, how to bind a KB to a crew/agent. Keep it under one page.

- [ ] **Step 3: Add link in user-guide index**

Append a `Personal Docs` entry to the user-guide index page (link to the new doc).

- [ ] **Step 4: Update README + TODO**

In README.md: add Personal Docs as a feature bullet. In TODO.md: mark this feature as shipped under the appropriate section (P2.5-3) and remove related open items.

- [ ] **Step 5: Run full backend + frontend test suites**

```bash
cd backend && pytest tests/ -v
cd frontend && npx tsc --noEmit && npm run build
cd frontend && npx playwright test
```

Expected: all green.

- [ ] **Step 6: Final commit + push**

```bash
git add CLAUDE.md README.md TODO.md docs/user-guide/personal-docs.md docs/user-guide/index.md
git commit -m "docs(personal-docs): user guide + CLAUDE.md + README"
git push -u origin feat/p2.5-3-personal-docs-folder-rag
```

- [ ] **Step 7: Open PR (use the project's `/pr` skill if available)**

Use the `/pr` skill to run the full PR cycle (verify → tests → commit → push → open PR).

---

## Self-Review (already performed inline)

Coverage walk-through against the spec:

- §3 architecture diagram → Tasks 2, 3, 5, 6, 7, 10, 11, 12.
- §4 data model → Tasks 1, 2; doc extension covered in Task 4 (writes new fields) + Task 8 (read API).
- §5 sync semantics → Task 5 (walker, plan, friction, cancel) + Task 7 (scheduler).
- §6 backend API → Task 6 covers all routes including SSE + confirm + cancel.
- §7 frontend tabs + add-folder modal + progress panel + native picker → Tasks 10, 11, 12.
- §8 agent runner integration → Task 9.
- §9 error handling → addressed throughout: 404s in router, `cap_reached`, interrupted-jobs reset on startup (Task 7 step 2), error cascade through `_finish`.
- §10 settings & defaults → Task 6 step 1.
- §11 privacy → folder picker in Task 10; default exclude list in Task 1.
- §12 testing → Tasks 2, 3, 4, 5, 6, 9, 14.
- §13 out of scope → respected (no live watcher, no code-aware chunking).
- §14 migration → forward-compat reads in Task 8 (`setdefault("source_type", "upload")`) and Pydantic defaults in Task 9.
- §15 rollout → branch creation in Task 1, push + PR in Task 15.

No placeholders, no "TBD", no "similar to Task N" without code. Type names round-trip (`FolderSource`, `IndexJob`, `FileCandidate`, `DiffPlan`, `resolve_kb_ids`, `KbMultiSelect`).
