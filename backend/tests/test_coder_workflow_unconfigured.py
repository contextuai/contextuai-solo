"""
Tests for CoderWorkflowService fail-fast behaviour when a role has no model.

After PR 17, any enabled role with model_id == "" causes the workflow to
emit a single SSE error event and terminate — no model dispatcher call.

Covered scenarios:
- Single role with empty model_id: error event contains the role's display_name.
- Multiple roles, first has empty model_id: fails on the first unconfigured role.
- Zero roles with no project model_id (fallback synthesised, also unconfigured).
- Model dispatcher is never called in any of the above paths.
"""

from __future__ import annotations

import json
import sys
import os
from typing import List
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_events(chunks: List[str]) -> List[dict]:
    events = []
    for chunk in chunks:
        if chunk.strip() == "data: [DONE]":
            events.append({"type": "_DONE_"})
            continue
        if chunk.startswith("data: "):
            try:
                events.append(json.loads(chunk[6:]))
            except json.JSONDecodeError:
                pass
    return events


async def _collect(gen) -> List[str]:
    return [chunk async for chunk in gen]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def wf_service(db_proxy):
    """Return a CoderWorkflowService backed by the in-memory db_proxy."""
    from services.coder_workflow_service import CoderWorkflowService
    return CoderWorkflowService(db_proxy)


@pytest_asyncio.fixture
async def project_with_empty_role(db_proxy):
    """Seed a project whose single Coder role has model_id == ''."""
    from repositories.coder_project_repository import CoderProjectRepository
    from repositories.coder_agent_role_repository import CoderAgentRoleRepository

    proj_repo = CoderProjectRepository(db_proxy)
    role_repo = CoderAgentRoleRepository(db_proxy)

    project = await proj_repo.create(
        name="Unconfigured",
        folder_path="/tmp/unconfigured",
        runtime="python",
    )
    pid = project["project_id"]
    await proj_repo.update(pid, {"workflow_mode": "solo"})

    await role_repo.create({
        "project_id": pid,
        "role_kind": "coder",
        "display_name": "Coder",
        "system_prompt": "You code.",
        "model_id": "",          # not yet configured
        "temperature": 0.3,
        "max_tokens": 512,
        "enabled": True,
        "order": 0,
    })

    return pid


@pytest_asyncio.fixture
async def project_with_mixed_roles(db_proxy):
    """Seed a sequential project; Planner has a model but Reviewer does not."""
    from repositories.coder_project_repository import CoderProjectRepository
    from repositories.coder_agent_role_repository import CoderAgentRoleRepository

    proj_repo = CoderProjectRepository(db_proxy)
    role_repo = CoderAgentRoleRepository(db_proxy)

    project = await proj_repo.create(
        name="Mixed",
        folder_path="/tmp/mixed",
        runtime="python",
    )
    pid = project["project_id"]
    await proj_repo.update(pid, {"workflow_mode": "sequential"})

    await role_repo.create({
        "project_id": pid,
        "role_kind": "planner",
        "display_name": "Planner",
        "system_prompt": "You plan.",
        "model_id": "",          # unconfigured — fail-fast should catch this first
        "temperature": 0.4,
        "max_tokens": 512,
        "enabled": True,
        "order": 0,
    })
    await role_repo.create({
        "project_id": pid,
        "role_kind": "reviewer",
        "display_name": "Code Reviewer",
        "system_prompt": "You review.",
        "model_id": "",          # also unconfigured
        "temperature": 0.3,
        "max_tokens": 512,
        "enabled": True,
        "order": 1,
    })

    return pid


@pytest_asyncio.fixture
async def project_no_roles(db_proxy):
    """Seed a project with zero roles and no model_id on the project doc."""
    from repositories.coder_project_repository import CoderProjectRepository

    proj_repo = CoderProjectRepository(db_proxy)
    project = await proj_repo.create(
        name="No roles",
        folder_path="/tmp/no-roles",
        runtime="python",
    )
    pid = project["project_id"]
    await proj_repo.update(pid, {"workflow_mode": "solo"})
    # Deliberately no model_id on the project doc.
    return pid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unconfigured_single_role_emits_error(wf_service, project_with_empty_role):
    """A single role with model_id='' triggers an error event, not a model call."""
    with patch("services.coder_workflow_service.stream_chat") as mock_dispatch:
        chunks = await _collect(
            wf_service.run(project_with_empty_role, "Write code", [])
        )

    events = _parse_events(chunks)
    error_events = [e for e in events if e.get("type") == "error"]

    assert error_events, "Expected at least one error event"
    assert "Coder" in error_events[0]["error"], (
        f"Error message should mention the role display_name; got: {error_events[0]['error']!r}"
    )
    assert "no model selected" in error_events[0]["error"].lower() or \
           "open the team panel" in error_events[0]["error"].lower(), (
        f"Error message should guide the user; got: {error_events[0]['error']!r}"
    )
    assert "_DONE_" in [e["type"] for e in events], "Stream must end with [DONE]"
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_unconfigured_role_no_workflow_start_before_error(wf_service, project_with_empty_role):
    """Fail-fast fires before workflow_start so the client sees the error first."""
    with patch("services.coder_workflow_service.stream_chat"):
        chunks = await _collect(
            wf_service.run(project_with_empty_role, "Write code", [])
        )

    events = _parse_events(chunks)
    types = [e["type"] for e in events]

    # The error must appear before workflow_start (or workflow_start must not appear).
    if "workflow_start" in types:
        error_idx = types.index("error")
        start_idx = types.index("workflow_start")
        assert error_idx < start_idx, (
            "error event should precede workflow_start"
        )


@pytest.mark.asyncio
async def test_unconfigured_mixed_roles_emits_error_for_first(wf_service, project_with_mixed_roles):
    """When multiple roles are unconfigured, the first one in order triggers the error."""
    with patch("services.coder_workflow_service.stream_chat") as mock_dispatch:
        chunks = await _collect(
            wf_service.run(project_with_mixed_roles, "Plan and review", [])
        )

    events = _parse_events(chunks)
    error_events = [e for e in events if e.get("type") == "error"]

    assert error_events, "Expected an error event"
    # First role by order is Planner.
    assert "Planner" in error_events[0]["error"], (
        f"Expected 'Planner' in error message; got: {error_events[0]['error']!r}"
    )
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_no_roles_with_no_project_model_emits_error(wf_service, project_no_roles):
    """Project with zero roles and no project model_id triggers the fail-fast error."""
    with patch("services.coder_workflow_service.stream_chat") as mock_dispatch:
        chunks = await _collect(
            wf_service.run(project_no_roles, "Write code", [])
        )

    events = _parse_events(chunks)
    error_events = [e for e in events if e.get("type") == "error"]

    assert error_events, "Expected an error event when no roles and no model"
    assert "_DONE_" in [e["type"] for e in events]
    mock_dispatch.assert_not_called()


def test_unconfigured_role_via_router(db_proxy):
    """POST /run with an unconfigured role returns SSE with an error event.

    Uses synchronous TestClient (which drives its own event loop internally),
    with stream_chat mocked so no actual model calls happen.

    Note: this must be a sync test — pytest-asyncio + TestClient cannot both
    run event loops simultaneously.
    """
    import asyncio
    from fastapi.testclient import TestClient
    import database
    from app import app
    from database import get_db, get_database
    from services.auth_service import get_current_user, get_current_user_optional
    from repositories.coder_project_repository import CoderProjectRepository
    from repositories.coder_agent_role_repository import CoderAgentRoleRepository

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

    database._async_db = db_proxy
    app.state.db = db_proxy

    # Seed the project synchronously using a fresh event loop.
    async def _seed():
        proj_repo = CoderProjectRepository(db_proxy)
        role_repo = CoderAgentRoleRepository(db_proxy)
        project = await proj_repo.create(
            name="Router Unconfigured",
            folder_path="/tmp/router-unconfigured",
            runtime="python",
        )
        pid = project["project_id"]
        await proj_repo.update(pid, {"workflow_mode": "solo"})
        await role_repo.create({
            "project_id": pid,
            "role_kind": "coder",
            "display_name": "Coder",
            "system_prompt": "You code.",
            "model_id": "",
            "temperature": 0.3,
            "max_tokens": 512,
            "enabled": True,
            "order": 0,
        })
        return pid

    # Use the conftest-provided event loop (already running for async fixtures),
    # but since this is a sync test we create our own loop for the seed.
    seed_loop = asyncio.new_event_loop()
    try:
        pid = seed_loop.run_until_complete(_seed())
    finally:
        seed_loop.close()

    client = TestClient(app)

    try:
        with patch("services.coder_workflow_service.stream_chat") as mock_dispatch:
            resp = client.post(
                f"/api/v1/coder/projects/{pid}/run",
                json={"message": "Write something"},
            )
    finally:
        app.dependency_overrides.clear()
        database._async_db = None

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")

    events = _parse_events(resp.text.splitlines())
    error_events = [e for e in events if e.get("type") == "error"]
    assert error_events, f"Expected error event in SSE; got events: {events}"
    assert "Coder" in error_events[0]["error"]
    mock_dispatch.assert_not_called()
