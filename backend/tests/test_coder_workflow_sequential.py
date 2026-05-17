"""
Tests for CoderWorkflowService — sequential mode.

Verifies:
- Roles fire in ``order`` field order.
- Each role's prompt includes previous roles' outputs prefixed with
  "## DisplayName\\n{output}\\n\\n".
- All roles' outputs appear in the final event stream.
"""

from __future__ import annotations

import json
import sys
import os
from typing import AsyncIterator
from unittest.mock import patch, AsyncMock

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fake_stream_for_role(output_text: str) -> AsyncIterator[dict]:
    """Yield output_text as a single token, then done."""
    yield {"type": "delta", "content": output_text}
    yield {"type": "done", "finish_reason": "stop",
           "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}}


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
async def sequential_project(db_proxy):
    """Seed a project with 3 roles in specific order."""
    from repositories.coder_project_repository import CoderProjectRepository
    from repositories.coder_agent_role_repository import CoderAgentRoleRepository

    proj_repo = CoderProjectRepository(db_proxy)
    role_repo = CoderAgentRoleRepository(db_proxy)

    project = await proj_repo.create(
        name="Sequential Test",
        folder_path="/tmp/seq-test",
        runtime="python",
    )
    await proj_repo.update(project["project_id"], {"workflow_mode": "sequential"})
    project = await proj_repo.get_by_id(project["project_id"])
    pid = project["project_id"]

    # Insert in reverse order to ensure the ``order`` field controls sequence.
    await role_repo.create({
        "project_id": pid, "role_kind": "docs",
        "display_name": "Tech Writer", "system_prompt": "You document.",
        "model_id": "gemma-3-12b", "temperature": 0.5, "max_tokens": 512,
        "enabled": True, "order": 2,
    })
    await role_repo.create({
        "project_id": pid, "role_kind": "coder",
        "display_name": "Coder", "system_prompt": "You code.",
        "model_id": "qwen2.5-coder-7b", "temperature": 0.3, "max_tokens": 1024,
        "enabled": True, "order": 0,
    })
    await role_repo.create({
        "project_id": pid, "role_kind": "reviewer",
        "display_name": "Reviewer", "system_prompt": "You review.",
        "model_id": "deepseek-coder-6.7b", "temperature": 0.3, "max_tokens": 512,
        "enabled": True, "order": 1,
    })

    return project


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sequential_three_roles_fire(db_proxy, sequential_project):
    """All 3 roles produce role_start + role_done events."""
    from services.coder_workflow_service import CoderWorkflowService

    call_count = 0

    async def _mock_stream(model_id, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        yield {"type": "delta", "content": f"output-{call_count}"}
        yield {"type": "done", "finish_reason": "stop", "usage": {"completion_tokens": 1}}

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", side_effect=_mock_stream):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(sequential_project["project_id"], "Build a feature"):
            chunks.append(chunk)

    events = _parse_events(chunks)
    role_starts = [e for e in events if e["type"] == "role_start"]
    role_dones = [e for e in events if e["type"] == "role_done"]

    assert len(role_starts) == 3
    assert len(role_dones) == 3


@pytest.mark.asyncio
async def test_sequential_order_respected(db_proxy, sequential_project):
    """Roles fire in order=0, 1, 2 regardless of insertion order."""
    from services.coder_workflow_service import CoderWorkflowService

    fired_names = []

    async def _mock_stream(model_id, messages, **kwargs):
        yield {"type": "delta", "content": "ok"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", side_effect=_mock_stream):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(sequential_project["project_id"], "Test"):
            chunks.append(chunk)

    events = _parse_events(chunks)
    role_starts = [e for e in events if e["type"] == "role_start"]
    # order=0 -> Coder, order=1 -> Reviewer, order=2 -> Tech Writer
    assert role_starts[0]["display_name"] == "Coder"
    assert role_starts[1]["display_name"] == "Reviewer"
    assert role_starts[2]["display_name"] == "Tech Writer"


@pytest.mark.asyncio
async def test_sequential_prior_context_injected(db_proxy, sequential_project):
    """Each role's prompt includes prior roles' outputs prefixed with ## DisplayName."""
    from services.coder_workflow_service import CoderWorkflowService

    captured_messages = []

    async def _mock_stream(model_id, messages, **kwargs):
        captured_messages.append(messages)
        call_idx = len(captured_messages)
        yield {"type": "delta", "content": f"ROLE-{call_idx}-OUTPUT"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}

    with patch("services.coder_workflow_service.stream_chat", side_effect=_mock_stream):
        svc = CoderWorkflowService(db_proxy)
        async for _ in svc.run(sequential_project["project_id"], "Write code"):
            pass

    # Role 0 (Coder): no prior context
    coder_user_msg = captured_messages[0][-1]["content"]
    assert "## " not in coder_user_msg or coder_user_msg.strip().startswith("Write code")

    # Role 1 (Reviewer): should see Coder's output prefixed with "## Coder"
    reviewer_user_msg = captured_messages[1][-1]["content"]
    assert "## Coder" in reviewer_user_msg
    assert "ROLE-1-OUTPUT" in reviewer_user_msg

    # Role 2 (Tech Writer): should see Coder + Reviewer outputs
    writer_user_msg = captured_messages[2][-1]["content"]
    assert "## Coder" in writer_user_msg
    assert "## Reviewer" in writer_user_msg
    assert "ROLE-1-OUTPUT" in writer_user_msg
    assert "ROLE-2-OUTPUT" in writer_user_msg


@pytest.mark.asyncio
async def test_sequential_all_role_dones_present(db_proxy, sequential_project):
    """All 3 role_done events appear in the stream."""
    from services.coder_workflow_service import CoderWorkflowService

    async def _mock_stream(model_id, messages, **kwargs):
        yield {"type": "delta", "content": "done-content"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", side_effect=_mock_stream):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(sequential_project["project_id"], "Work"):
            chunks.append(chunk)

    events = _parse_events(chunks)
    role_dones = [e for e in events if e["type"] == "role_done"]
    assert len(role_dones) == 3
    # Each role_done has a non-empty output
    for rd in role_dones:
        assert rd["output"]
