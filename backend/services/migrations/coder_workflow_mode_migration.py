"""
Migration — Coder workflow_mode backfill
=========================================

Sets ``workflow_mode = "solo"`` on every ``coder_projects`` row that does not
already have the field.  Idempotent: a marker row in ``migrations_applied``
prevents re-running.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

MIGRATION_NAME = "coder_workflow_mode_backfill_v1"
MIGRATIONS_COLLECTION = "migrations_applied"


async def run_coder_workflow_mode_migration(db) -> Dict[str, Any]:
    """Idempotently backfill workflow_mode on all coder_projects rows."""
    marker_coll = db[MIGRATIONS_COLLECTION]
    marker = await marker_coll.find_one({"name": MIGRATION_NAME})
    if marker is not None:
        logger.info("Migration %s already applied; skipping", MIGRATION_NAME)
        return {"name": MIGRATION_NAME, "status": "skipped"}

    projects_coll = db["coder_projects"]
    cursor = projects_coll.find({})
    rows = await cursor.to_list(length=10000)

    updated = 0
    for row in rows:
        if row.get("workflow_mode"):
            continue
        await projects_coll.update_one(
            {"_id": row["_id"]},
            {"$set": {"workflow_mode": "solo"}},
        )
        updated += 1

    await marker_coll.insert_one(
        {
            "name": MIGRATION_NAME,
            "applied_at": __import__("datetime").datetime.utcnow().isoformat(),
            "stats": {"projects_updated": updated},
        }
    )
    logger.info("Migration %s applied: %d row(s) updated", MIGRATION_NAME, updated)
    return {"name": MIGRATION_NAME, "status": "applied", "projects_updated": updated}
