"""Automations REST + SSE API.

Endpoints
---------
- GET    /api/v1/automations                              — list automations
- POST   /api/v1/automations                              — create
- GET    /api/v1/automations/{automation_id}              — fetch one
- PUT    /api/v1/automations/{automation_id}              — update
- DELETE /api/v1/automations/{automation_id}              — delete
- POST   /api/v1/automations/validate                     — validate a free-form prompt
- POST   /api/v1/automations/{automation_id}/validate     — validate stored prompt
- POST   /api/v1/automations/{automation_id}/run          — run synchronously, return final response
- GET    /api/v1/automations/{automation_id}/executions   — execution history for one
- GET    /api/v1/automations/executions/recent            — execution history across all
- GET    /api/v1/automations/executions/{execution_id}    — fetch one execution
- GET    /api/v1/automations/executions/{execution_id}/stream — SSE progress
- POST   /api/v1/automations/{automation_id}/promote-to-crew  — bridge to Crews
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from database import get_database
from models.automation_models import (
    AutomationCreate,
    AutomationExecutionRequest,
    AutomationExecutionResponse,
    AutomationListResponse,
    AutomationResponse,
    AutomationStatus,
    AutomationUpdate,
    AutomationValidation,
    ExecutionHistoryResponse,
    ExecutionMode,
    ExecutionStep,
    PromoteToCrewRequest,
    ValidationRequest,
)
from repositories.automation_execution_repository import (
    AutomationExecutionRepository,
)
from repositories.automation_repository import AutomationRepository
from services.automation_engine import automation_engine
from services.automation_parser import prompt_parser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/automations", tags=["automations"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def _auto_repo(db=Depends(get_database)) -> AutomationRepository:
    return AutomationRepository(db)


def _exec_repo(db=Depends(get_database)) -> AutomationExecutionRepository:
    return AutomationExecutionRepository(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_automation_response(row: Dict[str, Any]) -> AutomationResponse:
    return AutomationResponse(
        automation_id=row["automation_id"],
        name=row.get("name", ""),
        description=row.get("description", ""),
        prompt_template=row.get("prompt_template", ""),
        trigger_type=row.get("trigger_type", "manual"),
        trigger_config=row.get("trigger_config"),
        status=row.get("status", "draft"),
        created_at=row.get("created_at", ""),
        updated_at=row.get("updated_at", ""),
        last_run=row.get("last_run"),
        run_count=row.get("run_count", 0),
        personas_detected=row.get("personas_detected") or [],
        execution_mode=row.get("execution_mode", "smart"),
        output_actions=row.get("output_actions") or [],
        model_id=row.get("model_id"),
    )


def _to_execution_response(row: Dict[str, Any]) -> AutomationExecutionResponse:
    raw_steps = row.get("steps") or []
    steps: List[ExecutionStep] = []
    for s in raw_steps:
        try:
            steps.append(ExecutionStep(**s))
        except Exception:
            steps.append(
                ExecutionStep(
                    step_number=s.get("step_number", 0),
                    persona=s.get("persona", "?"),
                    instruction=s.get("instruction", ""),
                    full_prompt=s.get("full_prompt", ""),
                    result=s.get("result", ""),
                    status=s.get("status", "pending"),
                    error=s.get("error"),
                    duration_ms=int(s.get("duration_ms") or 0),
                )
            )

    return AutomationExecutionResponse(
        execution_id=row["execution_id"],
        automation_id=row["automation_id"],
        status=row.get("status", "running"),
        started_at=row.get("started_at", ""),
        completed_at=row.get("completed_at"),
        duration_ms=row.get("duration_ms"),
        steps=steps,
        final_result=row.get("result") or "",
        error_message=row.get("error"),
        total_steps=row.get("total_steps") or len(steps),
        successful_steps=row.get("successful_steps") or 0,
        failed_steps=row.get("failed_steps") or 0,
        output_results=row.get("output_results"),
    )


async def _validate_prompt(prompt: str, db) -> AutomationValidation:
    parsed = prompt_parser.parse(prompt)
    personas = parsed["personas"]

    # Cross-check against the agent library so unknown @agents become errors.
    errors: List[str] = []
    if personas:
        coll = db["workspace_agents"]
        cursor = coll.find({})
        rows = await cursor.to_list(length=500)
        available = {r.get("slug") for r in rows if r.get("slug")} | {
            r.get("name", "").lower() for r in rows
        }
        for name in personas:
            if name not in available and name.lower() not in available:
                # Fuzzy: check if any agent_id ends with -<name>
                exists = any(
                    str(r.get("_id", "")).endswith(f"-{name}") for r in rows
                )
                if not exists:
                    errors.append(f"Agent '@{name}' not found in agent library")

    return AutomationValidation(
        is_valid=parsed["is_valid"] and not errors,
        personas_detected=personas,
        execution_mode=ExecutionMode(parsed["execution_mode"]),
        warnings=parsed["warnings"],
        errors=errors,
        suggestions=parsed["suggestions"],
        estimated_duration_seconds=max(15, len(personas) * 10) if personas else None,
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=AutomationListResponse)
async def list_automations(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    repo: AutomationRepository = Depends(_auto_repo),
) -> AutomationListResponse:
    rows = await repo.list_all(
        status=status_filter,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    total = await repo.count({"status": status_filter} if status_filter else None)
    return AutomationListResponse(
        success=True,
        automations=[_to_automation_response(r) for r in rows],
        total_count=total,
        page=page,
        page_size=page_size,
        last_updated=datetime.utcnow().isoformat(),
    )


@router.post("", response_model=AutomationResponse, status_code=201)
async def create_automation(
    payload: AutomationCreate,
    repo: AutomationRepository = Depends(_auto_repo),
    db=Depends(get_database),
) -> AutomationResponse:
    parsed = prompt_parser.parse(payload.prompt_template)
    row = await repo.create(
        name=payload.name,
        description=payload.description,
        prompt_template=payload.prompt_template,
        trigger_type=payload.trigger_type.value,
        trigger_config=payload.trigger_config,
        status=payload.status.value,
        execution_mode=parsed["execution_mode"],
        personas_detected=parsed["personas"],
        output_actions=[a.model_dump() for a in (payload.output_actions or [])],
        model_id=payload.model_id,
    )
    return _to_automation_response(row)


@router.get("/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    automation_id: str, repo: AutomationRepository = Depends(_auto_repo)
) -> AutomationResponse:
    row = await repo.get_by_id(automation_id)
    if not row:
        raise HTTPException(404, f"Automation '{automation_id}' not found")
    return _to_automation_response(row)


@router.put("/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    automation_id: str,
    payload: AutomationUpdate,
    repo: AutomationRepository = Depends(_auto_repo),
) -> AutomationResponse:
    row = await repo.get_by_id(automation_id)
    if not row:
        raise HTTPException(404, f"Automation '{automation_id}' not found")

    update = payload.model_dump(exclude_none=True)
    if not update:
        raise HTTPException(400, "Nothing to update")

    # Re-parse if the prompt changed.
    if "prompt_template" in update:
        parsed = prompt_parser.parse(update["prompt_template"])
        update["personas_detected"] = parsed["personas"]
        update["execution_mode"] = parsed["execution_mode"]

    # Coerce nested OutputAction objects to dicts.
    if "output_actions" in update and update["output_actions"] is not None:
        update["output_actions"] = [
            a.model_dump() if hasattr(a, "model_dump") else a
            for a in update["output_actions"]
        ]
    # Coerce enum-typed fields.
    for field in ("trigger_type", "status"):
        if field in update and hasattr(update[field], "value"):
            update[field] = update[field].value

    updated = await repo.update(automation_id, update)
    if not updated:
        raise HTTPException(404, f"Automation '{automation_id}' not found")
    return _to_automation_response(updated)


@router.delete("/{automation_id}")
async def delete_automation(
    automation_id: str, repo: AutomationRepository = Depends(_auto_repo)
) -> Dict[str, Any]:
    if not await repo.delete(automation_id):
        raise HTTPException(404, f"Automation '{automation_id}' not found")
    return {"deleted": True, "automation_id": automation_id}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@router.post("/validate", response_model=AutomationValidation)
async def validate_prompt(
    payload: ValidationRequest, db=Depends(get_database)
) -> AutomationValidation:
    return await _validate_prompt(payload.prompt_template, db)


@router.post("/{automation_id}/validate", response_model=AutomationValidation)
async def validate_existing(
    automation_id: str,
    repo: AutomationRepository = Depends(_auto_repo),
    db=Depends(get_database),
) -> AutomationValidation:
    row = await repo.get_by_id(automation_id)
    if not row:
        raise HTTPException(404, f"Automation '{automation_id}' not found")
    return await _validate_prompt(row["prompt_template"], db)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

@router.post("/{automation_id}/run", response_model=AutomationExecutionResponse)
async def run_automation(
    automation_id: str,
    payload: Optional[AutomationExecutionRequest] = Body(default=None),
    repo: AutomationRepository = Depends(_auto_repo),
) -> AutomationExecutionResponse:
    if not await repo.get_by_id(automation_id):
        raise HTTPException(404, f"Automation '{automation_id}' not found")
    parameters = (payload.parameters if payload else None) or {}
    if payload and payload.dry_run:
        # Dry-run = validation only; do not actually execute.
        # (We still report it as a successful no-op so the UI can show "OK".)
        return AutomationExecutionResponse(
            execution_id="dry-run-" + uuid.uuid4().hex[:8],
            automation_id=automation_id,
            status="success",
            started_at=datetime.utcnow().isoformat(),
            completed_at=datetime.utcnow().isoformat(),
            duration_ms=0,
            steps=[],
            final_result="Dry run — automation not executed.",
            total_steps=0,
            successful_steps=0,
            failed_steps=0,
        )
    return await automation_engine.execute_automation(automation_id, parameters)


@router.get(
    "/{automation_id}/executions", response_model=ExecutionHistoryResponse
)
async def list_automation_executions(
    automation_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    repo: AutomationExecutionRepository = Depends(_exec_repo),
) -> ExecutionHistoryResponse:
    rows = await repo.list_for_automation(
        automation_id=automation_id, limit=page_size
    )
    return ExecutionHistoryResponse(
        executions=[_to_execution_response(r) for r in rows],
        total_count=await repo.count({"automation_id": automation_id}),
        page=page,
        page_size=page_size,
        last_updated=datetime.utcnow().isoformat(),
    )


@router.get("/executions/recent", response_model=ExecutionHistoryResponse)
async def list_recent_executions(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    repo: AutomationExecutionRepository = Depends(_exec_repo),
) -> ExecutionHistoryResponse:
    rows = await repo.list_recent(
        status=status_filter,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return ExecutionHistoryResponse(
        executions=[_to_execution_response(r) for r in rows],
        total_count=await repo.count(
            {"status": status_filter} if status_filter else None
        ),
        page=page,
        page_size=page_size,
        last_updated=datetime.utcnow().isoformat(),
    )


@router.get(
    "/executions/{execution_id}", response_model=AutomationExecutionResponse
)
async def get_execution(
    execution_id: str, repo: AutomationExecutionRepository = Depends(_exec_repo)
) -> AutomationExecutionResponse:
    row = await repo.get_by_id(execution_id)
    if not row:
        raise HTTPException(404, f"Execution '{execution_id}' not found")
    return _to_execution_response(row)


@router.get("/executions/{execution_id}/stream")
async def stream_execution(
    execution_id: str, repo: AutomationExecutionRepository = Depends(_exec_repo)
) -> StreamingResponse:
    """SSE stream that polls the execution row and emits when it changes.

    The engine writes step traces back to the DB as they finish, so we can
    mirror progress to the UI just by tailing the row.
    """

    async def gen():
        last_serialized: Optional[str] = None
        # 30-minute cap @ 0.4s tick.
        for _ in range(4500):
            row = await repo.get_by_id(execution_id)
            if not row:
                yield (
                    "event: error\n"
                    f"data: {json.dumps({'error': 'not_found'})}\n\n"
                )
                return
            payload = json.dumps(
                {
                    "execution_id": row["execution_id"],
                    "automation_id": row["automation_id"],
                    "status": row.get("status"),
                    "total_steps": row.get("total_steps") or 0,
                    "successful_steps": row.get("successful_steps") or 0,
                    "failed_steps": row.get("failed_steps") or 0,
                    "steps": row.get("steps") or [],
                    "result": row.get("result"),
                    "error": row.get("error"),
                    "duration_ms": row.get("duration_ms"),
                    "completed_at": row.get("completed_at"),
                }
            )
            if payload != last_serialized:
                yield f"data: {payload}\n\n"
                last_serialized = payload
            if row.get("status") in ("success", "failed", "partial"):
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Promote to Crew
# ---------------------------------------------------------------------------

@router.post("/{automation_id}/promote-to-crew")
async def promote_to_crew(
    automation_id: str,
    payload: Optional[PromoteToCrewRequest] = Body(default=None),
    repo: AutomationRepository = Depends(_auto_repo),
    db=Depends(get_database),
) -> Dict[str, Any]:
    """Bridge: turn an automation into a scheduled Crew.

    Maps each detected @agent to a CrewAgentConfig, output actions of type
    ``distribute`` to outbound ``connection_bindings``, and schedules a
    one-shot trigger when the automation's trigger is ``scheduled``.
    """
    automation = await repo.get_by_id(automation_id)
    if not automation:
        raise HTTPException(404, f"Automation '{automation_id}' not found")

    from repositories.crew_repository import CrewRepository

    crew_repo = CrewRepository(db)

    personas: List[str] = automation.get("personas_detected") or []
    if not personas:
        raise HTTPException(
            400,
            "Cannot promote: this automation has no @agent mentions to map onto crew agents.",
        )

    # Resolve each persona to a workspace_agents row so we can copy the system_prompt.
    agents_coll = db["workspace_agents"]
    crew_agents: List[Dict[str, Any]] = []
    for idx, name in enumerate(personas):
        row = await agents_coll.find_one({"slug": name}) or await agents_coll.find_one(
            {"name": {"$regex": f"^{name}$", "$options": "i"}}
        )
        crew_agents.append(
            {
                "agent_id": str(uuid.uuid4()),
                "role": "custom",
                "custom_role": name,
                "name": (row.get("name") if row else name) or name,
                "instructions": (row.get("system_prompt") if row else "")
                or automation["prompt_template"],
                "library_agent_id": (row or {}).get("agent_id"),
                "model_id": automation.get("model_id"),
                "tools": [],
                "order": idx,
                "depends_on": [],
                "knowledge_base_ids": [],
            }
        )

    # Outbound connection bindings come from any DISTRIBUTE output actions.
    connection_bindings: List[Dict[str, Any]] = []
    for action in automation.get("output_actions") or []:
        if action.get("type") == "distribute":
            cid = (action.get("config") or {}).get("connection_id")
            platform = (action.get("config") or {}).get("platform") or "blog"
            if cid:
                connection_bindings.append(
                    {
                        "connection_id": cid,
                        "platform": platform,
                        "direction": "outbound",
                    }
                )

    # Carry over a scheduled trigger if the automation had one configured.
    triggers: List[Dict[str, Any]] = []
    if (
        automation.get("trigger_type") == "scheduled"
        and automation.get("trigger_config")
    ):
        cron = (automation["trigger_config"] or {}).get("cron")
        run_at = (automation["trigger_config"] or {}).get("run_at")
        if cron or run_at:
            triggers.append(
                {
                    "type": "scheduled",
                    "connection_ids": [b["connection_id"] for b in connection_bindings],
                    "cron": cron,
                    "run_at": run_at,
                }
            )

    name = (payload.name if payload else None) or f"{automation['name']} (Crew)"
    description = (
        f"Promoted from automation: {automation['name']}\n\n"
        f"{automation.get('description') or ''}".strip()
    )

    crew_doc = await crew_repo.create_crew(
        user_id="desktop",
        data={
            "name": name,
            "description": description,
            "agents": crew_agents,
            "execution_config": {
                "mode": "sequential",
                "max_iterations": 1,
                "timeout_seconds": 600,
                "retry_on_failure": False,
                "max_retries": 0,
                "checkpoint_enabled": False,
                "max_agent_invocations": 10,
                "budget_limit_usd": 1.0,
            },
            "channel_bindings": [],
            "distribution_channels": [],
            "connection_bindings": connection_bindings,
            "triggers": triggers,
            "approval_required": False,
            "memory_enabled": True,
            "tags": ["promoted-from-automation"],
            "knowledge_base_ids": [],
        },
    )

    return {
        "promoted": True,
        "automation_id": automation_id,
        "crew_id": crew_doc["crew_id"],
        "crew": crew_doc,
    }
