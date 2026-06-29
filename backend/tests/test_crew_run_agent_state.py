"""Regression tests for CrewRunRepository.update_agent_state.

The SQLite motor-compat layer does not support MongoDB's positional array
operator (``agents.$.field``) nor matching ``agents.agent_id`` against array
elements. The original positional implementation therefore silently no-opped
and every crew run kept its per-agent state stuck at "pending" with no output,
even after the run completed. These tests lock in the read-modify-write
implementation that actually persists per-agent state.
"""

import pytest

from repositories.crew_repository import CrewRunRepository


def _run_data(agent_ids):
    return {
        "input": "do the thing",
        "input_data": None,
        "agents": [
            {
                "agent_id": aid,
                "name": f"Agent {i}",
                "role": "custom",
                "status": "pending",
                "output": None,
                "tokens_used": 0,
                "cost_usd": 0.0,
            }
            for i, aid in enumerate(agent_ids)
        ],
        "trigger_type": "manual",
        "trigger_source": "manual",
    }


@pytest.mark.asyncio
async def test_update_agent_state_persists_status_and_output(db_proxy):
    repo = CrewRunRepository(db_proxy)
    run = await repo.create_run("crew-1", "desktop-user", _run_data(["a1", "a2"]))
    run_id = run["run_id"]

    updated = await repo.update_agent_state(
        run_id, "a2", {"status": "completed", "output": "hello world", "tokens_used": 42}
    )
    assert updated is not None

    fresh = await repo.get_by_run_id(run_id)
    by_id = {a["agent_id"]: a for a in fresh["agents"]}
    # The targeted agent is updated...
    assert by_id["a2"]["status"] == "completed"
    assert by_id["a2"]["output"] == "hello world"
    assert by_id["a2"]["tokens_used"] == 42
    # ...and the other agent is left untouched (no array clobbering).
    assert by_id["a1"]["status"] == "pending"
    assert by_id["a1"]["output"] is None


@pytest.mark.asyncio
async def test_update_agent_state_returns_none_for_unknown_agent(db_proxy):
    repo = CrewRunRepository(db_proxy)
    run = await repo.create_run("crew-1", "desktop-user", _run_data(["a1"]))
    result = await repo.update_agent_state(run["run_id"], "missing", {"status": "completed"})
    assert result is None


@pytest.mark.asyncio
async def test_update_agent_state_keeps_agents_a_list(db_proxy):
    """Guards against the positional-operator bug that replaced the agents
    list with a dict shaped like ``{"$": {...}}``."""
    repo = CrewRunRepository(db_proxy)
    run = await repo.create_run("crew-1", "desktop-user", _run_data(["a1", "a2"]))
    run_id = run["run_id"]

    await repo.update_agent_state(run_id, "a1", {"status": "running"})
    await repo.update_agent_state(run_id, "a2", {"status": "completed"})

    fresh = await repo.get_by_run_id(run_id)
    assert isinstance(fresh["agents"], list)
    assert len(fresh["agents"]) == 2
    assert {a["agent_id"] for a in fresh["agents"]} == {"a1", "a2"}
