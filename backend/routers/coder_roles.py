"""Coder Agent Roles + Workflow config API (PR 14).

Endpoints
---------
Roles CRUD:
  GET    /api/v1/coder/projects/{project_id}/roles
  POST   /api/v1/coder/projects/{project_id}/roles
  PUT    /api/v1/coder/projects/{project_id}/roles/{role_id}
  DELETE /api/v1/coder/projects/{project_id}/roles/{role_id}
  POST   /api/v1/coder/projects/{project_id}/roles/apply-preset
  PUT    /api/v1/coder/projects/{project_id}/roles/reorder

Workflow:
  GET    /api/v1/coder/projects/{project_id}/workflow
  PUT    /api/v1/coder/projects/{project_id}/workflow

Preset discovery:
  GET    /api/v1/coder/role-presets
  GET    /api/v1/coder/role-presets/{preset_id}
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from database import get_database
from models.coder_models import (
    ApplyPresetRequest,
    CoderAgentRoleCreate,
    CoderAgentRoleResponse,
    CoderAgentRoleUpdate,
    ReorderRolesRequest,
    RolePresetDetail,
    RolePresetSummary,
    WorkflowModeResponse,
    WorkflowModeUpdate,
)
from repositories.coder_agent_role_repository import CoderAgentRoleRepository
from repositories.coder_project_repository import CoderProjectRepository
from services.coder_role_preset_service import CoderRolePresetService

router = APIRouter(prefix="/api/v1/coder", tags=["coder-roles"])

# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _role_repo(db=Depends(get_database)) -> CoderAgentRoleRepository:
    return CoderAgentRoleRepository(db)


def _project_repo(db=Depends(get_database)) -> CoderProjectRepository:
    return CoderProjectRepository(db)


def _preset_service() -> CoderRolePresetService:
    return CoderRolePresetService()


# ---------------------------------------------------------------------------
# Shared guard
# ---------------------------------------------------------------------------

async def _require_project(
    project_id: str,
    repo: CoderProjectRepository,
) -> Dict[str, Any]:
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(404, f"Project '{project_id}' not found")
    return project


# ---------------------------------------------------------------------------
# Role list / create
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/roles",
    response_model=List[CoderAgentRoleResponse],
)
async def list_roles(
    project_id: str,
    role_repo: CoderAgentRoleRepository = Depends(_role_repo),
    project_repo: CoderProjectRepository = Depends(_project_repo),
) -> List[CoderAgentRoleResponse]:
    await _require_project(project_id, project_repo)
    rows = await role_repo.list_for_project(project_id)
    return [_to_response(r) for r in rows]


@router.post(
    "/projects/{project_id}/roles",
    response_model=CoderAgentRoleResponse,
    status_code=201,
)
async def create_role(
    project_id: str,
    payload: CoderAgentRoleCreate,
    role_repo: CoderAgentRoleRepository = Depends(_role_repo),
    project_repo: CoderProjectRepository = Depends(_project_repo),
) -> CoderAgentRoleResponse:
    await _require_project(project_id, project_repo)

    # Auto-assign order if omitted.
    order = payload.order
    if order is None:
        order = (await role_repo.max_order_for_project(project_id)) + 1

    now = datetime.utcnow().isoformat()
    row = await role_repo.create(
        {
            "role_id": str(uuid.uuid4()),
            "project_id": project_id,
            "role_kind": payload.role_kind.value,
            "display_name": payload.display_name,
            "system_prompt": payload.system_prompt,
            "model_id": payload.model_id,
            "temperature": payload.temperature,
            "max_tokens": payload.max_tokens,
            "enabled": payload.enabled,
            "order": order,
            "created_at": now,
            "updated_at": now,
        }
    )
    return _to_response(row)


# ---------------------------------------------------------------------------
# Apply preset — registered BEFORE /{role_id} to avoid route shadowing
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/roles/apply-preset",
    response_model=List[CoderAgentRoleResponse],
)
async def apply_preset(
    project_id: str,
    payload: ApplyPresetRequest,
    role_repo: CoderAgentRoleRepository = Depends(_role_repo),
    project_repo: CoderProjectRepository = Depends(_project_repo),
    preset_svc: CoderRolePresetService = Depends(_preset_service),
) -> List[CoderAgentRoleResponse]:
    await _require_project(project_id, project_repo)
    try:
        rows = await preset_svc.apply_preset(project_id, payload.preset_id, role_repo)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return [_to_response(r) for r in rows]


# ---------------------------------------------------------------------------
# Reorder — registered BEFORE /{role_id} to avoid route shadowing
# ---------------------------------------------------------------------------

@router.put(
    "/projects/{project_id}/roles/reorder",
    response_model=List[CoderAgentRoleResponse],
)
async def reorder_roles(
    project_id: str,
    payload: ReorderRolesRequest,
    role_repo: CoderAgentRoleRepository = Depends(_role_repo),
    project_repo: CoderProjectRepository = Depends(_project_repo),
) -> List[CoderAgentRoleResponse]:
    await _require_project(project_id, project_repo)

    existing = await role_repo.list_for_project(project_id)
    existing_ids = {r["role_id"] for r in existing}

    if set(payload.role_ids) != existing_ids:
        raise HTTPException(
            400,
            "role_ids must contain exactly the same role IDs as the project "
            f"(got {len(payload.role_ids)}, expected {len(existing_ids)})",
        )

    updated = []
    for order, role_id in enumerate(payload.role_ids):
        row = await role_repo.update(role_id, {"order": order})
        if row:
            updated.append(row)

    # Return sorted by the new order.
    updated.sort(key=lambda r: r.get("order", 0))
    return [_to_response(r) for r in updated]


# ---------------------------------------------------------------------------
# Role update / delete — parameterized routes registered AFTER fixed-path ones
# ---------------------------------------------------------------------------

@router.put(
    "/projects/{project_id}/roles/{role_id}",
    response_model=CoderAgentRoleResponse,
)
async def update_role(
    project_id: str,
    role_id: str,
    payload: CoderAgentRoleUpdate,
    role_repo: CoderAgentRoleRepository = Depends(_role_repo),
    project_repo: CoderProjectRepository = Depends(_project_repo),
) -> CoderAgentRoleResponse:
    await _require_project(project_id, project_repo)
    partial = payload.model_dump(exclude_none=True)
    if not partial:
        raise HTTPException(400, "Nothing to update")
    row = await role_repo.update(role_id, partial)
    if not row:
        raise HTTPException(404, f"Role '{role_id}' not found")
    return _to_response(row)


@router.delete("/projects/{project_id}/roles/{role_id}")
async def delete_role(
    project_id: str,
    role_id: str,
    role_repo: CoderAgentRoleRepository = Depends(_role_repo),
    project_repo: CoderProjectRepository = Depends(_project_repo),
) -> Dict[str, Any]:
    await _require_project(project_id, project_repo)
    deleted = await role_repo.delete(role_id)
    if not deleted:
        raise HTTPException(404, f"Role '{role_id}' not found")
    return {"deleted": True, "role_id": role_id}


# ---------------------------------------------------------------------------
# Workflow mode
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{project_id}/workflow",
    response_model=WorkflowModeResponse,
)
async def get_workflow_mode(
    project_id: str,
    project_repo: CoderProjectRepository = Depends(_project_repo),
) -> WorkflowModeResponse:
    project = await _require_project(project_id, project_repo)
    return WorkflowModeResponse(
        project_id=project_id,
        workflow_mode=project.get("workflow_mode", "solo"),
    )


@router.put(
    "/projects/{project_id}/workflow",
    response_model=WorkflowModeResponse,
)
async def update_workflow_mode(
    project_id: str,
    payload: WorkflowModeUpdate,
    project_repo: CoderProjectRepository = Depends(_project_repo),
) -> WorkflowModeResponse:
    await _require_project(project_id, project_repo)
    updated = await project_repo.update(project_id, {"workflow_mode": payload.workflow_mode})
    if not updated:
        raise HTTPException(404, f"Project '{project_id}' not found")
    return WorkflowModeResponse(
        project_id=project_id,
        workflow_mode=updated.get("workflow_mode", "solo"),
    )


# ---------------------------------------------------------------------------
# Preset discovery
# ---------------------------------------------------------------------------

@router.get("/role-presets", response_model=List[RolePresetSummary])
async def list_role_presets(
    preset_svc: CoderRolePresetService = Depends(_preset_service),
) -> List[RolePresetSummary]:
    return preset_svc.list_presets()


@router.get("/role-presets/{preset_id}", response_model=RolePresetDetail)
async def get_role_preset(
    preset_id: str,
    preset_svc: CoderRolePresetService = Depends(_preset_service),
) -> RolePresetDetail:
    detail = preset_svc.get_preset(preset_id)
    if detail is None:
        raise HTTPException(404, f"Preset '{preset_id}' not found")
    return detail


# ---------------------------------------------------------------------------
# Internal serialisation helper
# ---------------------------------------------------------------------------

def _to_response(row: Dict[str, Any]) -> CoderAgentRoleResponse:
    from models.coder_models import RoleKind
    raw_kind = row.get("role_kind", "custom")
    try:
        kind = RoleKind(raw_kind)
    except ValueError:
        kind = RoleKind.CUSTOM

    return CoderAgentRoleResponse(
        role_id=row.get("role_id") or "",
        project_id=row.get("project_id") or "",
        role_kind=kind,
        display_name=row.get("display_name") or "",
        system_prompt=row.get("system_prompt") or "",
        model_id=row.get("model_id") or "",
        temperature=float(row.get("temperature", 0.7)),
        max_tokens=int(row.get("max_tokens", 4096)),
        enabled=bool(row.get("enabled", True)),
        order=int(row.get("order", 0)),
        created_at=row.get("created_at") or "",
        updated_at=row.get("updated_at") or "",
    )
