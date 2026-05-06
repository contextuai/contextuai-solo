"""Tests for Phase 4 PR 9 — crew step type "Run Coder project".

Covers:
1. Schema: ``CrewAgentConfig`` accepts a step with only ``coder_project_id``.
2. Schema: a step with neither ``instructions`` nor ``coder_project_id``
   raises ``ValidationError``.
3. Schema: ``CreateCrewRequest.validate_agents_for_mode`` counts Coder
   steps toward the "at least 1 step" minimum.
4. Orchestrator helper: untrusted project → step result is failed.
5. Orchestrator helper happy path: ``run_headless`` is mocked and the
   result is mapped onto the standard step shape.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(db_proxy, name: str = "Coder", trusted: bool = False) -> dict:
    """Insert a stub Coder project row directly via the repo."""
    from repositories.coder_project_repository import CoderProjectRepository

    async def _do():
        tmp = tempfile.mkdtemp(prefix="crew-coder-")
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


def _make_orchestrator():
    """Build a minimal CrewOrchestrator instance for helper-only tests."""
    from services.crew_orchestrator import CrewOrchestrator

    # The helper under test only touches the db / coder_run_service —
    # repos can be ``None`` because we never invoke run-state methods.
    return CrewOrchestrator(
        crew_repo=None,
        run_repo=None,
        memory_repo=None,
        agent_repo=None,
    )


# ---------------------------------------------------------------------------
# 1. Schema — Coder-only step is valid
# ---------------------------------------------------------------------------

def test_crew_with_coder_step_validates():
    """A CreateCrewRequest with one Coder-only step (no instructions) is valid."""
    from models.crew_models import CreateCrewRequest

    req = CreateCrewRequest(
        name="Coder Crew",
        agents=[
            {
                "name": "Lint Step",
                "coder_project_id": "proj-123",
                "coder_run_timeout_seconds": 30,
            }
        ],
    )
    assert len(req.agents) == 1
    step = req.agents[0]
    assert step.coder_project_id == "proj-123"
    assert step.coder_run_timeout_seconds == 30
    assert step.instructions == ""


# ---------------------------------------------------------------------------
# 2. Schema — neither instructions nor coder_project_id → error
# ---------------------------------------------------------------------------

def test_crew_step_without_instructions_or_coder_id_fails():
    """A step with no instructions and no coder_project_id must raise."""
    from models.crew_models import CrewAgentConfig

    with pytest.raises(ValidationError) as exc:
        CrewAgentConfig(name="Empty Step")

    msg = str(exc.value).lower()
    assert "instructions" in msg or "coder_project_id" in msg


# ---------------------------------------------------------------------------
# 3. Schema — counts Coder steps toward the "at least 1" rule
# ---------------------------------------------------------------------------

def test_validate_agents_for_mode_counts_coder_steps():
    """A crew composed entirely of Coder steps satisfies the min-step rule."""
    from models.crew_models import CreateCrewRequest, CrewExecutionConfig, ExecutionMode

    req = CreateCrewRequest(
        name="All-Coder Crew",
        agents=[
            {
                "name": "Build",
                "coder_project_id": "proj-1",
            }
        ],
        execution_config=CrewExecutionConfig(mode=ExecutionMode.SEQUENTIAL),
    )
    assert len(req.agents) == 1
    assert req.agents[0].coder_project_id == "proj-1"


def test_validate_agents_for_mode_rejects_empty_sequential():
    """Sanity: completely empty agents list is still rejected for sequential."""
    from models.crew_models import CreateCrewRequest, CrewExecutionConfig, ExecutionMode

    with pytest.raises(ValidationError):
        CreateCrewRequest(
            name="Empty Crew",
            agents=[],
            execution_config=CrewExecutionConfig(mode=ExecutionMode.SEQUENTIAL),
        )


# ---------------------------------------------------------------------------
# 4. Orchestrator helper — untrusted project returns failed
# ---------------------------------------------------------------------------

def test_run_headless_returns_failed_when_project_not_trusted(db_proxy):
    """An untrusted Coder project must NOT spawn a subprocess."""
    project = _make_project(db_proxy, name="Untrusted", trusted=False)

    orch = _make_orchestrator()

    step = {
        "name": "Run untrusted",
        "coder_project_id": project["project_id"],
        "coder_run_timeout_seconds": 30,
    }

    async def _do():
        return await orch._run_coder_step(step, db=db_proxy)

    result = asyncio.get_event_loop().run_until_complete(_do())
    assert result["status"] == "failed"
    assert result["project_id"] == project["project_id"]
    assert "trusted" in (result["error"] or "").lower()
    assert result["agent_name"].startswith("Coder: ")
    assert result["output"] == ""


def test_run_headless_returns_failed_when_project_missing(db_proxy):
    """Unknown project_id → status=failed, clear error, no DB exception."""
    orch = _make_orchestrator()

    step = {
        "name": "Run missing",
        "coder_project_id": "does-not-exist",
    }

    async def _do():
        return await orch._run_coder_step(step, db=db_proxy)

    result = asyncio.get_event_loop().run_until_complete(_do())
    assert result["status"] == "failed"
    assert "not found" in (result["error"] or "").lower()


def test_run_headless_returns_failed_when_project_id_empty(db_proxy):
    """Empty / missing coder_project_id → fail fast with clear error."""
    orch = _make_orchestrator()

    async def _do():
        return await orch._run_coder_step(
            {"name": "Bad", "coder_project_id": ""}, db=db_proxy
        )

    result = asyncio.get_event_loop().run_until_complete(_do())
    assert result["status"] == "failed"
    assert "coder_project_id" in (result["error"] or "")


# ---------------------------------------------------------------------------
# 5. Orchestrator helper happy path (mocked run_headless)
# ---------------------------------------------------------------------------

def test_run_headless_happy_path_mocked(db_proxy):
    """Mock ``run_headless`` and assert the result is mapped onto the
    standard step shape."""
    project = _make_project(db_proxy, name="Builder", trusted=True)

    orch = _make_orchestrator()

    fake_run_service = type("FakeRunSvc", (), {})()
    fake_run_service.run_headless = AsyncMock(
        return_value={
            "exit_code": 0,
            "output_lines": ["hello"],
            "duration_seconds": 0.1,
            "timed_out": False,
        }
    )

    step = {
        "name": "Builder Step",
        "coder_project_id": project["project_id"],
        "coder_run_timeout_seconds": 30,
    }

    with patch(
        "services.coder_run_service.get_run_service",
        return_value=fake_run_service,
    ):
        async def _do():
            return await orch._run_coder_step(step, db=db_proxy)

        result = asyncio.get_event_loop().run_until_complete(_do())

    assert result["status"] == "completed"
    assert result["error"] is None
    assert result["output"] == "hello"
    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    assert result["duration_ms"] == 100  # 0.1s → 100ms
    assert result["agent_name"] == "Coder: Builder"
    assert result["project_id"] == project["project_id"]

    fake_run_service.run_headless.assert_awaited_once()
    call_args = fake_run_service.run_headless.call_args
    # Positional: project; kwarg: timeout_seconds=30.
    assert call_args.kwargs.get("timeout_seconds") == 30


def test_run_headless_failure_maps_to_failed_status(db_proxy):
    """Non-zero exit_code → status=failed, error includes exit + timed_out."""
    project = _make_project(db_proxy, name="Crashy", trusted=True)
    orch = _make_orchestrator()

    fake_run_service = type("FakeRunSvc", (), {})()
    fake_run_service.run_headless = AsyncMock(
        return_value={
            "exit_code": 2,
            "output_lines": ["error: boom", "trace"],
            "duration_seconds": 0.05,
            "timed_out": False,
        }
    )

    step = {
        "name": "Crashy Step",
        "coder_project_id": project["project_id"],
    }

    with patch(
        "services.coder_run_service.get_run_service",
        return_value=fake_run_service,
    ):
        async def _do():
            return await orch._run_coder_step(step, db=db_proxy)

        result = asyncio.get_event_loop().run_until_complete(_do())

    assert result["status"] == "failed"
    assert "exit=2" in (result["error"] or "")
    assert "timed_out=False" in (result["error"] or "")
    assert result["output"] == "error: boom\ntrace"


def test_run_headless_caps_output_at_4000_chars(db_proxy):
    """Output above 4000 chars is trimmed to the trailing 4000 chars."""
    project = _make_project(db_proxy, name="Verbose", trusted=True)
    orch = _make_orchestrator()

    big_line = "x" * 5000
    fake_run_service = type("FakeRunSvc", (), {})()
    fake_run_service.run_headless = AsyncMock(
        return_value={
            "exit_code": 0,
            "output_lines": [big_line],
            "duration_seconds": 0.0,
            "timed_out": False,
        }
    )

    step = {
        "name": "Verbose Step",
        "coder_project_id": project["project_id"],
    }

    with patch(
        "services.coder_run_service.get_run_service",
        return_value=fake_run_service,
    ):
        async def _do():
            return await orch._run_coder_step(step, db=db_proxy)

        result = asyncio.get_event_loop().run_until_complete(_do())

    assert result["status"] == "completed"
    assert len(result["output"]) == 4000
