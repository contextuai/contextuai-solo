"""Tests for Phase 4 PR 7 — Cross-mode handoffs.

Three handoffs covered:
1. ``run_coder_project`` automation output handler (failure cases — the
   happy path actually spawns a subprocess so we exercise the error
   surface only).
2. ``POST /api/v1/coder/projects/{project_id}/index-as-kb`` 404 cases.
3. Index-as-KB happy path: project + KB exist, folder source row is
   created, an index job is kicked.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(db_proxy, name: str = "Test", trusted: bool = False) -> dict:
    """Insert a stub Coder project row directly via the repo. Returns the
    project dict (with project_id + folder_path)."""
    from repositories.coder_project_repository import CoderProjectRepository

    async def _do():
        tmp = tempfile.mkdtemp(prefix="coder-proj-")
        repo = CoderProjectRepository(db_proxy)
        row = await repo.create(
            name=name,
            folder_path=tmp,
            template_id=None,
            runtime="auto",
        )
        if trusted:
            await repo.set_trusted(row["project_id"], True)
            row = await repo.get_by_id(row["project_id"])
        return row

    return asyncio.get_event_loop().run_until_complete(_do())


def _make_kb(db_proxy, name: str = "K") -> str:
    """Insert a KB row and return its id."""
    import uuid
    from datetime import datetime

    from repositories.knowledge_base_repository import KnowledgeBaseRepository

    async def _do():
        repo = KnowledgeBaseRepository(db_proxy)
        kb_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        await repo.create(
            {
                "_id": kb_id,
                "name": name,
                "description": "",
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_dim": 384,
                "doc_count": 0,
                "chunk_count": 0,
                "created_at": now,
                "updated_at": now,
            }
        )
        return kb_id

    return asyncio.get_event_loop().run_until_complete(_do())


# ---------------------------------------------------------------------------
# 1. Automation output type: run_coder_project
# ---------------------------------------------------------------------------

def test_run_coder_project_unknown_id_returns_failed(db_proxy):
    """If the project_id doesn't exist, the handler returns status=failed."""
    from models.automation_models import AutomationExecutionResponse, ExecutionStatus
    from services.automation_output_service import automation_output_service

    execution = AutomationExecutionResponse(
        execution_id="e1",
        automation_id="a1",
        status=ExecutionStatus.SUCCESS,
        started_at="2024-01-01T00:00:00",
    )

    async def _do():
        return await automation_output_service._run_coder_project(
            execution,
            {"project_id": "does-not-exist"},
            db_proxy,
        )

    result = asyncio.get_event_loop().run_until_complete(_do())
    assert result["status"] == "failed"
    assert result["type"] == "run_coder_project"
    assert "not found" in result["error"].lower()


def test_run_coder_project_untrusted_returns_failed(db_proxy):
    """Existing-but-untrusted project must NOT spawn a subprocess."""
    from models.automation_models import AutomationExecutionResponse, ExecutionStatus
    from services.automation_output_service import automation_output_service

    project = _make_project(db_proxy, name="Untrusted", trusted=False)

    execution = AutomationExecutionResponse(
        execution_id="e1",
        automation_id="a1",
        status=ExecutionStatus.SUCCESS,
        started_at="2024-01-01T00:00:00",
    )

    async def _do():
        return await automation_output_service._run_coder_project(
            execution,
            {"project_id": project["project_id"]},
            db_proxy,
        )

    result = asyncio.get_event_loop().run_until_complete(_do())
    assert result["status"] == "failed"
    assert result["project_id"] == project["project_id"]
    assert "trusted" in result["error"].lower()


def test_run_coder_project_missing_project_id_returns_failed(db_proxy):
    """Empty config → fail fast with a clear error, no DB hit needed."""
    from models.automation_models import AutomationExecutionResponse, ExecutionStatus
    from services.automation_output_service import automation_output_service

    execution = AutomationExecutionResponse(
        execution_id="e1",
        automation_id="a1",
        status=ExecutionStatus.SUCCESS,
        started_at="2024-01-01T00:00:00",
    )

    async def _do():
        return await automation_output_service._run_coder_project(
            execution, {}, db_proxy,
        )

    result = asyncio.get_event_loop().run_until_complete(_do())
    assert result["status"] == "failed"
    assert "project_id" in result["error"]


# ---------------------------------------------------------------------------
# 2. Index-as-KB endpoint — failure modes
# ---------------------------------------------------------------------------

def test_index_as_kb_404_when_project_missing(test_app):
    resp = test_app.post(
        "/api/v1/coder/projects/does-not-exist/index-as-kb",
        json={"kb_id": "anything"},
    )
    assert resp.status_code == 404


def test_index_as_kb_404_when_kb_missing(test_app, db_proxy):
    """Project exists but kb_id is bogus."""
    project = _make_project(db_proxy, name="HasFolder", trusted=False)
    resp = test_app.post(
        f"/api/v1/coder/projects/{project['project_id']}/index-as-kb",
        json={"kb_id": "no-such-kb"},
    )
    assert resp.status_code == 404
    assert "knowledge base" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 3. Index-as-KB endpoint — happy path
# ---------------------------------------------------------------------------

def test_index_as_kb_creates_folder_source_and_kicks_job(test_app, db_proxy):
    """Happy path: creates a kb_folder_sources row + an index job."""
    with tempfile.TemporaryDirectory() as tmp:
        # Drop a tiny text file so the walker has something to do.
        with open(os.path.join(tmp, "readme.txt"), "w", encoding="utf-8") as f:
            f.write("hello world")

        # Stub project pointing at the temp dir.
        from repositories.coder_project_repository import CoderProjectRepository

        async def _seed_project():
            repo = CoderProjectRepository(db_proxy)
            return await repo.create(
                name="MyApp",
                folder_path=tmp,
                template_id=None,
                runtime="auto",
            )

        project = asyncio.get_event_loop().run_until_complete(_seed_project())

        # KB.
        kb_id = _make_kb(db_proxy, name="Coder KB")

        resp = test_app.post(
            f"/api/v1/coder/projects/{project['project_id']}/index-as-kb",
            json={"kb_id": kb_id, "schedule": "manual"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["kb_id"] == kb_id
        assert body["source_id"]
        assert body["job_id"]

        # Verify the folder source row landed with the right shape.
        from repositories.folder_source_repository import FolderSourceRepository

        async def _read():
            src_repo = FolderSourceRepository(db_proxy)
            return await src_repo.get_source(body["source_id"])

        source = asyncio.get_event_loop().run_until_complete(_read())
        assert source is not None
        assert source["kb_id"] == kb_id
        assert source["path"] == tmp
        assert "Coder project" in source["label"]
        assert source["schedule"] == "manual"


def test_index_as_kb_uses_explicit_label_when_supplied(test_app, db_proxy):
    """Explicit ``label`` overrides the default ``<name> (Coder project)``."""
    with tempfile.TemporaryDirectory() as tmp:
        from repositories.coder_project_repository import CoderProjectRepository

        async def _seed_project():
            repo = CoderProjectRepository(db_proxy)
            return await repo.create(
                name="LabeledApp",
                folder_path=tmp,
                template_id=None,
                runtime="auto",
            )

        project = asyncio.get_event_loop().run_until_complete(_seed_project())
        kb_id = _make_kb(db_proxy, name="Labeled KB")

        resp = test_app.post(
            f"/api/v1/coder/projects/{project['project_id']}/index-as-kb",
            json={"kb_id": kb_id, "label": "My Custom Label"},
        )
        assert resp.status_code == 200, resp.text

        from repositories.folder_source_repository import FolderSourceRepository

        async def _read():
            src_repo = FolderSourceRepository(db_proxy)
            return await src_repo.get_source(resp.json()["source_id"])

        source = asyncio.get_event_loop().run_until_complete(_read())
        assert source["label"] == "My Custom Label"
