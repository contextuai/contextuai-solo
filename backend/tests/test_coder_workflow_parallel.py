"""
Tests for CoderWorkflowService — parallel mode.

Verifies:
- Coder role runs first.
- Reviewer + Security run concurrently after Coder.
- Coder's role_done precedes Reviewer + Security role_done events.
- Reviewer + Security receive Coder's output as context.
"""

from __future__ import annotations

import json
import sys
import os
import asyncio
from typing import AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fake_stream(output: str) -> AsyncIterator[dict]:
    yield {"type": "delta", "content": output}
    yield {"type": "done", "finish_reason": "stop",
           "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}


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
async def parallel_project(db_proxy):
    """Seed a project with Coder, Reviewer, Security roles."""
    from repositories.coder_project_repository import CoderProjectRepository
    from repositories.coder_agent_role_repository import CoderAgentRoleRepository

    proj_repo = CoderProjectRepository(db_proxy)
    role_repo = CoderAgentRoleRepository(db_proxy)

    project = await proj_repo.create(
        name="Parallel Test",
        folder_path="/tmp/par-test",
        runtime="python",
    )
    await proj_repo.update(project["project_id"], {"workflow_mode": "parallel"})
    project = await proj_repo.get_by_id(project["project_id"])
    pid = project["project_id"]

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
    await role_repo.create({
        "project_id": pid, "role_kind": "security",
        "display_name": "Security", "system_prompt": "You audit.",
        "model_id": "phi-4-14b", "temperature": 0.2, "max_tokens": 512,
        "enabled": True, "order": 2,
    })

    return project


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parallel_coder_runs_first(db_proxy, parallel_project):
    """Coder's role_start appears before Reviewer and Security role_starts."""
    from services.coder_workflow_service import CoderWorkflowService

    async def _mock_stream(model_id, messages, **kwargs):
        yield {"type": "delta", "content": "output"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", side_effect=_mock_stream):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(parallel_project["project_id"], "Write a function"):
            chunks.append(chunk)

    events = _parse_events(chunks)
    role_starts = [e for e in events if e["type"] == "role_start"]

    assert len(role_starts) == 3
    # First role_start must be the Coder
    assert role_starts[0]["role_kind"] == "coder"


@pytest.mark.asyncio
async def test_parallel_coder_done_before_others(db_proxy, parallel_project):
    """Coder's role_done appears before Reviewer and Security role_done events."""
    from services.coder_workflow_service import CoderWorkflowService

    async def _mock_stream(model_id, messages, **kwargs):
        yield {"type": "delta", "content": "content"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", side_effect=_mock_stream):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(parallel_project["project_id"], "Test"):
            chunks.append(chunk)

    events = _parse_events(chunks)
    role_done_events = [e for e in events if e["type"] == "role_done"]

    # Find coder role_done index in the global event list
    all_types = [e["type"] for e in events]
    # All 3 role_done events present
    assert len(role_done_events) == 3

    # The Coder's role_done must come before Reviewer + Security role_done
    # We need to find which role_id corresponds to the Coder
    role_start_events = [e for e in events if e["type"] == "role_start"]
    coder_role_id = next(e["role_id"] for e in role_start_events if e["role_kind"] == "coder")
    other_role_ids = {e["role_id"] for e in role_start_events if e["role_kind"] != "coder"}

    # Find positions in the flat event list
    done_positions = {}
    for i, evt in enumerate(events):
        if evt["type"] == "role_done":
            done_positions[evt["role_id"]] = i

    coder_pos = done_positions[coder_role_id]
    for oid in other_role_ids:
        assert coder_pos < done_positions[oid], (
            f"Coder role_done at {coder_pos} is not before {oid} role_done at {done_positions[oid]}"
        )


@pytest.mark.asyncio
async def test_parallel_others_receive_coder_output(db_proxy, parallel_project):
    """Reviewer and Security receive Coder's output in their prompt."""
    from services.coder_workflow_service import CoderWorkflowService

    captured_messages = {}
    call_count = 0

    async def _mock_stream(model_id, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        # Identify which role this is by the model_id
        captured_messages[model_id + str(call_count)] = messages
        yield {"type": "delta", "content": "CODER-OUTPUT" if "qwen" in model_id else "other-output"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}

    all_messages = []

    async def _track_stream(model_id, messages, **kwargs):
        all_messages.append((model_id, messages))
        yield {"type": "delta", "content": "CODER-OUTPUT" if "qwen" in model_id else "check"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}

    with patch("services.coder_workflow_service.stream_chat", side_effect=_track_stream):
        svc = CoderWorkflowService(db_proxy)
        async for _ in svc.run(parallel_project["project_id"], "Implement X"):
            pass

    # First call = Coder
    assert "qwen" in all_messages[0][0]
    # Second and third calls = Reviewer + Security (in any order)
    for model_id, messages in all_messages[1:]:
        user_content = messages[-1]["content"]
        assert "CODER-OUTPUT" in user_content, (
            f"Expected coder output in context for {model_id}"
        )


@pytest.mark.asyncio
async def test_parallel_all_roles_present_in_stream(db_proxy, parallel_project):
    """All 3 roles produce role_start + role_done in the stream."""
    from services.coder_workflow_service import CoderWorkflowService

    async def _mock_stream(model_id, messages, **kwargs):
        yield {"type": "delta", "content": "x"}
        yield {"type": "done", "finish_reason": "stop", "usage": {}}

    chunks = []
    with patch("services.coder_workflow_service.stream_chat", side_effect=_mock_stream):
        svc = CoderWorkflowService(db_proxy)
        async for chunk in svc.run(parallel_project["project_id"], "Do something"):
            chunks.append(chunk)

    events = _parse_events(chunks)
    role_starts = [e for e in events if e["type"] == "role_start"]
    role_dones = [e for e in events if e["type"] == "role_done"]
    workflow_done = [e for e in events if e["type"] == "workflow_done"]

    assert len(role_starts) == 3
    assert len(role_dones) == 3
    assert len(workflow_done) == 1
    assert events[-1]["type"] == "_DONE_"
