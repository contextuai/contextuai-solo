"""
Tests for the coder workflow router (POST /run and POST /run/preview).

Uses FastAPI TestClient (httpx-based) and asserts SSE response shape.
No real model calls — CoderWorkflowService is mocked.
"""

from __future__ import annotations

import json
import sys
import os
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse_events(text: str) -> list[dict]:
    """Parse SSE response text into event dicts."""
    events = []
    for line in text.splitlines():
        if line.strip() == "data: [DONE]":
            events.append({"type": "_DONE_"})
        elif line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workflow_client(db_proxy):
    """TestClient with db override and a seeded project."""
    from fastapi.testclient import TestClient
    import database
    from app import app
    from database import get_db, get_database
    from services.auth_service import get_current_user, get_current_user_optional

    _USER = {
        "user_id": "test-user",
        "email": "test@test.local",
        "role": "admin",
        "organization": "solo",
        "department": None,
        "auth_type": "desktop",
        "scopes": ["*"],
    }

    async def _get_db():
        return db_proxy

    async def _get_user():
        return _USER

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_database] = _get_db
    app.dependency_overrides[get_current_user] = _get_user
    app.dependency_overrides[get_current_user_optional] = _get_user

    client = TestClient(app)

    async def _get_database():
        return db_proxy

    database.get_database = _get_database
    database.get_db = _get_database
    database._async_db = db_proxy
    app.state.db = db_proxy

    yield client

    database._async_db = None
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_project_id(db_proxy):
    """Create a project with a Coder role synchronously via asyncio."""
    import asyncio
    from repositories.coder_project_repository import CoderProjectRepository
    from repositories.coder_agent_role_repository import CoderAgentRoleRepository

    loop = asyncio.get_event_loop()

    async def _seed():
        proj_repo = CoderProjectRepository(db_proxy)
        role_repo = CoderAgentRoleRepository(db_proxy)
        project = await proj_repo.create(
            name="Router Test",
            folder_path="/tmp/router-test",
            runtime="python",
        )
        await proj_repo.update(project["project_id"], {"workflow_mode": "solo"})
        project = await proj_repo.get_by_id(project["project_id"])
        pid = project["project_id"]
        await role_repo.create({
            "project_id": pid,
            "role_kind": "coder",
            "display_name": "Coder",
            "system_prompt": "You code.",
            "model_id": "qwen2.5-coder-7b",
            "temperature": 0.3,
            "max_tokens": 512,
            "enabled": True,
            "order": 0,
        })
        return pid

    return loop.run_until_complete(_seed())


# ---------------------------------------------------------------------------
# POST /run — SSE shape
# ---------------------------------------------------------------------------

def test_run_returns_sse_stream(workflow_client, seeded_project_id):
    """POST /run returns text/event-stream with correct event shape."""
    async def _mock_run(project_id, user_message, chat_history=None):
        import json
        yield f"data: {json.dumps({'type': 'workflow_start', 'workflow_mode': 'solo', 'roles': []})}\n\n"
        yield f"data: {json.dumps({'type': 'role_start', 'role_id': 'r1', 'role_kind': 'coder', 'display_name': 'Coder', 'model_id': 'q'})}\n\n"
        yield f"data: {json.dumps({'type': 'role_token', 'role_id': 'r1', 'content': 'hello'})}\n\n"
        yield f"data: {json.dumps({'type': 'role_done', 'role_id': 'r1', 'output': 'hello', 'usage': {}})}\n\n"
        yield f"data: {json.dumps({'type': 'workflow_done', 'total_usage': {}})}\n\n"
        yield "data: [DONE]\n\n"

    with patch("routers.coder_workflow.CoderWorkflowService") as MockSvc:
        instance = MockSvc.return_value
        instance.run = _mock_run

        resp = workflow_client.post(
            f"/api/v1/coder/projects/{seeded_project_id}/run",
            json={"message": "Print hello"},
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    events = _sse_events(resp.text)
    types = [e["type"] for e in events]

    assert "workflow_start" in types
    assert "role_start" in types
    assert "role_token" in types
    assert "role_done" in types
    assert "workflow_done" in types
    assert "_DONE_" in types


def test_run_accepts_history(workflow_client, seeded_project_id):
    """POST /run accepts optional history field without error."""
    async def _mock_run(project_id, user_message, chat_history=None):
        import json
        yield f"data: {json.dumps({'type': 'workflow_done', 'total_usage': {}})}\n\n"
        yield "data: [DONE]\n\n"

    with patch("routers.coder_workflow.CoderWorkflowService") as MockSvc:
        instance = MockSvc.return_value
        instance.run = _mock_run

        resp = workflow_client.post(
            f"/api/v1/coder/projects/{seeded_project_id}/run",
            json={
                "message": "Continue",
                "history": [
                    {"role": "user", "content": "Previous question"},
                    {"role": "assistant", "content": "Previous answer"},
                ],
            },
        )

    assert resp.status_code == 200


def test_run_ends_with_done(workflow_client, seeded_project_id):
    """SSE stream always ends with data: [DONE]."""
    async def _mock_run(project_id, user_message, chat_history=None):
        import json
        yield f"data: {json.dumps({'type': 'workflow_done', 'total_usage': {}})}\n\n"
        yield "data: [DONE]\n\n"

    with patch("routers.coder_workflow.CoderWorkflowService") as MockSvc:
        instance = MockSvc.return_value
        instance.run = _mock_run

        resp = workflow_client.post(
            f"/api/v1/coder/projects/{seeded_project_id}/run",
            json={"message": "Test"},
        )

    assert "data: [DONE]" in resp.text


# ---------------------------------------------------------------------------
# POST /run/preview — JSON plan, no model calls
# ---------------------------------------------------------------------------

def test_preview_returns_json_plan(workflow_client, seeded_project_id):
    """POST /run/preview returns a JSON plan without making model calls."""
    fake_plan = {
        "project_id": seeded_project_id,
        "workflow_mode": "solo",
        "roles": [{"role_id": "r1", "role_kind": "coder", "display_name": "Coder", "model_id": "qwen2.5-coder-7b"}],
        "role_count": 1,
    }

    with patch("routers.coder_workflow.CoderWorkflowService") as MockSvc:
        instance = MockSvc.return_value
        instance.preview = AsyncMock(return_value=fake_plan)

        resp = workflow_client.post(
            f"/api/v1/coder/projects/{seeded_project_id}/run/preview",
            json={"message": "Describe the plan"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow_mode"] == "solo"
    assert body["role_count"] == 1
    assert body["roles"][0]["role_kind"] == "coder"


def test_preview_no_model_calls(workflow_client, seeded_project_id):
    """stream_chat dispatcher must NOT be called during preview."""
    fake_plan = {
        "project_id": seeded_project_id,
        "workflow_mode": "solo",
        "roles": [],
        "role_count": 0,
    }

    with patch("routers.coder_workflow.CoderWorkflowService") as MockSvc, \
         patch("services.model_dispatcher.stream_chat") as mock_dispatcher:
        instance = MockSvc.return_value
        instance.preview = AsyncMock(return_value=fake_plan)

        workflow_client.post(
            f"/api/v1/coder/projects/{seeded_project_id}/run/preview",
            json={"message": "Preview only"},
        )

        mock_dispatcher.assert_not_called()


def test_preview_404_for_unknown_project(workflow_client):
    """POST /run/preview returns 404 when the project doesn't exist."""
    fake_plan = {"error": "Project not found: nonexistent"}

    with patch("routers.coder_workflow.CoderWorkflowService") as MockSvc:
        instance = MockSvc.return_value
        instance.preview = AsyncMock(return_value=fake_plan)

        resp = workflow_client.post(
            "/api/v1/coder/projects/nonexistent/run/preview",
            json={"message": "Test"},
        )

    assert resp.status_code == 404
