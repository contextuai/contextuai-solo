"""
Approval Queue Router — Human-in-the-loop review endpoints.

Endpoints:
  GET    /api/v1/approvals              — List approvals (pending by default)
  GET    /api/v1/approvals/count        — Count pending approvals
  GET    /api/v1/approvals/{id}         — Get approval details
  POST   /api/v1/approvals/{id}/approve — Approve (and optionally edit)
  POST   /api/v1/approvals/{id}/reject  — Reject a draft
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from services.auth_service import get_current_user
from services.approval_service import ApprovalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


# ── Request Models ───────────────────────────────────────────────────

class ApproveRequest(BaseModel):
    edited_response: Optional[str] = None


# ── Dependencies ──────────────────────────────────────────────────────

def get_approval_service(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ApprovalService:
    return ApprovalService(db)


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/")
async def list_approvals(
    status: Optional[str] = "pending",
    limit: int = 50,
    svc: ApprovalService = Depends(get_approval_service),
    user: dict = Depends(get_current_user),
):
    """List approvals, filtered by status."""
    approvals = await svc.list_all(status=status, limit=limit)
    return {"approvals": approvals, "count": len(approvals)}


@router.get("/count")
async def count_pending(
    svc: ApprovalService = Depends(get_approval_service),
    user: dict = Depends(get_current_user),
):
    """Return count of pending approvals (for badge/notification)."""
    count = await svc.count_pending()
    return {"pending_count": count}


@router.get("/{approval_id}")
async def get_approval(
    approval_id: str,
    svc: ApprovalService = Depends(get_approval_service),
    user: dict = Depends(get_current_user),
):
    """Get a specific approval."""
    approval = await svc.get(approval_id)
    if not approval:
        raise HTTPException(404, "Approval not found")
    return {"approval": approval}


@router.post("/{approval_id}/approve")
async def approve(
    approval_id: str,
    request: ApproveRequest = ApproveRequest(),
    svc: ApprovalService = Depends(get_approval_service),
    user: dict = Depends(get_current_user),
):
    """Approve a pending response (optionally edit it first)."""
    try:
        approval = await svc.approve_and_send(
            approval_id,
            edited_response=request.edited_response,
            reviewed_by=user.get("user_id", "desktop-user"),
        )
        return {"approval": approval, "status": "sent"}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error("Approval send failed: %s", e)
        raise HTTPException(500, f"Failed to send: {e}")


@router.post("/{approval_id}/reject")
async def reject(
    approval_id: str,
    svc: ApprovalService = Depends(get_approval_service),
    user: dict = Depends(get_current_user),
):
    """Reject a pending response (discard)."""
    try:
        approval = await svc.reject_approval(
            approval_id,
            reviewed_by=user.get("user_id", "desktop-user"),
        )
        return {"approval": approval, "status": "rejected"}
    except ValueError as e:
        raise HTTPException(404, str(e))
