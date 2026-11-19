"""
Enterprise Policy & Catalog Governance Router (Issue #79).

Exposes:
- ``GET  /api/v1/enterprise/policy``
- ``PUT  /api/v1/enterprise/policy``
- ``POST /api/v1/enterprise/catalog/sync``
- ``POST /api/v1/enterprise/models/{model_id}/verify``
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.enterprise_policy import (
    ModelIntegrityError,
    get_enterprise_policy,
    resolve_expected_sha256,
    save_user_enterprise_settings,
    verify_gguf_sha256,
)
from services.hf_hub_discovery import refresh_ota_catalog
from services.model_catalog import get_model
from services.model_manager import model_manager
from services.net_guard import EgressBlockedError

router = APIRouter(prefix="/api/v1/enterprise", tags=["enterprise"])


class EnterprisePolicyUpdateRequest(BaseModel):
    catalog_url: Optional[str] = None
    catalog_exclusive: Optional[bool] = None
    require_sha256: Optional[bool] = None
    airplane_lock_enforced: Optional[bool] = None
    allowed_model_sha256: Optional[Any] = None


class CatalogSyncRequest(BaseModel):
    remote_url: Optional[str] = None
    cache_path: Optional[str] = None
    exclusive: Optional[bool] = None


class ModelVerifyRequest(BaseModel):
    expected_sha256: Optional[str] = None
    require_checksum: Optional[bool] = None


@router.get("/policy")
async def read_enterprise_policy():
    """Return the effective enterprise policy, locked fields, and source."""
    return get_enterprise_policy()


@router.put("/policy")
async def update_enterprise_policy(request: EnterprisePolicyUpdateRequest):
    """Persist unlocked user enterprise settings; returns 403 if locked by IT policy."""
    patch: Dict[str, Any] = request.model_dump(exclude_unset=True)
    try:
        updated = save_user_enterprise_settings(patch)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        from models.audit_models import AuditAction, AuditSeverity
        from services.audit_service import audit_log_sync
        audit_log_sync(
            getattr(AuditAction, "SETTINGS_CHANGED", "admin.settings.changed"),
            resource_type="enterprise_policy",
            resource_id="policy",
            details={"updated_fields": sorted(patch.keys())},
            severity=AuditSeverity.INFO,
        )
    except Exception:
        pass
    return updated


@router.post("/catalog/sync")
async def sync_enterprise_catalog(request: Optional[CatalogSyncRequest] = None):
    """Sync the curated model catalog from the configured enterprise or OTA source."""
    req = request or CatalogSyncRequest()
    try:
        return await refresh_ota_catalog(
            remote_url=req.remote_url,
            cache_path=req.cache_path,
            exclusive=req.exclusive,
        )
    except EgressBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/{model_id}/verify")
async def verify_installed_model(
    model_id: str,
    request: Optional[ModelVerifyRequest] = None,
):
    """Compute and verify the SHA-256 checksum of an installed GGUF model."""
    req = request or ModelVerifyRequest()
    lookup_id = model_id[len("local:"):] if model_id.startswith("local:") else model_id

    model_path = model_manager.get_model_path(lookup_id) or model_manager.get_model_path(model_id)
    if not model_path:
        for installed in model_manager.list_installed():
            if installed.get("id") in (model_id, lookup_id) or installed.get("filename") == model_id:
                model_path = installed.get("path")
                break

    if not model_path or not os.path.isfile(model_path):
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' is not installed locally.",
        )

    catalog_entry = get_model(lookup_id) or get_model(model_id)
    expected = req.expected_sha256 or resolve_expected_sha256(
        model_id=model_id,
        filename=os.path.basename(model_path),
        catalog_entry=catalog_entry,
    )

    try:
        result = verify_gguf_sha256(
            model_path,
            expected,
            require_checksum=req.require_checksum,
        )
    except ModelIntegrityError as exc:
        try:
            from models.audit_models import AuditAction, AuditSeverity
            from services.audit_service import audit_log_sync
            audit_log_sync(
                getattr(AuditAction, "MODEL_INTEGRITY_FAILED", "model.integrity_failed"),
                resource_type="model",
                resource_id=model_id,
                details={
                    "path": model_path,
                    "expected_sha256": expected,
                    "reason": str(exc),
                },
                severity=AuditSeverity.ERROR,
            )
        except Exception:
            pass
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "model_id": model_id,
        "path": model_path,
        **result,
    }
