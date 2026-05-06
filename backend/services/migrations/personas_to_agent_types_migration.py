"""
Migration 0003 — Personas → Agent Types
========================================

Folds the legacy ``personas`` collection into ``workspace_agents`` so the
Solo UI can present a single, tabbed agent library organised by *kind*.

Mapping
-------
| persona_type_id        | kind     |
|------------------------|----------|
| generic                | prompt   |
| web_search             | web      |
| postgresql, mysql,     | database |
| mssql, snowflake,      |          |
| mongodb                |          |
| mcp                    | mcp      |
| api_integration        | api      |
| file_operations        | file     |

Idempotent
----------
A marker row is written into ``migrations_applied`` after first successful
run; subsequent startups become a no-op. Set ``MIGRATE_DRY_RUN=1`` to log
the would-be writes without committing.

Backward compat
---------------
The original persona row is left in place — the /personas route still
resolves to the legacy data while the UI shows a "moved to Agents" banner
during one release window.

Each migrated workspace_agents row carries:
- ``_id`` and ``agent_id`` set to the persona_id (so any crew still
  referencing the old persona ID continues to resolve).
- ``kind`` derived from persona_type_id.
- ``source = "migrated_persona"``.
- The persona's credentials (encrypted blob is preserved verbatim).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger(__name__)

MIGRATION_NAME = "personas_to_agent_types_v1"
MIGRATIONS_COLLECTION = "migrations_applied"

# persona_type_id -> kind
PERSONA_TYPE_KIND_MAP: Dict[str, str] = {
    "generic": "prompt",
    "web_search": "web",
    "postgresql": "database",
    "mysql": "database",
    "mssql": "database",
    "snowflake": "database",
    "mongodb": "database",
    "mcp": "mcp",
    "api_integration": "api",
    "file_operations": "file",
    # Sane defaults for unrecognised types — treat as a prompt agent.
}

# Existing seeded workspace_agents rows from agent-library/*.md don't have a
# `kind` field. They're the 96 business agents and they're all prompt-only.
DEFAULT_KIND_FOR_LIBRARY_AGENTS = "prompt"


def _is_dry_run() -> bool:
    return os.getenv("MIGRATE_DRY_RUN", "").strip() in ("1", "true", "TRUE", "yes")


async def run_personas_to_agent_types_migration(db) -> Dict[str, Any]:
    """Idempotently fold the personas collection into workspace_agents."""
    marker_coll = db[MIGRATIONS_COLLECTION]
    marker = await marker_coll.find_one({"name": MIGRATION_NAME})
    if marker is not None:
        logger.info("Migration %s already applied; skipping", MIGRATION_NAME)
        return {"name": MIGRATION_NAME, "status": "skipped", "stats": marker.get("stats", {})}

    dry_run = _is_dry_run()
    stats = {
        "agent_library_rows_backfilled_kind": 0,
        "personas_processed": 0,
        "agents_created_from_personas": 0,
        "agents_updated_from_personas": 0,
        "personas_skipped_no_type": 0,
    }
    diff_log = []

    workspace_agents = db["workspace_agents"]
    personas = db["personas"]

    # ------------------------------------------------------------------
    # Pass 1 — backfill `kind` on existing workspace_agents rows.
    # ------------------------------------------------------------------
    cursor = workspace_agents.find({})
    rows = await cursor.to_list(length=10000)
    for row in rows:
        if row.get("kind"):
            continue
        agent_id = row.get("_id") or row.get("agent_id")
        diff_log.append({"op": "backfill_kind", "agent_id": agent_id, "kind": DEFAULT_KIND_FOR_LIBRARY_AGENTS})
        if not dry_run:
            await workspace_agents.update_one(
                {"_id": row["_id"]}, {"$set": {"kind": DEFAULT_KIND_FOR_LIBRARY_AGENTS}}
            )
        stats["agent_library_rows_backfilled_kind"] += 1

    # ------------------------------------------------------------------
    # Pass 2 — promote each persona into a workspace_agents row.
    # ------------------------------------------------------------------
    cursor = personas.find({})
    persona_rows = await cursor.to_list(length=10000)
    for persona in persona_rows:
        stats["personas_processed"] += 1
        persona_type_id = persona.get("persona_type_id") or persona.get("type")
        if not persona_type_id:
            stats["personas_skipped_no_type"] += 1
            continue

        kind = PERSONA_TYPE_KIND_MAP.get(persona_type_id, "prompt")
        persona_id = (
            persona.get("persona_id")
            or persona.get("id")
            or str(persona.get("_id"))
        )

        existing = await workspace_agents.find_one({"_id": persona_id})

        agent_doc = {
            "_id": persona_id,
            "agent_id": persona_id,
            "name": persona.get("name") or "Untitled persona",
            "slug": (persona.get("slug") or persona.get("name") or persona_id)
            .lower()
            .replace(" ", "-"),
            "description": persona.get("description") or "",
            "category": persona.get("category") or persona_type_id,
            "category_label": persona.get("category") or persona_type_id.replace("_", " ").title(),
            "icon": persona.get("icon") or "user",
            "capabilities": [],
            "frameworks": [],
            "system_prompt": persona.get("system_prompt") or "",
            "is_active": persona.get("status", "active") == "active",
            "is_system": False,
            "source": "migrated_persona",
            "created_by": persona.get("user_id") or "desktop",
            "created_at": persona.get("created_at") or datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "kind": kind,
            "persona_type_id": persona_type_id,
            "credentials": persona.get("credentials") or {},
        }

        if existing:
            stats["agents_updated_from_personas"] += 1
            diff_log.append({"op": "update", "agent_id": persona_id, "kind": kind})
            if not dry_run:
                # Preserve any user edits made directly on the workspace_agents
                # row (system_prompt etc.) — only fill in missing fields and
                # the new `kind`/`persona_type_id`/`credentials` triple.
                merge = {**agent_doc}
                for key in ("system_prompt", "name", "description"):
                    if existing.get(key):
                        merge[key] = existing[key]
                merge.pop("_id", None)
                await workspace_agents.update_one(
                    {"_id": persona_id}, {"$set": merge}
                )
        else:
            stats["agents_created_from_personas"] += 1
            diff_log.append({"op": "insert", "agent_id": persona_id, "kind": kind})
            if not dry_run:
                await workspace_agents.insert_one(agent_doc)

    # ------------------------------------------------------------------
    # Mark migration as applied.
    # ------------------------------------------------------------------
    if dry_run:
        logger.info(
            "DRY-RUN %s: %s",
            MIGRATION_NAME,
            json.dumps(stats),
        )
        for entry in diff_log[:25]:
            logger.info("  diff: %s", json.dumps(entry))
        return {"name": MIGRATION_NAME, "status": "dry_run", "stats": stats}

    await marker_coll.insert_one(
        {
            "name": MIGRATION_NAME,
            "applied_at": datetime.utcnow().isoformat(),
            "stats": stats,
        }
    )
    logger.info("Migration %s applied: %s", MIGRATION_NAME, json.dumps(stats))
    return {"name": MIGRATION_NAME, "status": "applied", "stats": stats}
