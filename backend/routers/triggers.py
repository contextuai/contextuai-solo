"""
Trigger Management Router — CRUD for channel-crew triggers.

Endpoints:
  GET    /api/v1/triggers                   — List all triggers
  POST   /api/v1/triggers                   — Create a trigger
  GET    /api/v1/triggers/{trigger_id}      — Get trigger details
  PUT    /api/v1/triggers/{trigger_id}      — Update a trigger
  DELETE /api/v1/triggers/{trigger_id}      — Delete a trigger
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from services.auth_service import get_current_user
from repositories.trigger_repository import TriggerRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/triggers", tags=["triggers"])


# ── Request Models ───────────────────────────────────────────────────

class CreateTriggerRequest(BaseModel):
    channel_type: str = Field(..., pattern="^(telegram|discord|whatsapp|teams|slack)$")
    channel_id: str = Field(default="*", description="Specific chat ID or * for all")
    crew_id: Optional[str] = None
    agent_id: Optional[str] = None
    enabled: bool = True
    approval_required: bool = False
    cooldown_seconds: int = Field(default=0, ge=0)


class UpdateTriggerRequest(BaseModel):
    crew_id: Optional[str] = None
    agent_id: Optional[str] = None
    enabled: Optional[bool] = None
    approval_required: Optional[bool] = None
    cooldown_seconds: Optional[int] = None


# ── Dependencies ──────────────────────────────────────────────────────

def get_trigger_repo(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> TriggerRepository:
    return TriggerRepository(db)


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/")
async def list_triggers(
    channel_type: Optional[str] = None,
    enabled_only: bool = False,
    repo: TriggerRepository = Depends(get_trigger_repo),
    user: dict = Depends(get_current_user),
):
    """List all trigger configurations."""
    triggers = await repo.list_all(channel_type=channel_type, enabled_only=enabled_only)
    return {"triggers": triggers, "count": len(triggers)}


@router.post("/")
async def create_trigger(
    request: CreateTriggerRequest,
    repo: TriggerRepository = Depends(get_trigger_repo),
    user: dict = Depends(get_current_user),
):
    """Create a new channel-crew trigger."""
    trigger = await repo.create(request.model_dump())
    return {"trigger": trigger}


@router.get("/{trigger_id}")
async def get_trigger(
    trigger_id: str,
    repo: TriggerRepository = Depends(get_trigger_repo),
    user: dict = Depends(get_current_user),
):
    """Get a specific trigger."""
    trigger = await repo.get_by_id(trigger_id)
    if not trigger:
        raise HTTPException(404, "Trigger not found")
    return {"trigger": trigger}


@router.put("/{trigger_id}")
async def update_trigger(
    trigger_id: str,
    request: UpdateTriggerRequest,
    repo: TriggerRepository = Depends(get_trigger_repo),
    user: dict = Depends(get_current_user),
):
    """Update a trigger configuration."""
    existing = await repo.get_by_id(trigger_id)
    if not existing:
        raise HTTPException(404, "Trigger not found")

    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if not updates:
        return {"trigger": existing}

    trigger = await repo.update(trigger_id, updates)
    return {"trigger": trigger}


@router.delete("/{trigger_id}")
async def delete_trigger(
    trigger_id: str,
    repo: TriggerRepository = Depends(get_trigger_repo),
    user: dict = Depends(get_current_user),
):
    """Delete a trigger."""
    deleted = await repo.delete(trigger_id)
    if not deleted:
        raise HTTPException(404, "Trigger not found")
    return {"status": "deleted", "trigger_id": trigger_id}
