"""
Distribution Channel Registry Router — Publish content to external platforms.

Endpoints:
  GET    /api/v1/distribution/types             — List available channel types
  POST   /api/v1/distribution/channels          — Register a channel
  GET    /api/v1/distribution/channels          — List channels
  GET    /api/v1/distribution/channels/{id}     — Get channel details
  PATCH  /api/v1/distribution/channels/{id}     — Update channel
  DELETE /api/v1/distribution/channels/{id}     — Delete channel
  PATCH  /api/v1/distribution/channels/{id}/toggle — Enable/disable
  POST   /api/v1/distribution/publish           — Publish to one channel
  POST   /api/v1/distribution/publish/multi     — Publish to multiple channels
  GET    /api/v1/distribution/deliveries        — Delivery history
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from services.auth_service import get_current_user, require_admin
from services.distribution_service import DistributionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/distribution", tags=["distribution"])


# ------------------------------------------------------------------
# Request Models
# ------------------------------------------------------------------

class CreateChannelRequest(BaseModel):
    channel_type: str = Field(..., pattern="^(linkedin|twitter|blog|email|slack)$")
    name: str = Field(..., min_length=1, max_length=100)
    config: dict = Field(default_factory=dict)


class UpdateChannelRequest(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None


class ToggleRequest(BaseModel):
    enabled: bool


class PublishRequest(BaseModel):
    channel_id: str
    content: str = Field(..., min_length=1)
    title: Optional[str] = None
    metadata: Optional[dict] = None


class MultiPublishRequest(BaseModel):
    channel_ids: List[str] = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    title: Optional[str] = None
    metadata: Optional[dict] = None


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------

async def get_distribution_service(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> DistributionService:
    return DistributionService(db)


def _get_user_id(user: dict) -> str:
    return user.get("user_id") or user.get("sub")


# ------------------------------------------------------------------
# Channel Types
# ------------------------------------------------------------------

@router.get("/types")
async def list_channel_types(
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """List available distribution channel types with constraints."""
    types = await svc.get_channel_types()
    return {"status": "success", "data": {"types": types, "count": len(types)}}


# ------------------------------------------------------------------
# Channel CRUD
# ------------------------------------------------------------------

@router.post("/channels", dependencies=[Depends(require_admin)])
async def create_channel(
    request: CreateChannelRequest,
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """Register a new distribution channel."""
    user_id = _get_user_id(user)
    org = user.get("organization")
    channel = await svc.create_channel(
        channel_type=request.channel_type,
        name=request.name,
        config=request.config,
        organization=org,
        created_by=user_id,
    )
    return {"status": "success", "data": channel}


@router.get("/channels")
async def list_channels(
    channel_type: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """List distribution channels (credentials masked)."""
    org = user.get("organization")
    channels = await svc.list_channels(org, channel_type)
    return {"status": "success", "data": {"channels": channels, "count": len(channels)}}


@router.get("/channels/{channel_id}")
async def get_channel(
    channel_id: str,
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """Get a specific distribution channel."""
    channel = await svc.get_channel(channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    # Mask credentials in response
    if "config" in channel:
        channel["config"] = svc._mask_credentials(channel["config"])
    return {"status": "success", "data": channel}


@router.patch("/channels/{channel_id}", dependencies=[Depends(require_admin)])
async def update_channel(
    channel_id: str,
    request: UpdateChannelRequest,
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """Update a distribution channel."""
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    channel = await svc.update_channel(channel_id, updates)
    if not channel:
        raise HTTPException(404, "Channel not found")
    return {"status": "success", "data": channel}


@router.delete("/channels/{channel_id}", dependencies=[Depends(require_admin)])
async def delete_channel(
    channel_id: str,
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """Delete a distribution channel."""
    deleted = await svc.delete_channel(channel_id)
    if not deleted:
        raise HTTPException(404, "Channel not found")
    return {"status": "success", "message": "Channel deleted"}


@router.patch("/channels/{channel_id}/toggle", dependencies=[Depends(require_admin)])
async def toggle_channel(
    channel_id: str,
    request: ToggleRequest,
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """Enable or disable a distribution channel."""
    channel = await svc.toggle_channel(channel_id, request.enabled)
    if not channel:
        raise HTTPException(404, "Channel not found")
    return {"status": "success", "data": channel}


# ------------------------------------------------------------------
# Publishing
# ------------------------------------------------------------------

@router.post("/publish")
async def publish_content(
    request: PublishRequest,
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """Publish content to a single distribution channel."""
    user_id = _get_user_id(user)
    result = await svc.publish(
        channel_id=request.channel_id,
        content=request.content,
        title=request.title,
        metadata=request.metadata,
        published_by=user_id,
    )
    return {"status": "success", "data": result}


@router.post("/publish/multi")
async def publish_multi(
    request: MultiPublishRequest,
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """Publish content to multiple distribution channels."""
    user_id = _get_user_id(user)
    result = await svc.publish_to_multiple(
        channel_ids=request.channel_ids,
        content=request.content,
        title=request.title,
        metadata=request.metadata,
        published_by=user_id,
    )
    return {"status": "success", "data": result}


# ------------------------------------------------------------------
# Delivery History
# ------------------------------------------------------------------

@router.get("/deliveries")
async def list_deliveries(
    channel_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    svc: DistributionService = Depends(get_distribution_service),
):
    """Get content delivery history."""
    deliveries = await svc.get_deliveries(channel_id, limit)
    return {"status": "success", "data": {"deliveries": deliveries, "count": len(deliveries)}}
