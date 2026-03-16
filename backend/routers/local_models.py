"""
Local Models Router

REST API for the Model Hub: browse catalog, detect hardware, download/delete
GGUF models, and manage installed models.  Desktop-only (no auth needed).
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import get_database
from services.model_manager import model_manager
from services.local_model_seeder import sync_local_models_to_db
from services.model_catalog import (
    get_catalog,
    get_model,
    get_recommended,
    get_all_categories,
    LOCAL_MODEL_CATALOG,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/local-models", tags=["local-models"])


# ── Request / Response models ──────────────────────────────────────────────

class DownloadRequest(BaseModel):
    model_id: str


class CustomDownloadRequest(BaseModel):
    hf_repo: str
    hf_filename: str


class CancelRequest(BaseModel):
    model_id: str


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/system-info")
async def get_system_info():
    """Detect system RAM and GPU for model recommendations."""
    info = model_manager.get_system_info()
    return info


@router.get("/catalog")
async def get_model_catalog(
    category: Optional[str] = Query(None, description="Filter by category"),
    max_ram_gb: Optional[int] = Query(None, description="Max RAM budget in GB"),
):
    """
    Get the curated local model catalog.

    Optionally filter by category and/or RAM budget.  Returns models sorted
    by parameter count.  Each entry includes an ``installed`` flag.
    """
    models = get_catalog(max_ram_gb=max_ram_gb, category=category)

    # Enrich with installation status
    for m in models:
        m["installed"] = model_manager.is_installed(m["id"])

    system_info = model_manager.get_system_info()
    recommended = get_recommended(system_info["total_ram_gb"])
    # Mark recommended models
    rec_ids = {r["id"] for r in recommended}
    for m in models:
        m["is_recommended"] = m["id"] in rec_ids

    return {
        "models": models,
        "total": len(models),
        "system_ram_gb": system_info["total_ram_gb"],
        "max_recommended_params": system_info["max_recommended_params"],
        "categories": get_all_categories(),
    }


@router.get("/catalog/{model_id}")
async def get_catalog_model(model_id: str):
    """Get details for a single catalog model."""
    entry = get_model(model_id)
    if not entry:
        return {"error": f"Model '{model_id}' not found in catalog"}
    entry["installed"] = model_manager.is_installed(model_id)
    return entry


@router.get("/installed")
async def list_installed_models():
    """List all locally downloaded GGUF models."""
    models = model_manager.list_installed()
    disk = model_manager.get_disk_usage()
    return {
        "models": models,
        "count": len(models),
        "disk_usage": disk,
    }


@router.get("/recommended")
async def get_recommended_models(limit: int = Query(3, ge=1, le=10)):
    """Get top recommended models for this system's hardware."""
    system_info = model_manager.get_system_info()
    models = get_recommended(system_info["total_ram_gb"], limit=limit)
    for m in models:
        m["installed"] = model_manager.is_installed(m["id"])
    return {
        "models": models,
        "system_ram_gb": system_info["total_ram_gb"],
        "max_recommended_params": system_info["max_recommended_params"],
    }


@router.post("/download")
async def download_model(request: DownloadRequest):
    """
    Download a model from HuggingFace.

    Returns an SSE stream with progress updates.
    After download completes, auto-registers the model in the database
    so it appears in /api/v1/models/ for Chat, Workspace, and Crews.
    """
    async def event_stream():
        async for progress in model_manager.download_model(request.model_id):
            yield f"data: {json.dumps(progress)}\n\n"
            if progress.get("status") == "done":
                try:
                    db = await get_database()
                    await sync_local_models_to_db(db)
                except Exception as e:
                    logger.warning("Failed to sync model to DB after download: %s", e)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/download/custom")
async def download_custom_model(request: CustomDownloadRequest):
    """Download any GGUF model by HuggingFace repo + filename."""
    async def event_stream():
        async for progress in model_manager.download_custom(
            request.hf_repo, request.hf_filename
        ):
            yield f"data: {json.dumps(progress)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/download/cancel")
async def cancel_download(request: CancelRequest):
    """Cancel an in-progress download."""
    cancelled = model_manager.cancel_download(request.model_id)
    return {
        "status": "cancelled" if cancelled else "not_found",
        "model_id": request.model_id,
    }


@router.delete("/{model_id}")
async def delete_model(model_id: str):
    """Delete a downloaded model and remove it from the model registry."""
    result = model_manager.delete_model(model_id)
    if result.get("status") == "deleted":
        try:
            db = await get_database()
            await sync_local_models_to_db(db)
        except Exception as e:
            logger.warning("Failed to sync DB after model delete: %s", e)
    return result


@router.get("/disk-usage")
async def get_disk_usage():
    """Get disk space usage for downloaded models."""
    return model_manager.get_disk_usage()


@router.get("/loaded")
async def get_loaded_model():
    """Check which model is currently loaded in memory."""
    from services.local_model_service import local_model_service
    status = local_model_service.get_status()
    return status or {"loaded": False}
