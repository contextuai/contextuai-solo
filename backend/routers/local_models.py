"""
Local Models Router

REST API for the Model Hub: browse catalog, detect hardware, download/delete
GGUF models, import local GGUF files, search HuggingFace Hub, preload/benchmark
models, and manage installed models. Desktop-only (protected by sidecar token
middleware when configured).
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import get_database
from services.hardware import get_hardware_profile
from services.hf_hub_discovery import (
    list_hf_repo_gguf_files,
    refresh_ota_catalog,
    search_hf_gguf_models,
)
from services.local_model_seeder import sync_local_models_to_db
from services.model_catalog import (
    LOCAL_MODEL_CATALOG,
    get_all_categories,
    get_catalog,
    get_model,
    get_recommended,
)
from services.model_fit_engine import classify_model_fit, select_best_model_for_machine
from services.model_manager import model_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/local-models", tags=["local-models"])


# ── Request / Response models ──────────────────────────────────────────────

class DownloadRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str


class CustomDownloadRequest(BaseModel):
    hf_repo: str
    hf_filename: str


class CancelRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str


class ImportGGUFRequest(BaseModel):
    source_path: str
    copy_file: bool = False


class CatalogRefreshRequest(BaseModel):
    remote_url: Optional[str] = None
    cache_path: Optional[str] = None


class ServerConfigRequest(BaseModel):
    enabled: bool


_DEFAULT_V1_ENDPOINT_BASE = "http://127.0.0.1:18741/v1"


def _developer_settings_path() -> Path:
    override = (os.environ.get("VESPER_DEVELOPER_SETTINGS_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".contextuai-solo" / "data" / "developer_settings.json"


def is_local_server_enabled() -> bool:
    """Return whether the OpenAI-compatible /v1 local server is enabled (default True)."""
    path = _developer_settings_path()
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "local_server_enabled" in data:
                return bool(data["local_server_enabled"])
    except Exception as exc:
        logger.warning("Failed to read developer settings from %s: %s", path, exc)
    return True


def set_local_server_enabled(enabled: bool) -> bool:
    """Persist the local_server_enabled toggle to developer_settings.json."""
    path = _developer_settings_path()
    payload: dict = {}
    try:
        if path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload = existing
    except Exception:
        payload = {}
    payload["local_server_enabled"] = bool(enabled)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return bool(enabled)


async def _resolve_hf_token() -> Optional[str]:
    """Fetch stored HuggingFace token from CloudProviderService if configured (SPEC-08)."""
    try:
        from services.cloud_provider_service import CloudProviderService
        db = await get_database()
        if db is not None:
            creds = await CloudProviderService(db).get_credentials("huggingface")
            if creds and creds.get("api_key"):
                return str(creds["api_key"]).strip()
    except Exception:
        pass
    return None


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/system-info")
async def get_system_info():
    """Detect system RAM and GPU for model recommendations."""
    info = model_manager.get_system_info()
    return info


@router.get("/hardware")
async def get_hardware_xray(rescan: bool = Query(False, description="Force fresh hardware scan")):
    """Return full Hardware X-Ray profile (CPU, RAM, GPU, VRAM, backend, tier) (SPEC-27)."""
    return get_hardware_profile(rescan=rescan)


_FAMILY_DEFAULT_LOGOS = {
    "gemma": "https://cdn.simpleicons.org/googlegemini/4285F4",
    "codegemma": "https://cdn.simpleicons.org/googlegemini/4285F4",
    "llama": "https://cdn.simpleicons.org/meta/0467DF",
    "qwen": "https://cdn.simpleicons.org/alibabacloud/FF6A00",
    "deepseek": "https://cdn.simpleicons.org/deepseek/4D6BFE",
    "mistral": "https://cdn.simpleicons.org/mistralai/FA520F",
    "phi": "https://cdn.simpleicons.org/microsoft/00A4EF",
    "smollm": "https://cdn.simpleicons.org/huggingface/FFD21E",
}


@router.get("/catalog")
async def get_model_catalog(
    category: Optional[str] = Query(None, description="Filter by category"),
    max_ram_gb: Optional[int] = Query(None, description="Max RAM budget in GB"),
):
    """
    Get the curated local model catalog enriched with Hardware X-Ray fit badges
    and the single best model recommendation for this machine (SPEC-27).
    """
    raw_models = get_catalog(max_ram_gb=max_ram_gb, category=category)
    hw = get_hardware_profile()

    recommended = get_recommended(int(hw["total_ram_gb"]), limit=5)
    rec_ids = {r["id"] for r in recommended}

    models = []
    for m in raw_models:
        item = dict(m)
        if not item.get("logo_url"):
            fam = str(item.get("family") or "").lower()
            if fam in _FAMILY_DEFAULT_LOGOS:
                item["logo_url"] = _FAMILY_DEFAULT_LOGOS[fam]
        item["installed"] = model_manager.is_installed(item["id"])
        item["is_recommended"] = item["id"] in rec_ids
        item["fit"] = classify_model_fit(item, hw)
        models.append(item)

    best_for_machine = select_best_model_for_machine(models, hw, category=category)
    if best_for_machine:
        best_for_machine = dict(best_for_machine)
        best_for_machine["installed"] = model_manager.is_installed(best_for_machine["id"])

    return {
        "models": models,
        "total": len(models),
        "system_ram_gb": hw["total_ram_gb"],
        "max_recommended_params": hw["max_recommended_params"],
        "hardware": hw,
        "best_for_machine": best_for_machine,
        "recommended_model_id": best_for_machine["id"] if best_for_machine else None,
        "categories": get_all_categories(),
    }


@router.get("/catalog/{model_id}")
async def get_catalog_model(model_id: str):
    """Get details for a single catalog model."""
    entry = get_model(model_id)
    if not entry:
        return {"error": f"Model '{model_id}' not found in catalog"}
    out = dict(entry)
    out["installed"] = model_manager.is_installed(model_id)
    out["fit"] = classify_model_fit(out, get_hardware_profile())
    return out


@router.post("/catalog/refresh")
async def refresh_catalog_endpoint(request: Optional[CatalogRefreshRequest] = None):
    """Refresh the curated catalog from OTA cache or remote manifest (SPEC-34)."""
    req = request or CatalogRefreshRequest()
    try:
        return await refresh_ota_catalog(
            remote_url=req.remote_url,
            cache_path=req.cache_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/hf-search")
async def hf_search_endpoint(
    query: str = Query("", description="Search query"),
    sort: str = Query("trending", description="Sort order: trending | downloads | likes | recent"),
    limit: int = Query(20, ge=1, le=50),
    verified_only: bool = Query(True, description="Filter to verified GGUF quantizers"),
):
    """Search HuggingFace Hub live for GGUF models (SPEC-34)."""
    hf_token = await _resolve_hf_token()
    try:
        return await search_hf_gguf_models(
            query=query,
            sort=sort,
            limit=limit,
            verified_only=verified_only,
            hf_token=hf_token,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/hf-repo-files")
async def hf_repo_files_endpoint(
    repo_id: str = Query(..., description="HuggingFace repo id (e.g. unsloth/Qwen3-8B-GGUF)"),
):
    """List .gguf files in a HuggingFace repo with per-quant hardware fit badges (SPEC-34)."""
    hf_token = await _resolve_hf_token()
    try:
        return await list_hf_repo_gguf_files(
            repo_id=repo_id,
            hardware_profile=get_hardware_profile(),
            hf_token=hf_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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


@router.post("/import")
async def import_local_gguf_endpoint(request: ImportGGUFRequest):
    """Import an existing .gguf file from disk and sync it into the database (SPEC-08)."""
    try:
        result = model_manager.import_local_gguf(
            source_path=request.source_path,
            copy_file=request.copy_file,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        db = await get_database()
        if db is not None:
            await sync_local_models_to_db(db)
    except Exception as exc:
        logger.warning("Failed to sync imported model to DB: %s", exc)

    return result


@router.post("/download")
async def download_model(request: DownloadRequest):
    """
    Download a model from HuggingFace.

    Returns an SSE stream with progress updates.
    After download completes, auto-registers the model in the database
    so it appears in /api/v1/models/ for Chat, Workspace, and Crews.
    """
    hf_token = await _resolve_hf_token()

    async def event_stream():
        async for progress in model_manager.download_model(request.model_id, hf_token=hf_token):
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
    hf_token = await _resolve_hf_token()

    async def event_stream():
        async for progress in model_manager.download_custom(
            request.hf_repo, request.hf_filename, hf_token=hf_token
        ):
            yield f"data: {json.dumps(progress)}\n\n"
            if progress.get("status") == "done":
                try:
                    db = await get_database()
                    await sync_local_models_to_db(db)
                except Exception as e:
                    logger.warning("Failed to sync custom model to DB after download: %s", e)

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


@router.post("/{model_id}/preload")
async def preload_local_model(model_id: str):
    """Preload a local GGUF model into memory (SPEC-09)."""
    from services.local_model_service import local_model_service
    try:
        return await local_model_service.preload_model(model_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{model_id}/benchmark")
async def benchmark_local_model(model_id: str):
    """Run a quick speed benchmark on a local GGUF model and return tok/s (SPEC-15)."""
    from services.local_model_service import local_model_service
    try:
        return await local_model_service.benchmark_model(model_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/server-stats")
async def get_local_server_stats():
    """Return live /v1 request log and loaded model status for the /server control panel."""
    from routers.openai_compat import get_recent_v1_requests
    from services.local_model_service import local_model_service

    return {
        "loaded_model": local_model_service.get_status(),
        "recent_requests": get_recent_v1_requests(),
    }


@router.get("/server-config")
async def get_local_server_config():
    """Return whether the local OpenAI-compatible /v1 server is enabled."""
    enabled = is_local_server_enabled()
    return {
        "enabled": enabled,
        "server_enabled": enabled,
        "endpoint_base": _DEFAULT_V1_ENDPOINT_BASE,
    }


@router.post("/server-config")
async def update_local_server_config(request: ServerConfigRequest):
    """Enable or disable the local OpenAI-compatible /v1 server."""
    enabled = set_local_server_enabled(request.enabled)
    return {
        "enabled": enabled,
        "server_enabled": enabled,
        "endpoint_base": _DEFAULT_V1_ENDPOINT_BASE,
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


@router.post("/sync")
async def sync_models():
    """Sync installed GGUF models into the models DB collection."""
    db = await get_database()
    synced = await sync_local_models_to_db(db)
    return {"synced": synced}


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
