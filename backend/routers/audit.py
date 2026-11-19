"""
Audit Trail & ABOM Compliance Export Router.

Exposes local SQLite audit log querying, AI Bill of Materials (ABOM) posture
snapshots, and downloadable JSON / RFC-4180 CSV compliance exports.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from models.audit_models import AuditAction, AuditListResponse
from repositories.audit_repository import AuditRepository
from services.audit_service import (
    audit_log,
    export_audit_csv,
    export_audit_json,
    generate_abom,
)

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _clean_opt(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    stripped = val.strip()
    return stripped or None


def _validate_iso_date(val: Optional[str], field_name: str) -> Optional[str]:
    cleaned = _clean_opt(val)
    if cleaned is None:
        return None
    try:
        candidate = cleaned[:-1] + "+00:00" if cleaned.endswith("Z") else cleaned
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ISO date/datetime for '{field_name}': {cleaned}",
        ) from exc
    return cleaned


@router.get("/events", response_model=AuditListResponse)
async def list_audit_events(
    action: Optional[str] = Query(None, description="Exact action or prefix ending in '.*'"),
    severity: Optional[str] = Query(None, description="Filter by severity (info, warning, error, critical)"),
    resource_type: Optional[str] = Query(None, description="Filter by resource_type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource_id"),
    user_id: Optional[str] = Query(None, description="Filter by user_id"),
    from_date: Optional[str] = Query(None, description="Inclusive start date/timestamp (ISO-8601)"),
    to_date: Optional[str] = Query(None, description="Inclusive end date/timestamp (ISO-8601)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    """Query paginated local SQLite audit trail events with filters."""
    valid_from = _validate_iso_date(from_date, "from_date")
    valid_to = _validate_iso_date(to_date, "to_date")

    repo = AuditRepository()
    events, total = await repo.query(
        user_id=_clean_opt(user_id),
        action=_clean_opt(action),
        severity=_clean_opt(severity),
        resource_type=_clean_opt(resource_type),
        resource_id=_clean_opt(resource_id),
        from_date=valid_from,
        to_date=valid_to,
        page=page,
        page_size=page_size,
    )
    return AuditListResponse(
        events=events,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/abom")
async def get_abom_report():
    """Return the live AI Bill of Materials (ABOM) compliance report."""
    return await asyncio.to_thread(generate_abom)


@router.get("/export")
async def export_audit_bundle(
    format: str = Query("json", description="Export format: 'json' or 'csv'"),
    limit: int = Query(5000, ge=1, le=50000),
):
    """Export the compliance bundle as downloadable JSON (ABOM + events) or CSV."""
    fmt = (format or "json").strip().lower()
    if fmt not in ("json", "csv"):
        raise HTTPException(
            status_code=400,
            detail="Invalid export format. Supported formats: 'json', 'csv'.",
        )

    await audit_log(
        AuditAction.AUDIT_EXPORTED,
        resource_type="audit_export",
        resource_id=fmt,
        details={"format": fmt, "limit": limit},
    )

    if fmt == "csv":
        content = await asyncio.to_thread(export_audit_csv, None, limit)
        media_type = "text/csv; charset=utf-8"
    else:
        content = await asyncio.to_thread(export_audit_json, None, limit)
        media_type = "application/json"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="vesper-audit-abom.{fmt}"'
        },
    )
