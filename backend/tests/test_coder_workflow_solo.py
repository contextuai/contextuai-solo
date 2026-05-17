"""
Tests for CoderWorkflowService — solo mode.

Verifies the event sequence:
  workflow_start -> role_start -> role_token* -> role_done -> workflow_done -> [DONE]
"""

from __future__ import annotations

import json
import sys
import os
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fake_stream(tokens: list[str]) -> AsyncIterator[dict]:
    for tok in tokens:
        yield {"type": "delta", "content": tok}
    yield {"type": "done", "finish_reason": "stop",
           "usage": {"prompt_tokens": 3, "completion_tokens": len(tokens), "total_tokens": 3 + len(tokens)}}


def _parse_events(chunks: list[str]) -> list[dict]:
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def solo_project(db_proxy):
    """Seed a project with a single Coder role."""
    from repositories.coder_project_repository import CoderProjectRepository
    from repositories.coder_agent_role_repository import CoderAgentRoleRepository

    proj_repo = CoderProjectRepository(db_proxy)
    role_repo = CoderAgentRoleRepository(db_proxy)

    project = await proj_repo.create(
        name="Solo Test",
        folder_path="/tmp/solo-test",
        runtime="python",
    )
    # Set workflow_mode = solo
    await proj_repo.update(project["project_id"], {"workflow_mode": "solo"})
    project = await proj_repo.get_by_id(project["project_id"])

    await role_repo.create({
        "project_id": project["project_id"],
        "role_kind": "coder",
        "display_name": "Solo Coder",
        "system_prompt": "You write code.",
        "model_id": "qwen2.5-coder-7b",
        "temperature": 0.3,
        "max_tokens": 512,
        "enabled": True,
        "order": 0,
    })

    return project


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_solo_event_sequence(db_proxy, solo_project):
    """workflow_start -> role_start -> role_token* -> role_done -> workflow_done -> [DONE]."""
    from services.coder_workflow_service import CoderWorkflowService

    fake = _fake_stream(["print", "(", "'hello'", ")"])

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", return_value=fake):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(
            solo_project["project_id"], "Print hello in Python"
        ):
            chunks.append(chunk)

    events = _parse_events(chunks)
    types = [e["type"] for e in events]

    assert types[0] == "workflow_start"
    assert types[1] == "role_start"
    # At least one token
    token_events = [e for e in events if e["type"] == "role_token"]
    assert len(token_events) >= 1
    # role_done follows tokens
    role_done_idx = types.index("role_done")
    assert role_done_idx > 1
    # workflow_done is second to last before [DONE]
    assert "workflow_done" in types
    assert types[-1] == "_DONE_"


@pytest.mark.asyncio
async def test_solo_workflow_start_contains_role_info(db_proxy, solo_project):
    """workflow_start event lists the role that will run."""
    from services.coder_workflow_service import CoderWorkflowService

    fake = _fake_stream(["code"])

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", return_value=fake):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(
            solo_project["project_id"], "Test"
        ):
            chunks.append(chunk)

    events = _parse_events(chunks)
    start_evt = events[0]
    assert start_evt["type"] == "workflow_start"
    assert start_evt["workflow_mode"] == "solo"
    assert len(start_evt["roles"]) == 1
    assert start_evt["roles"][0]["role_kind"] == "coder"
    assert start_evt["roles"][0]["display_name"] == "Solo Coder"


@pytest.mark.asyncio
async def test_solo_role_done_contains_full_output(db_proxy, solo_project):
    """role_done.output is the concatenation of all tokens."""
    from services.coder_workflow_service import CoderWorkflowService

    tokens = ["def", " hello", "():", "\n    pass"]
    fake = _fake_stream(tokens)

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", return_value=fake):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(
            solo_project["project_id"], "Write hello"
        ):
            chunks.append(chunk)

    events = _parse_events(chunks)
    role_done = next(e for e in events if e["type"] == "role_done")
    assert role_done["output"] == "".join(tokens)


@pytest.mark.asyncio
async def test_solo_workflow_done_contains_usage(db_proxy, solo_project):
    """workflow_done.total_usage aggregates the role's usage."""
    from services.coder_workflow_service import CoderWorkflowService

    fake = _fake_stream(["x"])

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", return_value=fake):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(
            solo_project["project_id"], "X"
        ):
            chunks.append(chunk)

    events = _parse_events(chunks)
    workflow_done = next(e for e in events if e["type"] == "workflow_done")
    assert "total_usage" in workflow_done
    # completion_tokens = 1 (one token in fake stream)
    assert workflow_done["total_usage"].get("completion_tokens", 0) >= 1
