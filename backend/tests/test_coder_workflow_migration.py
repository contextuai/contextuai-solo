"""Tests for coder_workflow_mode_migration (PR 14)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from services.migrations.coder_workflow_mode_migration import (
    run_coder_workflow_mode_migration,
)


@pytest_asyncio.fixture
async def clean_db(db_proxy):
    """Yield a db_proxy with the migrations_applied collection pre-cleared."""
    coll = db_proxy["migrations_applied"]
    await coll.delete_many({"name": "coder_workflow_mode_backfill_v1"})
    yield db_proxy
    # Clean up after test.
    await coll.delete_many({"name": "coder_workflow_mode_backfill_v1"})


@pytest.mark.asyncio
async def test_migration_backfills_missing_workflow_mode(clean_db):
    projects = clean_db["coder_projects"]

    # Seed two rows without workflow_mode.
    for _ in range(2):
        await projects.insert_one({
            "_id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "name": "Old Project",
            "folder_path": "/tmp/old",
            "status": "created",
        })

    result = await run_coder_workflow_mode_migration(clean_db)
    assert result["status"] == "applied"
    assert result["projects_updated"] == 2

    # Every row should now have workflow_mode = "solo".
    rows = await projects.find({}).to_list(length=100)
    assert all(r.get("workflow_mode") == "solo" for r in rows)


@pytest.mark.asyncio
async def test_migration_skips_rows_already_having_workflow_mode(clean_db):
    projects = clean_db["coder_projects"]

    # Insert one row that already has workflow_mode.
    await projects.insert_one({
        "_id": str(uuid.uuid4()),
        "project_id": str(uuid.uuid4()),
        "name": "Modern Project",
        "folder_path": "/tmp/modern",
        "workflow_mode": "sequential",
        "status": "created",
    })

    result = await run_coder_workflow_mode_migration(clean_db)
    assert result["status"] == "applied"
    # The already-filled row must not have been touched.
    assert result["projects_updated"] == 0

    rows = await projects.find({}).to_list(length=100)
    assert rows[0]["workflow_mode"] == "sequential"


@pytest.mark.asyncio
async def test_migration_is_idempotent(clean_db):
    projects = clean_db["coder_projects"]
    await projects.insert_one({
        "_id": str(uuid.uuid4()),
        "project_id": str(uuid.uuid4()),
        "name": "Idempotent",
        "folder_path": "/tmp/idemp",
        "status": "created",
    })

    result1 = await run_coder_workflow_mode_migration(clean_db)
    assert result1["status"] == "applied"

    result2 = await run_coder_workflow_mode_migration(clean_db)
    assert result2["status"] == "skipped"

    # Value unchanged after second run.
    rows = await projects.find({}).to_list(length=100)
    assert rows[0]["workflow_mode"] == "solo"


@pytest.mark.asyncio
async def test_migration_no_projects_runs_cleanly(clean_db):
    """Migration on an empty collection should complete without error."""
    result = await run_coder_workflow_mode_migration(clean_db)
    assert result["status"] == "applied"
    assert result["projects_updated"] == 0
