"""
Tests for POST /run/preview endpoint — plan as JSON, no model calls.

Verifies:
- Returns project_id, workflow_mode, roles, role_count.
- Roles include role_id, role_kind, display_name, model_id.
- __DEFAULT__ model_id is resolved (or reported as unresolved).
- The model dispatcher is NOT invoked.
"""

from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def project_with_roles(db_proxy):
    """Seed a project with 2 roles: Coder (order=0) and Reviewer (order=1)."""
    from repositories.coder_project_repository import CoderProjectRepository
    from repositories.coder_agent_role_repository import CoderAgentRoleRepository

    proj_repo = CoderProjectRepository(db_proxy)
    role_repo = CoderAgentRoleRepository(db_proxy)

    project = await proj_repo.create(
        name="Preview Test",
        folder_path="/tmp/preview-test",
        runtime="python",
    )
    await proj_repo.update(project["project_id"], {"workflow_mode": "sequential"})
    project = await proj_repo.get_by_id(project["project_id"])
    pid = project["project_id"]

    await role_repo.create({
        "project_id": pid, "role_kind": "coder",
        "display_name": "Coder", "system_prompt": "Code.",
        "model_id": "qwen2.5-coder-7b",
        "temperature": 0.3, "max_tokens": 512,
        "enabled": True, "order": 0,
    })
    await role_repo.create({
        "project_id": pid, "role_kind": "reviewer",
        "display_name": "Reviewer", "system_prompt": "Review.",
        "model_id": "deepseek-coder-6.7b",
        "temperature": 0.3, "max_tokens": 256,
        "enabled": True, "order": 1,
    })
    return project


@pytest_asyncio.fixture
async def project_with_default_model(db_proxy):
    """Seed a project with a role using __DEFAULT__ model sentinel."""
    from repositories.coder_project_repository import CoderProjectRepository
    from repositories.coder_agent_role_repository import CoderAgentRoleRepository

    proj_repo = CoderProjectRepository(db_proxy)
    role_repo = CoderAgentRoleRepository(db_proxy)

    project = await proj_repo.create(
        name="Default Model Preview",
        folder_path="/tmp/dm-preview",
        runtime="python",
    )
    await proj_repo.update(project["project_id"], {"workflow_mode": "custom"})
    project = await proj_repo.get_by_id(project["project_id"])
    pid = project["project_id"]

    await role_repo.create({
        "project_id": pid, "role_kind": "coder",
        "display_name": "Coder", "system_prompt": "Code.",
        "model_id": "__DEFAULT__",
        "temperature": 0.3, "max_tokens": 512,
        "enabled": True, "order": 0,
    })
    return project


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preview_returns_plan_schema(db_proxy, project_with_roles):
    """preview() returns dict with project_id, workflow_mode, roles, role_count."""
    from services.coder_workflow_service import CoderWorkflowService

    svc = CoderWorkflowService(db_proxy)
    plan = await svc.preview(project_with_roles["project_id"])

    assert plan["project_id"] == project_with_roles["project_id"]
    assert plan["workflow_mode"] == "sequential"
    assert plan["role_count"] == 2
    assert len(plan["roles"]) == 2


@pytest.mark.asyncio
async def test_preview_roles_have_required_fields(db_proxy, project_with_roles):
    """Each role in the plan has role_id, role_kind, display_name, model_id."""
    from services.coder_workflow_service import CoderWorkflowService

    svc = CoderWorkflowService(db_proxy)
    plan = await svc.preview(project_with_roles["project_id"])

    for role in plan["roles"]:
        assert "role_id" in role
        assert "role_kind" in role
        assert "display_name" in role
        assert "model_id" in role


@pytest.mark.asyncio
async def test_preview_roles_sorted_by_order(db_proxy, project_with_roles):
    """Roles in the plan are sorted by their order field."""
    from services.coder_workflow_service import CoderWorkflowService

    svc = CoderWorkflowService(db_proxy)
    plan = await svc.preview(project_with_roles["project_id"])

    assert plan["roles"][0]["role_kind"] == "coder"
    assert plan["roles"][1]["role_kind"] == "reviewer"


@pytest.mark.asyncio
async def test_preview_no_dispatcher_called(db_proxy, project_with_roles):
    """The model dispatcher is never invoked during preview."""
    from services.coder_workflow_service import CoderWorkflowService

    with patch("services.coder_workflow_service.stream_chat") as mock_dispatch:
        svc = CoderWorkflowService(db_proxy)
        await svc.preview(project_with_roles["project_id"])

    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_preview_default_model_resolved_or_reported(db_proxy, project_with_default_model):
    """__DEFAULT__ model sentinel is resolved or reported as unresolved."""
    from services.coder_workflow_service import CoderWorkflowService

    fake_manager = MagicMock()
    fake_manager.list_installed.return_value = [{"id": "qwen2.5-coder-7b"}]

    with patch("services.model_dispatcher.model_manager", fake_manager, create=True):
        svc = CoderWorkflowService(db_proxy)
        plan = await svc.preview(project_with_default_model["project_id"])

    # The model_id in the plan should not be the raw __DEFAULT__ sentinel
    # (it should be resolved, or reported as "(unresolved)")
    role_model_id = plan["roles"][0]["model_id"]
    # Either resolved to a real model or has "(unresolved)" suffix
    assert "__DEFAULT__" not in role_model_id or "(unresolved)" in role_model_id


@pytest.mark.asyncio
async def test_preview_unknown_project_returns_error(db_proxy):
    """preview() for a non-existent project returns a dict with 'error'."""
    from services.coder_workflow_service import CoderWorkflowService

    svc = CoderWorkflowService(db_proxy)
    result = await svc.preview("does-not-exist-xyz")

    assert "error" in result


@pytest.mark.asyncio
async def test_preview_empty_roster(db_proxy):
    """preview() for a project with no roles returns role_count=0."""
    from repositories.coder_project_repository import CoderProjectRepository
    from services.coder_workflow_service import CoderWorkflowService

    proj_repo = CoderProjectRepository(db_proxy)
    project = await proj_repo.create(
        name="Empty Roster",
        folder_path="/tmp/empty",
        runtime="python",
    )

    svc = CoderWorkflowService(db_proxy)
    plan = await svc.preview(project["project_id"])

    # No error — just an empty plan
    assert "error" not in plan
    assert plan["role_count"] == 0
    assert plan["roles"] == []
