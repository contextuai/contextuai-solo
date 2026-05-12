"""CRUD smoke tests for CoderAgentRoleRepository (PR 14)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from repositories.coder_agent_role_repository import CoderAgentRoleRepository


def _role(project_id: str, order: int = 0, kind: str = "coder") -> dict:
    return {
        "role_id": str(uuid.uuid4()),
        "project_id": project_id,
        "role_kind": kind,
        "display_name": f"Role {order}",
        "system_prompt": f"You are specialist number {order}.",
        "model_id": "qwen2.5-coder-7b",
        "temperature": 0.3,
        "max_tokens": 2048,
        "enabled": True,
        "order": order,
    }


@pytest_asyncio.fixture
async def role_repo(db_proxy):
    return CoderAgentRoleRepository(db_proxy)


@pytest.mark.asyncio
async def test_create_and_get(role_repo):
    pid = str(uuid.uuid4())
    row = await role_repo.create(_role(pid, order=0))
    assert row["role_id"]
    assert row["project_id"] == pid
    assert row["role_kind"] == "coder"
    assert row["order"] == 0


@pytest.mark.asyncio
async def test_list_for_project_sorted_by_order(role_repo):
    pid = str(uuid.uuid4())
    # Insert out of order intentionally.
    await role_repo.create(_role(pid, order=2, kind="reviewer"))
    await role_repo.create(_role(pid, order=0, kind="coder"))
    await role_repo.create(_role(pid, order=1, kind="planner"))

    rows = await role_repo.list_for_project(pid)
    assert len(rows) == 3
    orders = [r["order"] for r in rows]
    assert orders == sorted(orders)


@pytest.mark.asyncio
async def test_update(role_repo):
    pid = str(uuid.uuid4())
    created = await role_repo.create(_role(pid, order=0))
    role_id = created["role_id"]

    updated = await role_repo.update(role_id, {"display_name": "Updated Name", "enabled": False})
    assert updated is not None
    assert updated["display_name"] == "Updated Name"
    assert updated["enabled"] is False


@pytest.mark.asyncio
async def test_delete(role_repo):
    pid = str(uuid.uuid4())
    created = await role_repo.create(_role(pid, order=0))
    role_id = created["role_id"]

    deleted = await role_repo.delete(role_id)
    assert deleted is True

    # Second delete returns False.
    deleted_again = await role_repo.delete(role_id)
    assert deleted_again is False


@pytest.mark.asyncio
async def test_delete_for_project(role_repo):
    pid = str(uuid.uuid4())
    for i in range(3):
        await role_repo.create(_role(pid, order=i))

    count = await role_repo.delete_for_project(pid)
    assert count == 3

    remaining = await role_repo.list_for_project(pid)
    assert remaining == []


@pytest.mark.asyncio
async def test_max_order_for_project_empty(role_repo):
    pid = str(uuid.uuid4())
    assert await role_repo.max_order_for_project(pid) == -1


@pytest.mark.asyncio
async def test_max_order_for_project_with_rows(role_repo):
    pid = str(uuid.uuid4())
    await role_repo.create(_role(pid, order=0))
    await role_repo.create(_role(pid, order=5))
    await role_repo.create(_role(pid, order=2))
    assert await role_repo.max_order_for_project(pid) == 5


@pytest.mark.asyncio
async def test_update_nonexistent_returns_none(role_repo):
    result = await role_repo.update(str(uuid.uuid4()), {"display_name": "ghost"})
    assert result is None


@pytest.mark.asyncio
async def test_list_for_project_isolation(role_repo):
    """Roles from different projects don't leak."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    await role_repo.create(_role(pid_a, order=0))
    await role_repo.create(_role(pid_b, order=0))

    rows_a = await role_repo.list_for_project(pid_a)
    assert all(r["project_id"] == pid_a for r in rows_a)
    assert len(rows_a) == 1
