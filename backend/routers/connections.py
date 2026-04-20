"""Unified Connections REST API (Phase 3 PR 2).

Surfaces all credential stores — OAuth (LinkedIn/IG/FB), Reddit, Twitter,
token-paste channels (Telegram/Discord), and outbound-only types (Blog,
Email, Slack webhook) — behind one endpoint.

  GET    /api/v1/connections                      — unified list
  GET    /api/v1/connections/{id}                 — single summary
  PATCH  /api/v1/connections/{id}/capabilities    — toggle inbound/outbound
  POST   /api/v1/connections/outbound             — create blog/email/slack_webhook
  PUT    /api/v1/connections/outbound/{id}        — update
  DELETE /api/v1/connections/outbound/{id}        — remove

Per-platform credential endpoints (reddit, twitter, oauth, channels) stay
unchanged — this router is a read-plus-capability-toggle layer on top.
"""

from fastapi import APIRouter, Depends, HTTPException

from database import get_database
from models.connection_models import (
    CapabilityUpdate,
    ConnectionListResponse,
    ConnectionSummary,
    OutboundConnectionCreate,
    OutboundConnectionUpdate,
)
from services.auth_service import get_current_user
from services.connection_service import ConnectionService

router = APIRouter(prefix="/api/v1/connections", tags=["connections"])


def _svc(db=Depends(get_database)) -> ConnectionService:
    return ConnectionService(db)


def _user_id(user: dict) -> str:
    return user.get("user_id") or user.get("sub") or "desktop"


# ---------------------------------------------------------------------------
# List + single read
# ---------------------------------------------------------------------------

@router.get("", response_model=ConnectionListResponse)
async def list_connections(svc: ConnectionService = Depends(_svc)):
    rows = await svc.list_connections()
    return ConnectionListResponse(connections=rows, total_count=len(rows))


@router.get("/{connection_id}", response_model=ConnectionSummary)
async def get_connection(
    connection_id: str,
    svc: ConnectionService = Depends(_svc),
):
    row = await svc.get_connection(connection_id)
    if not row:
        raise HTTPException(404, f"Connection {connection_id} not found")
    return row


# ---------------------------------------------------------------------------
# PATCH capabilities
# ---------------------------------------------------------------------------

@router.patch("/{connection_id}/capabilities", response_model=ConnectionSummary)
async def patch_capabilities(
    connection_id: str,
    update: CapabilityUpdate,
    svc: ConnectionService = Depends(_svc),
):
    return await svc.update_capabilities(connection_id, update)


# ---------------------------------------------------------------------------
# Outbound-only CRUD (blog / email / slack_webhook)
# ---------------------------------------------------------------------------

@router.post("/outbound", response_model=ConnectionSummary, status_code=201)
async def create_outbound(
    request: OutboundConnectionCreate,
    svc: ConnectionService = Depends(_svc),
    user: dict = Depends(get_current_user),
):
    return await svc.create_outbound(request, _user_id(user))


@router.put("/outbound/{connection_id}", response_model=ConnectionSummary)
async def update_outbound(
    connection_id: str,
    update: OutboundConnectionUpdate,
    svc: ConnectionService = Depends(_svc),
):
    return await svc.update_outbound(connection_id, update)


@router.delete("/outbound/{connection_id}", status_code=204)
async def delete_outbound(
    connection_id: str,
    svc: ConnectionService = Depends(_svc),
):
    await svc.delete_outbound(connection_id)
