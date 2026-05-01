"""Tests for FolderSourceRepository + IndexJobRepository."""
import sys
import os
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository


# ---------------------------------------------------------------------------
# FolderSourceRepository
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_then_list_for_kb(db_proxy):
    repo = FolderSourceRepository(db_proxy)
    src = await repo.create_source(
        kb_id="kb1",
        path="C:/x",
        label="X",
        include_globs=["**/*"],
        exclude_globs=[],
        schedule="manual",
        max_file_bytes=1024,
        max_files=10,
        max_depth=5,
    )
    assert src["kb_id"] == "kb1"
    assert src["status"] == "active"
    items = await repo.list_for_kb("kb1")
    assert len(items) == 1
    assert items[0]["path"] == "C:/x"


@pytest.mark.asyncio
async def test_due_for_schedule(db_proxy):
    repo = FolderSourceRepository(db_proxy)
    s1 = await repo.create_source(
        kb_id="kb1", path="C:/a", label="a",
        include_globs=["**/*"], exclude_globs=[], schedule="1h",
        max_file_bytes=1, max_files=1, max_depth=1,
    )
    s2 = await repo.create_source(
        kb_id="kb1", path="C:/b", label="b",
        include_globs=["**/*"], exclude_globs=[], schedule="manual",
        max_file_bytes=1, max_files=1, max_depth=1,
    )
    due = await repo.list_due_for_sync()
    due_ids = {d["_id"] for d in due}
    assert s1["_id"] in due_ids  # never synced + 1h schedule => due
    assert s2["_id"] not in due_ids  # manual schedule => never auto-due


@pytest.mark.asyncio
async def test_due_skips_recently_synced(db_proxy):
    repo = FolderSourceRepository(db_proxy)
    src = await repo.create_source(
        kb_id="kb1", path="C:/a", label="a",
        include_globs=["**/*"], exclude_globs=[], schedule="1h",
        max_file_bytes=1, max_files=1, max_depth=1,
    )
    recent = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
    await repo.update_source(src["_id"], {"last_sync_at": recent})
    due = await repo.list_due_for_sync()
    assert src["_id"] not in {d["_id"] for d in due}


@pytest.mark.asyncio
async def test_update_and_delete(db_proxy):
    repo = FolderSourceRepository(db_proxy)
    src = await repo.create_source(
        kb_id="kb1", path="C:/a", label="a",
        include_globs=["**/*"], exclude_globs=[], schedule="manual",
        max_file_bytes=1, max_files=1, max_depth=1,
    )
    await repo.update_source(src["_id"], {"label": "renamed", "status": "paused"})
    fetched = await repo.get_source(src["_id"])
    assert fetched["label"] == "renamed"
    assert fetched["status"] == "paused"

    await repo.delete_source(src["_id"])
    assert await repo.get_source(src["_id"]) is None


@pytest.mark.asyncio
async def test_delete_for_kb(db_proxy):
    repo = FolderSourceRepository(db_proxy)
    await repo.create_source(
        kb_id="kb1", path="C:/a", label="a",
        include_globs=["**/*"], exclude_globs=[], schedule="manual",
        max_file_bytes=1, max_files=1, max_depth=1,
    )
    await repo.create_source(
        kb_id="kb2", path="C:/b", label="b",
        include_globs=["**/*"], exclude_globs=[], schedule="manual",
        max_file_bytes=1, max_files=1, max_depth=1,
    )
    deleted = await repo.delete_for_kb("kb1")
    assert deleted == 1
    assert len(await repo.list_for_kb("kb1")) == 0
    assert len(await repo.list_for_kb("kb2")) == 1


# ---------------------------------------------------------------------------
# IndexJobRepository
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_and_get_job(db_proxy):
    repo = IndexJobRepository(db_proxy)
    job = await repo.create_job(kb_id="kb1", source_id="src1", kind="full_sync")
    assert job["status"] == "queued"
    fetched = await repo.get_job(job["_id"])
    assert fetched["kind"] == "full_sync"


@pytest.mark.asyncio
async def test_running_for_source_returns_active_job(db_proxy):
    repo = IndexJobRepository(db_proxy)
    j1 = await repo.create_job(kb_id="kb1", source_id="src1", kind="full_sync")
    await repo.patch(j1["_id"], {"status": "done"})
    j2 = await repo.create_job(kb_id="kb1", source_id="src1", kind="incremental")
    await repo.patch(j2["_id"], {"status": "running"})
    running = await repo.running_for_source("src1")
    assert running is not None
    assert running["_id"] == j2["_id"]


@pytest.mark.asyncio
async def test_request_cancel_sets_flag(db_proxy):
    repo = IndexJobRepository(db_proxy)
    job = await repo.create_job(kb_id="kb1", source_id="src1", kind="full_sync")
    await repo.request_cancel(job["_id"])
    fetched = await repo.get_job(job["_id"])
    assert fetched["cancel_requested"] is True


@pytest.mark.asyncio
async def test_reset_orphans_marks_running_jobs_interrupted(db_proxy):
    repo = IndexJobRepository(db_proxy)
    j1 = await repo.create_job(kb_id="kb1", source_id="src1", kind="full_sync")
    await repo.patch(j1["_id"], {"status": "running"})
    j2 = await repo.create_job(kb_id="kb1", source_id="src1", kind="full_sync")
    await repo.patch(j2["_id"], {"status": "done"})
    count = await repo.reset_orphans()
    assert count == 1
    assert (await repo.get_job(j1["_id"]))["status"] == "error"
    assert (await repo.get_job(j2["_id"]))["status"] == "done"
