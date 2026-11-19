"""
Glass-Box Privacy Shield Router (SPEC-28).

Exposes live outbound network egress ledger, Airplane Lock toggle, and
verifiable privacy manifest.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.net_guard import (
    clear_egress_ledger,
    get_egress_ledger,
    get_privacy_manifest,
    set_airplane_lock,
)

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])


class AirplaneLockRequest(BaseModel):
    enabled: bool


@router.get("/ledger")
async def read_privacy_ledger():
    """Return the live outbound network activity ledger and zero-egress status."""
    return get_egress_ledger()


@router.post("/airplane-lock")
async def update_airplane_lock(request: AirplaneLockRequest):
    """Toggle Airplane Lock to block or allow non-loopback network requests."""
    try:
        state = set_airplane_lock(request.enabled)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {
        **state,
        "ledger": get_egress_ledger(),
    }


@router.delete("/ledger")
async def reset_privacy_ledger():
    """Clear the in-memory egress ledger."""
    clear_egress_ledger()
    return get_egress_ledger()


@router.get("/manifest")
async def read_privacy_manifest():
    """Return the verifiable privacy manifest for this installation."""
    return get_privacy_manifest()
