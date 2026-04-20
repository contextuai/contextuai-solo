"""
Phase 3 PR 1 migration: backfill connection_bindings, triggers, approval_required.

Idempotent. Inline at startup. Tracks completion in the `migrations_applied`
collection. Set MIGRATE_DRY_RUN=1 to log the diff without writing.

What it does
------------
1. For every crew with non-empty legacy `channel_bindings` and empty
   `connection_bindings`, convert each binding to the new schema with
   `direction="both"` (preserves current behavior — bound channels were
   implicitly bidirectional).
2. If any legacy binding had `approval_required=true`, set the new
   top-level `crew.approval_required=true`.
3. Defaults `triggers=[]`, `connection_bindings=[]`, `approval_required=false`
   on any crew missing the fields entirely.
4. Records orphan `distribution_channels` (no matching crew) for follow-up.

The migration does NOT delete `channel_bindings` — they stay alongside the new
fields until PR 4 retires the legacy code path.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger(__name__)

MIGRATION_NAME = "unify_connections_v1"
MARKER_COLLECTION = "migrations_applied"


def _is_dry_run() -> bool:
    return os.environ.get("MIGRATE_DRY_RUN", "").strip() in ("1", "true", "True")


def _connection_id_for(channel_type: str) -> str:
    """For legacy bindings, the channel_type is the de-facto connection identifier
    (single-user app: one Telegram, one Discord, etc.). PR 2's connection_service
    normalises this to real record IDs."""
    return channel_type


async def run_unify_connections_migration(db) -> Dict[str, Any]:
    """Run the migration. Returns a stats dict (always — even on dry run / no-op)."""
    dry_run = _is_dry_run()
    stats: Dict[str, Any] = {
        "name": MIGRATION_NAME,
        "dry_run": dry_run,
        "skipped": False,
        "crews_processed": 0,
        "bindings_converted": 0,
        "crews_marked_approval_required": 0,
        "crews_initialised_empty": 0,
        "distribution_channels_orphaned": 0,
    }

    marker_collection = db[MARKER_COLLECTION]
    existing = await marker_collection.find_one({"name": MIGRATION_NAME})
    if existing:
        stats["skipped"] = True
        logger.info("Migration %s already applied at %s — skipping",
                    MIGRATION_NAME, existing.get("applied_at"))
        return stats

    crews_collection = db["crews"]
    cursor = crews_collection.find({})
    diff_log = []

    async for crew in cursor:
        stats["crews_processed"] += 1
        crew_id = crew.get("crew_id") or str(crew.get("_id"))
        legacy_bindings = crew.get("channel_bindings") or []
        new_bindings = crew.get("connection_bindings") or []
        crew_changes: Dict[str, Any] = {}

        if legacy_bindings and not new_bindings:
            converted = []
            any_approval = False
            for binding in legacy_bindings:
                channel_type = binding.get("channel_type")
                if not channel_type:
                    continue
                converted.append({
                    "connection_id": _connection_id_for(channel_type),
                    "platform": channel_type,
                    "direction": "both",
                })
                if binding.get("approval_required"):
                    any_approval = True

            if converted:
                crew_changes["connection_bindings"] = converted
                stats["bindings_converted"] += len(converted)

            if any_approval and not crew.get("approval_required"):
                crew_changes["approval_required"] = True
                stats["crews_marked_approval_required"] += 1

        if "connection_bindings" not in crew:
            crew_changes.setdefault("connection_bindings", new_bindings)
            stats["crews_initialised_empty"] += 1
        if "triggers" not in crew:
            crew_changes.setdefault("triggers", crew.get("triggers") or [])
        if "approval_required" not in crew:
            crew_changes.setdefault("approval_required", bool(crew.get("approval_required")))

        if crew_changes:
            diff_log.append({"crew_id": crew_id, "changes": crew_changes})
            if not dry_run:
                await crews_collection.update_one(
                    {"_id": crew["_id"]},
                    {"$set": crew_changes},
                )

    # Orphan check: distribution_channels with no crew tied to them.
    # In v1 we just count and log — PR 2 wires real ownership.
    try:
        dc_collection = db["distribution_channels"]
        dc_count = await dc_collection.count_documents({})
        stats["distribution_channels_orphaned"] = dc_count
    except Exception:
        # Collection may not exist yet on a fresh install
        pass

    if dry_run:
        logger.info(
            "[DRY RUN] %s would touch %d crew(s); diff:\n%s",
            MIGRATION_NAME,
            len(diff_log),
            json.dumps(diff_log, indent=2, default=str)[:4000],
        )
        return stats

    await marker_collection.insert_one({
        "name": MIGRATION_NAME,
        "applied_at": datetime.utcnow().isoformat(),
        "stats": {k: v for k, v in stats.items() if k != "name"},
    })
    logger.info("Migration %s applied: %s", MIGRATION_NAME, stats)
    return stats
