"""
Migration 0004 — Workspace → Crews/Projects + Runs
==================================================

Folds ``workspace_projects`` and ``workspace_executions`` into ``crews``
and ``crew_runs`` so the Solo UI can present a single tabbed home for
teams of agents (recurring crews and one-shot projects alike).

Schema change
-------------
- ``crews.kind``      — new field, ``"crew" | "project"`` (default: ``"crew"``).
- ``crews.migrated_from_project_id`` — back-link for promoted projects.
- ``crew_runs.trigger_type`` — already present (``manual | reactive |
  scheduled``); promoted execution rows get ``"manual"``.
- ``crew_runs.migrated_from_execution_id`` — back-link for traceability.

Idempotent
----------
Marker row in ``migrations_applied``. Set ``MIGRATE_DRY_RUN=1`` to log
the diff without committing.

In-flight safety
----------------
The originating ``workspace_projects`` / ``workspace_executions`` /
``workspace_jobs`` rows are LEFT IN PLACE. The orchestrator
(``services/workspace/orchestrator.py``) still resolves jobs via
``workspace_jobs.job_id``; deleting any of those would break runs in
flight. Cleanup happens in a later release.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

MIGRATION_NAME = "workspace_to_crew_runs_v1"
MIGRATIONS_COLLECTION = "migrations_applied"

DEFAULT_KIND_FOR_EXISTING_CREWS = "crew"


def _is_dry_run() -> bool:
    return os.getenv("MIGRATE_DRY_RUN", "").strip() in ("1", "true", "TRUE", "yes")


def _now() -> str:
    return datetime.utcnow().isoformat()


async def run_workspace_to_crew_runs_migration(db) -> Dict[str, Any]:
    marker_coll = db[MIGRATIONS_COLLECTION]
    marker = await marker_coll.find_one({"name": MIGRATION_NAME})
    if marker is not None:
        logger.info("Migration %s already applied; skipping", MIGRATION_NAME)
        return {
            "name": MIGRATION_NAME,
            "status": "skipped",
            "stats": marker.get("stats", {}),
        }

    dry_run = _is_dry_run()
    stats = {
        "crews_backfilled_kind": 0,
        "projects_processed": 0,
        "projects_promoted_to_crews": 0,
        "projects_already_promoted": 0,
        "executions_processed": 0,
        "executions_promoted_to_runs": 0,
        "executions_already_promoted": 0,
    }
    diff_log: List[Dict[str, Any]] = []

    crews = db["crews"]
    crew_runs = db["crew_runs"]
    projects = db["workspace_projects"]
    executions = db["workspace_executions"]

    # ------------------------------------------------------------------
    # Pass 1 — backfill `kind="crew"` on every existing crew row.
    # ------------------------------------------------------------------
    cursor = crews.find({})
    crew_rows = await cursor.to_list(length=10000)
    for row in crew_rows:
        if row.get("kind"):
            continue
        diff_log.append(
            {"op": "backfill_kind", "crew_id": row.get("crew_id"), "kind": DEFAULT_KIND_FOR_EXISTING_CREWS}
        )
        if not dry_run:
            await crews.update_one(
                {"_id": row["_id"]}, {"$set": {"kind": DEFAULT_KIND_FOR_EXISTING_CREWS}}
            )
        stats["crews_backfilled_kind"] += 1

    # ------------------------------------------------------------------
    # Pass 2 — promote each workspace_project to a kind="project" crew.
    # ------------------------------------------------------------------
    cursor = projects.find({})
    project_rows = await cursor.to_list(length=10000)
    for project in project_rows:
        stats["projects_processed"] += 1
        project_id = (
            project.get("project_id")
            or project.get("id")
            or str(project.get("_id"))
        )

        existing = await crews.find_one(
            {"$or": [{"crew_id": project_id}, {"migrated_from_project_id": project_id}]}
        )
        if existing:
            stats["projects_already_promoted"] += 1
            continue

        agents = []
        for idx, agent in enumerate(project.get("team_agents") or project.get("agents") or []):
            agents.append(
                {
                    "agent_id": agent.get("agent_id") or str(uuid.uuid4()),
                    "role": agent.get("role") or "custom",
                    "custom_role": agent.get("role") or None,
                    "name": agent.get("name") or f"Agent {idx + 1}",
                    "instructions": agent.get("instructions")
                    or agent.get("system_prompt")
                    or "",
                    "library_agent_id": agent.get("library_agent_id"),
                    "model_id": agent.get("model_id") or project.get("model_id"),
                    "tools": agent.get("tools") or [],
                    "order": idx,
                    "depends_on": agent.get("depends_on") or [],
                    "knowledge_base_ids": agent.get("knowledge_base_ids") or [],
                }
            )

        crew_doc = {
            "crew_id": project_id,
            "user_id": project.get("user_id") or "desktop",
            "name": project.get("name") or project.get("title") or "Untitled project",
            "description": project.get("description") or "",
            "status": "active" if project.get("status") != "archived" else "archived",
            "agents": agents,
            "execution_config": {
                "mode": "sequential",
                "max_iterations": 1,
                "timeout_seconds": 600,
                "retry_on_failure": False,
                "max_retries": 0,
                "checkpoint_enabled": bool(
                    (project.get("config") or {}).get("enable_checkpoints")
                ),
                "max_agent_invocations": 10,
                "budget_limit_usd": 1.0,
            },
            "schedule": None,
            "channel_bindings": [],
            "distribution_channels": [],
            "connection_bindings": [],
            "triggers": [],
            "approval_required": False,
            "memory_enabled": True,
            "tags": (project.get("tags") or []) + ["migrated-from-workspace"],
            "knowledge_base_ids": project.get("knowledge_base_ids") or [],
            "total_runs": project.get("execution_count") or 0,
            "total_cost_usd": 0.0,
            "last_run_at": project.get("last_execution"),
            "deleted_at": project.get("deleted_at"),
            "created_at": project.get("created_at") or _now(),
            "updated_at": _now(),
            # Phase 4 PR 3 markers
            "kind": "project",
            "migrated_from_project_id": project_id,
            "migrated_at": _now(),
        }
        diff_log.append({"op": "promote_project", "project_id": project_id, "name": crew_doc["name"]})
        if not dry_run:
            await crews.insert_one(crew_doc)
        stats["projects_promoted_to_crews"] += 1

    # ------------------------------------------------------------------
    # Pass 3 — promote each workspace_execution to a crew_runs row.
    # ------------------------------------------------------------------
    cursor = executions.find({})
    execution_rows = await cursor.to_list(length=20000)
    for execution in execution_rows:
        stats["executions_processed"] += 1
        execution_id = (
            execution.get("execution_id")
            or execution.get("id")
            or str(execution.get("_id"))
        )
        project_id = execution.get("project_id")

        existing = await crew_runs.find_one(
            {"$or": [
                {"run_id": execution_id},
                {"migrated_from_execution_id": execution_id},
            ]}
        )
        if existing:
            stats["executions_already_promoted"] += 1
            continue

        agents_state = []
        for step in execution.get("steps") or []:
            agents_state.append(
                {
                    "agent_id": step.get("agent_id") or str(uuid.uuid4()),
                    "name": step.get("agent_name") or "Agent",
                    "role": step.get("role") or "custom",
                    "status": _map_step_status(step.get("status")),
                    "started_at": step.get("started_at"),
                    "completed_at": step.get("completed_at"),
                    "output": step.get("output_summary") or step.get("output"),
                    "error": step.get("error"),
                    "tokens_used": int(step.get("tokens_used") or 0),
                    "cost_usd": float(step.get("cost_usd") or 0.0),
                    "iteration": int(step.get("step_index") or 0),
                }
            )

        run_doc = {
            "run_id": execution_id,
            "crew_id": project_id,  # the promoted crew uses the project_id verbatim
            "user_id": execution.get("user_id") or "desktop",
            "status": _map_run_status(execution.get("status")),
            "input": None,
            "input_data": None,
            "agents": agents_state,
            "result": (execution.get("result") or {}).get("summary")
            if isinstance(execution.get("result"), dict)
            else execution.get("result"),
            "error": execution.get("error"),
            "total_tokens": int((execution.get("metrics") or {}).get("total_tokens") or 0),
            "total_cost_usd": float((execution.get("metrics") or {}).get("total_cost") or 0.0),
            "started_at": execution.get("started_at"),
            "completed_at": execution.get("completed_at"),
            "duration_ms": (execution.get("metrics") or {}).get("duration_ms"),
            "trigger_type": "manual",
            "trigger_source": "manual",
            "created_at": execution.get("created_at") or _now(),
            "updated_at": _now(),
            "migrated_from_execution_id": execution_id,
            "migrated_at": _now(),
        }
        diff_log.append({"op": "promote_execution", "execution_id": execution_id})
        if not dry_run:
            await crew_runs.insert_one(run_doc)
        stats["executions_promoted_to_runs"] += 1

    # ------------------------------------------------------------------
    # Mark migration as applied.
    # ------------------------------------------------------------------
    if dry_run:
        logger.info("DRY-RUN %s: %s", MIGRATION_NAME, json.dumps(stats))
        for entry in diff_log[:25]:
            logger.info("  diff: %s", json.dumps(entry))
        return {"name": MIGRATION_NAME, "status": "dry_run", "stats": stats}

    await marker_coll.insert_one(
        {
            "name": MIGRATION_NAME,
            "applied_at": _now(),
            "stats": stats,
        }
    )
    logger.info("Migration %s applied: %s", MIGRATION_NAME, json.dumps(stats))
    return {"name": MIGRATION_NAME, "status": "applied", "stats": stats}


def _map_step_status(status: str | None) -> str:
    return {
        "pending": "pending",
        "running": "running",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }.get(status or "pending", "pending")


def _map_run_status(status: str | None) -> str:
    return {
        "pending": "pending",
        "queued": "pending",
        "running": "running",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }.get(status or "pending", "pending")
