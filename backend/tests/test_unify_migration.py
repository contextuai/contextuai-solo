"""Tests for Phase 3 PR 1 unify_connections migration."""

import os

import pytest
import pytest_asyncio

from services.migrations.unify_connections_migration import (
    MARKER_COLLECTION,
    MIGRATION_NAME,
    run_unify_connections_migration,
)


@pytest_asyncio.fixture
async def seeded_db(db_proxy):
    """Seed the test DB with a few legacy crews and a distribution channel."""
    crews = db_proxy["crews"]

    # Crew 1: legacy channel_bindings, one with approval_required
    await crews.insert_one({
        "crew_id": "crew-1",
        "user_id": "u1",
        "name": "Legacy Telegram",
        "status": "active",
        "channel_bindings": [
            {"channel_type": "telegram", "enabled": True, "approval_required": True},
            {"channel_type": "discord", "enabled": True, "approval_required": False},
        ],
    })

    # Crew 2: no bindings at all, missing new fields entirely
    await crews.insert_one({
        "crew_id": "crew-2",
        "user_id": "u1",
        "name": "Bare",
        "status": "active",
    })

    # Crew 3: already migrated (has connection_bindings) — must not double-convert
    await crews.insert_one({
        "crew_id": "crew-3",
        "user_id": "u1",
        "name": "Already Migrated",
        "status": "active",
        "channel_bindings": [
            {"channel_type": "reddit", "enabled": True, "approval_required": False},
        ],
        "connection_bindings": [
            {"connection_id": "reddit-custom", "platform": "reddit", "direction": "inbound"},
        ],
    })

    await db_proxy["distribution_channels"].insert_one({
        "channel_type": "linkedin",
        "config": {},
        "enabled": True,
    })

    return db_proxy


@pytest.mark.asyncio
async def test_migration_converts_legacy_bindings(seeded_db):
    stats = await run_unify_connections_migration(seeded_db)

    assert stats["skipped"] is False
    assert stats["crews_processed"] == 3
    # Crew 1: 2 bindings. Crew 3: already has connection_bindings (skipped).
    assert stats["bindings_converted"] == 2
    assert stats["crews_marked_approval_required"] == 1
    assert stats["distribution_channels_orphaned"] == 1

    crew1 = await seeded_db["crews"].find_one({"crew_id": "crew-1"})
    assert len(crew1["connection_bindings"]) == 2
    platforms = {b["platform"] for b in crew1["connection_bindings"]}
    assert platforms == {"telegram", "discord"}
    for b in crew1["connection_bindings"]:
        assert b["direction"] == "both"
    assert crew1["approval_required"] is True

    crew2 = await seeded_db["crews"].find_one({"crew_id": "crew-2"})
    assert crew2["connection_bindings"] == []
    assert crew2["triggers"] == []
    assert crew2["approval_required"] is False

    # Crew 3 must keep its pre-existing connection_bindings untouched.
    crew3 = await seeded_db["crews"].find_one({"crew_id": "crew-3"})
    assert len(crew3["connection_bindings"]) == 1
    assert crew3["connection_bindings"][0]["connection_id"] == "reddit-custom"


@pytest.mark.asyncio
async def test_migration_is_idempotent(seeded_db):
    first = await run_unify_connections_migration(seeded_db)
    assert first["skipped"] is False

    # Tamper with a crew to prove second run doesn't re-touch it.
    await seeded_db["crews"].update_one(
        {"crew_id": "crew-1"},
        {"$set": {"connection_bindings": [{"connection_id": "x", "platform": "telegram", "direction": "outbound"}]}},
    )

    second = await run_unify_connections_migration(seeded_db)
    assert second["skipped"] is True

    crew1 = await seeded_db["crews"].find_one({"crew_id": "crew-1"})
    # Still the tampered value — migration did not run again
    assert crew1["connection_bindings"][0]["connection_id"] == "x"


@pytest.mark.asyncio
async def test_dry_run_does_not_write(seeded_db, monkeypatch):
    monkeypatch.setenv("MIGRATE_DRY_RUN", "1")
    stats = await run_unify_connections_migration(seeded_db)

    assert stats["dry_run"] is True
    assert stats["bindings_converted"] == 2  # still reports what it *would* do

    # Marker NOT written
    marker = await seeded_db[MARKER_COLLECTION].find_one({"name": MIGRATION_NAME})
    assert marker is None

    # Crew 1 NOT mutated
    crew1 = await seeded_db["crews"].find_one({"crew_id": "crew-1"})
    assert "connection_bindings" not in crew1 or crew1.get("connection_bindings") == []


@pytest.mark.asyncio
async def test_migration_survives_missing_distribution_collection(db_proxy):
    # No seeding → no distribution_channels rows
    await db_proxy["crews"].insert_one({
        "crew_id": "solo",
        "user_id": "u1",
        "name": "Solo",
        "status": "active",
    })
    stats = await run_unify_connections_migration(db_proxy)
    assert stats["skipped"] is False
    assert stats["crews_processed"] == 1
