"""Integration tests for PersonalDocsService.

These exercise the real embedding pipeline and so are skipped if the
bundled all-MiniLM-L6-v2 ONNX model is not on disk.
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from repositories.chunk_repository import ChunkRepository
from repositories.document_repository import DocumentRepository
from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services.personal_docs_service import PersonalDocsService
from services.rag_service import RAGService


def _embedding_model_available() -> bool:
    base = os.environ.get(
        "MODELS_DIR",
        os.path.join(Path.home(), ".contextuai-solo", "models"),
    )
    return (Path(base) / "embedding" / "all-MiniLM-L6-v2" / "model.onnx").exists()


needs_embeddings = pytest.mark.skipif(
    not _embedding_model_available(),
    reason="all-MiniLM-L6-v2 ONNX model not present",
)


async def _seed_kb(db, kb_id="kb1") -> None:
    await db["knowledge_bases"].insert_one(
        {
            "_id": kb_id,
            "name": "kb",
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dim": 384,
            "doc_count": 0,
            "chunk_count": 0,
            "created_at": "2026-04-30T00:00:00",
            "updated_at": "2026-04-30T00:00:00",
        }
    )


def _make_service(db, friction_threshold: int) -> PersonalDocsService:
    rag = RAGService(
        KnowledgeBaseRepository(db),
        DocumentRepository(db),
        ChunkRepository(db),
    )
    return PersonalDocsService(
        FolderSourceRepository(db),
        IndexJobRepository(db),
        DocumentRepository(db),
        rag,
        friction_threshold=friction_threshold,
    )


async def _wait_for(jobs: IndexJobRepository, job_id: str, *, terminal_states):
    for _ in range(150):  # ~15 s
        j = await jobs.get_job(job_id)
        if j and j["status"] in terminal_states:
            return j
        await asyncio.sleep(0.1)
    raise AssertionError(
        f"job {job_id} did not reach {terminal_states} in time"
    )


@needs_embeddings
@pytest.mark.asyncio
async def test_full_sync_indexes_files(tmp_path, db_proxy):
    await _seed_kb(db_proxy)
    src_repo = FolderSourceRepository(db_proxy)
    job_repo = IndexJobRepository(db_proxy)
    doc_repo = DocumentRepository(db_proxy)
    svc = _make_service(db_proxy, friction_threshold=10_000)

    docs = tmp_path / "docs"
    (docs / "sub").mkdir(parents=True)
    (docs / "a.md").write_text("alpha document content")
    (docs / "sub" / "b.txt").write_text("bravo document content")

    src = await src_repo.create_source(
        kb_id="kb1", path=str(docs), label="docs",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual",
        max_file_bytes=10_000, max_files=100, max_depth=5,
    )
    job = await svc.start_sync(source=src, kind="full_sync")
    final = await _wait_for(job_repo, job["_id"],
                            terminal_states={"done", "error", "cancelled"})
    assert final["status"] == "done", final
    assert final["files_added"] == 2
    docs_in_kb = await doc_repo.list_for_kb("kb1")
    assert len(docs_in_kb) == 2


@needs_embeddings
@pytest.mark.asyncio
async def test_friction_modal_pauses_until_confirmed(tmp_path, db_proxy):
    await _seed_kb(db_proxy)
    src_repo = FolderSourceRepository(db_proxy)
    job_repo = IndexJobRepository(db_proxy)
    svc = _make_service(db_proxy, friction_threshold=1)  # trip on >1 file

    d = tmp_path / "d"
    d.mkdir()
    for i in range(3):
        (d / f"f{i}.txt").write_text("content " * 5)
    src = await src_repo.create_source(
        kb_id="kb1", path=str(d), label="d",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual",
        max_file_bytes=1000, max_files=100, max_depth=5,
    )

    job = await svc.start_sync(source=src, kind="full_sync")
    paused = await _wait_for(
        job_repo, job["_id"],
        terminal_states={"awaiting_confirmation", "done", "error"},
    )
    assert paused["status"] == "awaiting_confirmation"
    assert paused["files_total"] == 3

    await svc.confirm(job_id=job["_id"])
    final = await _wait_for(
        job_repo, job["_id"],
        terminal_states={"done", "error", "cancelled"},
    )
    assert final["status"] == "done"
    assert final["files_added"] == 3


@needs_embeddings
@pytest.mark.asyncio
async def test_incremental_classifies_new_updated_removed(tmp_path, db_proxy):
    await _seed_kb(db_proxy)
    src_repo = FolderSourceRepository(db_proxy)
    job_repo = IndexJobRepository(db_proxy)
    svc = _make_service(db_proxy, friction_threshold=10_000)

    d = tmp_path / "d"
    d.mkdir()
    a = d / "a.md"; a.write_text("alpha original")
    b = d / "b.md"; b.write_text("bravo")
    src = await src_repo.create_source(
        kb_id="kb1", path=str(d), label="d",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual",
        max_file_bytes=2000, max_files=100, max_depth=5,
    )
    job1 = await svc.start_sync(source=src, kind="full_sync")
    await _wait_for(job_repo, job1["_id"],
                    terminal_states={"done", "error", "cancelled"})

    # Mutate the tree: change a, add c, remove b
    a.write_text("alpha edited and much longer body " * 3)
    (d / "c.md").write_text("charlie")
    b.unlink()
    # Bump mtime explicitly in case the FS timestamp didn't tick
    os.utime(a, None)

    refreshed = await src_repo.get_source(src["_id"])
    job2 = await svc.start_sync(source=refreshed, kind="incremental")
    final = await _wait_for(job_repo, job2["_id"],
                            terminal_states={"done", "error", "cancelled"})
    assert final["status"] == "done", final
    assert final["files_added"] == 1
    assert final["files_updated"] == 1
    assert final["files_removed"] == 1


@pytest.mark.asyncio
async def test_failed_ingest_surfaces_error_not_silent_done(tmp_path, db_proxy):
    """If every file fails to ingest (e.g. embedding model missing), the job
    must end in `error` with a message — not a silent `done` with 0 docs.

    Regression test for the packaged-build bug where the bundled embedding
    model was absent, so `ingest_from_path` raised FileNotFoundError for every
    file and the job reported "done, 0 docs of N".
    """
    await _seed_kb(db_proxy)
    src_repo = FolderSourceRepository(db_proxy)
    job_repo = IndexJobRepository(db_proxy)
    svc = _make_service(db_proxy, friction_threshold=10_000)

    async def _boom(*args, **kwargs):
        raise FileNotFoundError("ONNX model not found at /bundle/model.onnx")

    svc.rag.ingest_from_path = _boom  # type: ignore[assignment]

    d = tmp_path / "d"
    d.mkdir()
    for i in range(3):
        (d / f"f{i}.md").write_text("# heading\nbody text", encoding="utf-8")
    src = await src_repo.create_source(
        kb_id="kb1", path=str(d), label="d",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual",
        max_file_bytes=10_000, max_files=100, max_depth=5,
    )

    job = await svc.start_sync(source=src, kind="full_sync")
    final = await _wait_for(job_repo, job["_id"],
                            terminal_states={"done", "error", "cancelled"})

    assert final["status"] == "error", final
    assert final["files_added"] == 0
    assert final["files_failed"] == 3
    assert "ONNX model not found" in (final.get("error") or "")

    # The source row should also carry the error for the UI.
    refreshed = await src_repo.get_source(src["_id"])
    assert "ONNX model not found" in (refreshed.get("error") or "")


@needs_embeddings
@pytest.mark.asyncio
async def test_concurrent_sync_returns_existing_running_job(tmp_path, db_proxy):
    await _seed_kb(db_proxy)
    src_repo = FolderSourceRepository(db_proxy)
    job_repo = IndexJobRepository(db_proxy)
    svc = _make_service(db_proxy, friction_threshold=1)

    d = tmp_path / "d"
    d.mkdir()
    for i in range(3):
        (d / f"f{i}.txt").write_text("y")
    src = await src_repo.create_source(
        kb_id="kb1", path=str(d), label="d",
        include_globs=["**/*"], exclude_globs=[],
        schedule="manual",
        max_file_bytes=1000, max_files=100, max_depth=5,
    )

    job = await svc.start_sync(source=src, kind="full_sync")
    # Wait until the job is in the awaiting_confirmation state — that
    # guarantees it's still in the running set, so a second start_sync
    # should attach to the same job.
    await _wait_for(
        job_repo, job["_id"],
        terminal_states={"awaiting_confirmation", "done", "error"},
    )
    again = await svc.start_sync(source=src, kind="full_sync")
    assert again["_id"] == job["_id"]
    await svc.confirm(job_id=job["_id"])
    await _wait_for(job_repo, job["_id"],
                    terminal_states={"done", "error", "cancelled"})
