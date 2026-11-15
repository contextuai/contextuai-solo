"""SPEC-33, SPEC-14 PR-B, SPEC-10, SPEC-11: Lite Edition, Memory Auto-Recall, Crew Dry-Run, and KB Staleness tests."""
import time
import pytest
from fastapi.testclient import TestClient

import app as app_module
import settings
from models.memory_models import MemoryFactCreate, MemorySettingsUpdate
from repositories.memory_repository import MemoryRepository
from repositories.memory_settings_repository import MemorySettingsRepository
from services.memory_service import MemoryService
from services.crew_orchestrator import CrewOrchestrator
from repositories.document_repository import DocumentRepository
from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from repositories.chunk_repository import ChunkRepository
from services.personal_docs_service import PersonalDocsService
from services.rag_service import RAGService


def test_lite_edition_endpoints_and_switch(monkeypatch):
    monkeypatch.delenv("CONTEXTUAI_SIDECAR_TOKEN", raising=False)
    settings.set_active_edition("lite")
    client = TestClient(app_module.app)

    r_get = client.get("/api/v1/desktop/edition")
    assert r_get.status_code == 200
    assert r_get.json()["edition"] == "lite"
    assert r_get.json()["brand_name"] == "Vesper"

    r_unlock = client.post("/api/v1/desktop/unlock-solo")
    assert r_unlock.status_code == 200
    assert r_unlock.json()["edition"] == "solo"
    assert r_unlock.json()["unlocked"] is True


@pytest.mark.asyncio
async def test_memory_auto_recall_for_prompt(db_proxy):
    mem_repo = MemoryRepository(db_proxy)
    settings_repo = MemorySettingsRepository(db_proxy)
    svc = MemoryService(mem_repo, settings_repo)

    await svc.add_fact(
        MemoryFactCreate(
            subject="SaaS pricing",
            predicate="is",
            value="$49/seat per month",
            scope="global",
        )
    )

    # Recall when enabled for chat surface
    block = await svc.recall_for_prompt(
        "What is our standard SaaS pricing?",
        surface="chat",
    )
    assert "## What I know" in block
    assert "$49/seat" in block

    # Disable chat surface -> returns empty string
    await svc.update_settings(MemorySettingsUpdate(chat_enabled=False))
    block_disabled = await svc.recall_for_prompt(
        "What is our standard SaaS pricing?",
        surface="chat",
    )
    assert block_disabled == ""


@pytest.mark.asyncio
async def test_crew_dry_run_captures_preview_without_external_publish():
    orch = CrewOrchestrator(crew_repo=None, run_repo=None, memory_repo=None, agent_repo=None)
    crew = {
        "crew_id": "crew-1",
        "name": "Growth Crew",
        "channel_bindings": [
            {"channel_type": "telegram", "enabled": True, "approval_required": False},
            {"channel_type": "linkedin", "enabled": True, "approval_required": True},
        ],
    }
    previews = await orch._publish_to_bound_channels(
        crew,
        "Launch post draft content",
        run_id="run-123",
        dry_run=True,
    )
    assert len(previews) == 2
    assert all(p["status"] == "dry_run_preview" and p["dry_run"] is True for p in previews)
    assert previews[0]["preview_content"] == "Launch post draft content"


@pytest.mark.asyncio
async def test_kb_folder_staleness_detection(db_proxy, tmp_path):
    folder = tmp_path / "docs_folder"
    folder.mkdir()
    doc_file = folder / "handbook.md"
    doc_file.write_text("# Handbook v1\nInitial content", encoding="utf-8")

    src_repo = FolderSourceRepository(db_proxy)
    job_repo = IndexJobRepository(db_proxy)
    doc_repo = DocumentRepository(db_proxy)
    kb_repo = KnowledgeBaseRepository(db_proxy)
    chunk_repo = ChunkRepository(db_proxy)
    rag = RAGService(kb_repo, doc_repo, chunk_repo)
    svc = PersonalDocsService(src_repo, job_repo, doc_repo, rag, friction_threshold=100)

    source = await src_repo.create_source(
        kb_id="kb-1",
        path=str(folder),
        label="Handbook",
        include_globs=[],
        exclude_globs=[],
        schedule="manual",
        max_file_bytes=1024 * 1024,
        max_files=100,
        max_depth=4,
    )

    # Before sync -> stale because 1 new file is unindexed
    st1 = await svc.check_folder_staleness(source["_id"])
    assert st1["is_stale"] is True
    assert st1["changed_files_count"] == 1

    # Simulate indexed document matching current size & mtime
    stat = doc_file.stat()
    await db_proxy["kb_documents"].insert_one({
        "_id": "doc-1",
        "kb_id": "kb-1",
        "source_id": source["_id"],
        "abs_path": str(doc_file),
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
    })
    st2 = await svc.check_folder_staleness(source["_id"])
    assert st2["is_stale"] is False
    assert st2["changed_files_count"] == 0

    # Modify file -> becomes stale
    time.sleep(0.02)
    doc_file.write_text("# Handbook v2\nUpdated content with more details", encoding="utf-8")
    st3 = await svc.check_folder_staleness(source["_id"])
    assert st3["is_stale"] is True
    assert st3["changed_files_count"] == 1
    assert st3["updated_files"] == 1
