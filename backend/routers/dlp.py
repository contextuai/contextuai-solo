"""
DLP (Data Loss Prevention) Router (Issue #77).

Exposes endpoints to inspect and update local DLP policy settings, manage
custom regex rules, and dry-run scan text before sending to cloud models.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.dlp_service import (
    get_dlp_settings,
    scan_and_redact,
    update_dlp_settings,
)

router = APIRouter(prefix="/api/v1/dlp", tags=["dlp"])


class CustomDlpRulePayload(BaseModel):
    id: Optional[str] = None
    name: str
    pattern: str
    placeholder: Optional[str] = "[REDACTED:CUSTOM]"
    enabled: bool = True


class DlpSettingsUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    redact_logs: Optional[bool] = None
    categories: Optional[Dict[str, bool]] = None
    custom_rules: Optional[List[CustomDlpRulePayload]] = None
    custom: Optional[List[CustomDlpRulePayload]] = None


class DlpTestRequest(BaseModel):
    text: str
    policy: Optional[Dict[str, Any]] = None


@router.get("/settings")
async def read_dlp_settings():
    """Return the effective local DLP policy settings."""
    return get_dlp_settings()


@router.put("/settings")
async def write_dlp_settings(payload: DlpSettingsUpdateRequest):
    """Update and persist local DLP policy settings."""
    patch = payload.model_dump(exclude_none=True)
    try:
        updated = update_dlp_settings(patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Fire-and-forget audit event (safe both before and after audit_service migration)
    try:
        from models.audit_models import AuditAction
        from services import audit_service

        action = getattr(AuditAction, "DLP_POLICY_UPDATED", "dlp.policy.updated")
        sync_fn = getattr(audit_service, "audit_log_sync", None)
        if callable(sync_fn):
            sync_fn(
                action,
                resource_type="dlp_policy",
                resource_id="default",
                details={
                    "enabled": updated.get("enabled"),
                    "redact_logs": updated.get("redact_logs"),
                    "categories": updated.get("categories"),
                    "custom_rule_count": len(updated.get("custom_rules") or []),
                },
            )
    except Exception:
        pass

    return updated


@router.post("/test")
async def dry_run_dlp_test(payload: DlpTestRequest):
    """Dry-run DLP scanning on sample text without persisting or sending egress."""
    try:
        result = scan_and_redact(payload.text, policy=payload.policy)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.to_dict()
