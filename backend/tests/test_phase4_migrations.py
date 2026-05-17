"""Tests for Phase 4 PR 10 — migrations from personas/workspace into the
unified agent + crew schema.

Covers two migrations:
- ``services.migrations.personas_to_agent_types_migration``
- ``services.migrations.workspace_to_crew_runs_migration``

Both rely on the Motor-compat layer over SQLite (``adapters/motor_compat.py``)
exercised via the ``db_proxy`` fixture in ``tests/conftest.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import pytest

from services.migrations.personas_to_agent_types_migration import (
    MIGRATION_NAME as PERSONAS_MIGRATION_NAME,
    MIGRATIONS_COLLECTION as PERSONAS_MARKER_COLLECTION,
    run_personas_to_agent_types_migration,
)
from services.migrations.workspace_to_crew_runs_migration import (
    MIGRATION_NAME as WORKSPACE_MIGRATION_NAME,
    MIGRATIONS_COLLECTION as WORKSPACE_MARKER_COLLECTION,
    run_workspace_to_crew_runs_migration,
)


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


async def _seed_persona(db, **fields: Any) -> Dict[str, Any]:
    """Insert a personas doc with sensible defaults; return the doc."""
    persona_id = fields.get("persona_id") or fields.get("_id") or "p-test"
    doc: Dict[str, Any] = {
        "_id": persona_id,
        "persona_id": persona_id,
        "name": "Test Persona",
        "description": "A persona used by the migration test",
        "persona_type_id": "generic",
        "system_prompt": "default-from-persona",
        "status": "active",
        "user_id": "desktop",
        "credentials": {},
        "created_at": datetime.utcnow().isoformat(),
    }
    doc.update(fields)
    # Make sure _id and persona_id stay aligned if caller passed only one.
    doc["_id"] = doc.get("_id") or doc["persona_id"]
    doc["persona_id"] = doc.get("persona_id") or doc["_id"]
    await db["personas"].insert_one(doc)
    return doc


async def _seed_agent(db, **fields: Any) -> Dict[str, Any]:
    """Insert a workspace_agents doc; return the doc."""
    agent_id = fields.get("agent_id") or fields.get("_id") or "a-test"
    doc: Dict[str, Any] = {
        "_id": agent_id,
        "agent_id": agent_id,
        "name": "Test Agent",
        "slug": "test-agent",
        "description": "",
        "category": "general",
        "category_label": "General",
        "icon": "user",
        "capabilities": [],
        "frameworks": [],
        "system_prompt": "library default",
        "is_active": True,
        "is_system": True,
        "source": "library",
        "created_by": "desktop",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    doc.update(fields)
    doc["_id"] = doc.get("_id") or doc["agent_id"]
    doc["agent_id"] = doc.get("agent_id") or doc["_id"]
    await db["workspace_agents"].insert_one(doc)
    return doc


async def _seed_project(db, **fields: Any) -> Dict[str, Any]:
    project_id = fields.get("project_id") or fields.get("_id") or "proj-test"
    doc: Dict[str, Any] = {
        "_id": project_id,
        "project_id": project_id,
        "name": "Test project",
        "description": "",
        "status": "active",
        "user_id": "desktop",
        "team_agents": [],
        "created_at": datetime.utcnow().isoformat(),
    }
    doc.update(fields)
    doc["_id"] = doc.get("_id") or doc["project_id"]
    doc["project_id"] = doc.get("project_id") or doc["_id"]
    await db["workspace_projects"].insert_one(doc)
    return doc


async def _seed_execution(db, **fields: Any) -> Dict[str, Any]:
    execution_id = fields.get("execution_id") or fields.get("_id") or "exec-test"
    doc: Dict[str, Any] = {
        "_id": execution_id,
        "execution_id": execution_id,
        "project_id": fields.get("project_id") or "proj-test",
        "user_id": "desktop",
        "status": "completed",
        "steps": [],
        "metrics": {},
        "created_at": datetime.utcnow().isoformat(),
    }
    doc.update(fields)
    doc["_id"] = doc.get("_id") or doc["execution_id"]
    doc["execution_id"] = doc.get("execution_id") or doc["_id"]
    await db["workspace_executions"].insert_one(doc)
    return doc


async def _seed_crew(db, **fields: Any) -> Dict[str, Any]:
    crew_id = fields.get("crew_id") or fields.get("_id") or "crew-test"
    doc: Dict[str, Any] = {
        "_id": crew_id,
        "crew_id": crew_id,
        "user_id": "desktop",
        "name": "Test crew",
        "status": "active",
        "agents": [],
        "created_at": datetime.utcnow().isoformat(),
    }
    doc.update(fields)
    doc["_id"] = doc.get("_id") or doc["crew_id"]
    doc["crew_id"] = doc.get("crew_id") or doc["_id"]
    await db["crews"].insert_one(doc)
    return doc


# ===========================================================================
# Test set A — personas_to_agent_types_migration
# ===========================================================================


@pytest.mark.asyncio
async def test_personas_migration_backfills_kind_on_existing_agents(db_proxy):
    await _seed_agent(db_proxy, _id="lib-1", agent_id="lib-1", name="Library One")
    await _seed_agent(db_proxy, _id="lib-2", agent_id="lib-2", name="Library Two")

    result = await run_personas_to_agent_types_migration(db_proxy)

    assert result["status"] == "applied"
    assert result["stats"]["agent_library_rows_backfilled_kind"] == 2

    rows = await db_proxy["workspace_agents"].find({}).to_list(length=100)
    by_id = {r["_id"]: r for r in rows}
    assert by_id["lib-1"]["kind"] == "prompt"
    assert by_id["lib-2"]["kind"] == "prompt"


@pytest.mark.asyncio
async def test_personas_migration_promotes_each_persona(db_proxy):
    expected = {
        "p-generic": "prompt",
        "p-postgres": "database",
        "p-web": "web",
        "p-mcp": "mcp",
        "p-api": "api",
        "p-file": "file",
    }
    type_for = {
        "p-generic": "generic",
        "p-postgres": "postgresql",
        "p-web": "web_search",
        "p-mcp": "mcp",
        "p-api": "api_integration",
        "p-file": "file_operations",
    }
    for pid, ptype in type_for.items():
        await _seed_persona(
            db_proxy,
            persona_id=pid,
            _id=pid,
            persona_type_id=ptype,
            name=f"Persona {pid}",
        )

    result = await run_personas_to_agent_types_migration(db_proxy)

    assert result["status"] == "applied"
    assert result["stats"]["agents_created_from_personas"] == 6

    for pid, expected_kind in expected.items():
        row = await db_proxy["workspace_agents"].find_one({"_id": pid})
        assert row is not None, f"missing workspace_agents row for {pid}"
        assert row["_id"] == pid
        assert row["agent_id"] == pid
        assert row["kind"] == expected_kind


@pytest.mark.asyncio
async def test_personas_migration_is_idempotent(db_proxy):
    await _seed_persona(
        db_proxy, persona_id="p-only", _id="p-only", persona_type_id="generic"
    )

    first = await run_personas_to_agent_types_migration(db_proxy)
    assert first["status"] == "applied"

    rows_after_first = await db_proxy["workspace_agents"].find({}).to_list(length=100)
    count_after_first = len(rows_after_first)
    assert count_after_first == 1

    second = await run_personas_to_agent_types_migration(db_proxy)
    assert second["status"] == "skipped"
    # Skipped runs return the persisted marker stats, which equal the first
    # run's stats.
    assert second["stats"] == first["stats"]

    rows_after_second = await db_proxy["workspace_agents"].find({}).to_list(length=100)
    assert len(rows_after_second) == count_after_first


@pytest.mark.asyncio
async def test_personas_migration_dry_run_writes_nothing(db_proxy, monkeypatch):
    monkeypatch.setenv("MIGRATE_DRY_RUN", "1")
    await _seed_persona(
        db_proxy, persona_id="p-dry", _id="p-dry", persona_type_id="generic"
    )

    result = await run_personas_to_agent_types_migration(db_proxy)

    assert result["status"] == "dry_run"

    marker = await db_proxy[PERSONAS_MARKER_COLLECTION].find_one(
        {"name": PERSONAS_MIGRATION_NAME}
    )
    assert marker is None

    rows = await db_proxy["workspace_agents"].find({}).to_list(length=100)
    assert rows == []


@pytest.mark.asyncio
async def test_personas_migration_skips_persona_without_type(db_proxy):
    # Insert a persona whose persona_type_id and "type" are both falsy.
    await db_proxy["personas"].insert_one(
        {
            "_id": "p-typeless",
            "persona_id": "p-typeless",
            "name": "Typeless",
            "persona_type_id": None,
            "user_id": "desktop",
            "created_at": datetime.utcnow().isoformat(),
        }
    )

    result = await run_personas_to_agent_types_migration(db_proxy)

    assert result["status"] == "applied"
    assert result["stats"]["personas_skipped_no_type"] == 1

    row = await db_proxy["workspace_agents"].find_one({"_id": "p-typeless"})
    assert row is None


@pytest.mark.asyncio
async def test_personas_migration_preserves_existing_agent_fields_on_update(db_proxy):
    # A workspace_agents row already exists for "p1" with a user-edited prompt.
    await _seed_agent(
        db_proxy,
        _id="p1",
        agent_id="p1",
        name="User-edited name",
        system_prompt="user-edited",
    )
    # And there's a persona with the same id but a different default prompt.
    await _seed_persona(
        db_proxy,
        persona_id="p1",
        _id="p1",
        persona_type_id="generic",
        name="Persona default name",
        system_prompt="default-from-persona",
    )

    result = await run_personas_to_agent_types_migration(db_proxy)
    assert result["status"] == "applied"
    assert result["stats"]["agents_updated_from_personas"] == 1

    row = await db_proxy["workspace_agents"].find_one({"_id": "p1"})
    assert row is not None
    assert row["system_prompt"] == "user-edited"
    # kind/persona_type_id should still be applied even though existing fields
    # were preserved.
    assert row["kind"] == "prompt"
    assert row["persona_type_id"] == "generic"


# ===========================================================================
# Test set B — workspace_to_crew_runs_migration
# ===========================================================================


@pytest.mark.asyncio
async def test_workspace_migration_backfills_kind_on_existing_crews(db_proxy):
    await _seed_crew(db_proxy, _id="c-1", crew_id="c-1", name="Existing 1")
    await _seed_crew(db_proxy, _id="c-2", crew_id="c-2", name="Existing 2")

    result = await run_workspace_to_crew_runs_migration(db_proxy)

    assert result["status"] == "applied"
    assert result["stats"]["crews_backfilled_kind"] == 2

    rows = await db_proxy["crews"].find({}).to_list(length=100)
    by_id = {r["_id"]: r for r in rows}
    assert by_id["c-1"]["kind"] == "crew"
    assert by_id["c-2"]["kind"] == "crew"


@pytest.mark.asyncio
async def test_workspace_migration_promotes_workspace_project(db_proxy):
    await _seed_project(
        db_proxy,
        project_id="proj1",
        _id="proj1",
        name="My project",
        team_agents=[
            {
                "agent_id": "agent-a",
                "name": "Agent A",
                "role": "researcher",
                "instructions": "do stuff",
            }
        ],
        user_id="desktop",
        created_at="2026-01-01T00:00:00",
    )

    result = await run_workspace_to_crew_runs_migration(db_proxy)

    assert result["status"] == "applied"
    assert result["stats"]["projects_promoted_to_crews"] == 1

    crew = await db_proxy["crews"].find_one({"crew_id": "proj1"})
    assert crew is not None
    assert crew["crew_id"] == "proj1"
    assert crew["kind"] == "project"
    assert crew["migrated_from_project_id"] == "proj1"
    assert crew["name"] == "My project"
    assert "migrated-from-workspace" in crew["tags"]


@pytest.mark.asyncio
async def test_workspace_migration_promotes_workspace_executions(db_proxy):
    await _seed_project(db_proxy, project_id="proj-exec", _id="proj-exec")
    await _seed_execution(
        db_proxy,
        execution_id="exec-1",
        _id="exec-1",
        project_id="proj-exec",
        status="completed",
    )
    await _seed_execution(
        db_proxy,
        execution_id="exec-2",
        _id="exec-2",
        project_id="proj-exec",
        status="failed",
    )

    result = await run_workspace_to_crew_runs_migration(db_proxy)

    assert result["status"] == "applied"
    assert result["stats"]["executions_promoted_to_runs"] == 2

    runs = await db_proxy["crew_runs"].find({}).to_list(length=100)
    assert len(runs) == 2
    by_migrated = {r["migrated_from_execution_id"]: r for r in runs}
    assert set(by_migrated.keys()) == {"exec-1", "exec-2"}
    for run in runs:
        assert run["crew_id"] == "proj-exec"
        assert run["trigger_type"] == "manual"


@pytest.mark.asyncio
async def test_workspace_migration_is_idempotent(db_proxy):
    await _seed_project(db_proxy, project_id="proj-idem", _id="proj-idem")
    await _seed_execution(
        db_proxy,
        execution_id="exec-idem",
        _id="exec-idem",
        project_id="proj-idem",
    )

    first = await run_workspace_to_crew_runs_migration(db_proxy)
    assert first["status"] == "applied"

    crews_before = await db_proxy["crews"].find({}).to_list(length=100)
    runs_before = await db_proxy["crew_runs"].find({}).to_list(length=100)

    second = await run_workspace_to_crew_runs_migration(db_proxy)
    assert second["status"] == "skipped"
    assert second["stats"] == first["stats"]

    crews_after = await db_proxy["crews"].find({}).to_list(length=100)
    runs_after = await db_proxy["crew_runs"].find({}).to_list(length=100)
    assert len(crews_after) == len(crews_before)
    assert len(runs_after) == len(runs_before)


@pytest.mark.asyncio
async def test_workspace_migration_already_promoted_skipped_per_row(db_proxy):
    # Simulate a partial-recovery scenario: project exists in workspace_projects
    # AND there's already a crew row for it. The marker is missing, so the
    # migration runs but should not double-promote.
    await _seed_project(db_proxy, project_id="p1", _id="p1", name="Partial")
    await _seed_crew(
        db_proxy,
        _id="p1",
        crew_id="p1",
        name="Partial",
        kind="project",
        migrated_from_project_id="p1",
    )

    # Defensively delete any marker that may have been created.
    await db_proxy[WORKSPACE_MARKER_COLLECTION].delete_many(
        {"name": WORKSPACE_MIGRATION_NAME}
    )

    result = await run_workspace_to_crew_runs_migration(db_proxy)

    assert result["status"] == "applied"
    assert result["stats"]["projects_already_promoted"] == 1
    assert result["stats"]["projects_promoted_to_crews"] == 0

    crew_rows = await db_proxy["crews"].find({"crew_id": "p1"}).to_list(length=100)
    assert len(crew_rows) == 1


# ===========================================================================
# Cross-cutting
# ===========================================================================


@pytest.mark.asyncio
async def test_both_migrations_compose_cleanly(db_proxy):
    await _seed_persona(
        db_proxy,
        persona_id="p-compose",
        _id="p-compose",
        persona_type_id="postgresql",
        name="Compose Persona",
    )
    await _seed_project(
        db_proxy,
        project_id="proj-compose",
        _id="proj-compose",
        name="Compose Project",
    )

    persona_result = await run_personas_to_agent_types_migration(db_proxy)
    workspace_result = await run_workspace_to_crew_runs_migration(db_proxy)

    assert persona_result["status"] == "applied"
    assert workspace_result["status"] == "applied"
    assert persona_result["stats"]["agents_created_from_personas"] == 1
    assert workspace_result["stats"]["projects_promoted_to_crews"] == 1

    # Persona is in workspace_agents.
    agent = await db_proxy["workspace_agents"].find_one({"_id": "p-compose"})
    assert agent is not None
    assert agent["kind"] == "database"

    # Project is in crews.
    crew = await db_proxy["crews"].find_one({"crew_id": "proj-compose"})
    assert crew is not None
    assert crew["kind"] == "project"

    # Both markers persisted.
    p_marker = await db_proxy[PERSONAS_MARKER_COLLECTION].find_one(
        {"name": PERSONAS_MIGRATION_NAME}
    )
    w_marker = await db_proxy[WORKSPACE_MARKER_COLLECTION].find_one(
        {"name": WORKSPACE_MIGRATION_NAME}
    )
    assert p_marker is not None
    assert w_marker is not None
