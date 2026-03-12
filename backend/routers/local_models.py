"""
Local GGUF model management API endpoints.
Provides endpoints to list, download, load, unload, and delete local AI models.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

try:
    from huggingface_hub import hf_hub_download

    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False
    logger.warning("huggingface_hub not installed — model downloads will be unavailable")

try:
    from sse_starlette.sse import EventSourceResponse

    SSE_AVAILABLE = True
except ImportError:
    SSE_AVAILABLE = False
    logger.warning("sse_starlette not installed — progress streaming will be unavailable")

router = APIRouter(prefix="/api/v1/local-models", tags=["local-models"])

# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------

AVAILABLE_MODELS: List[Dict[str, Any]] = [
    {
        "id": "gemma-3-1b",
        "name": "Gemma 3 1B",
        "file": "google_gemma-3-1b-it-Q4_K_M.gguf",
        "hf_repo": "bartowski/google_gemma-3-1b-it-GGUF",
        "hf_file": "google_gemma-3-1b-it-Q4_K_M.gguf",
        "size_bytes": 756_000_000,
        "ram_gb": 2,
        "supports_tools": False,
        "tier": "basic",
    },
    {
        "id": "qwen2.5-1.5b",
        "name": "Qwen 2.5 1.5B",
        "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "hf_repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "hf_file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size_bytes": 1_073_741_824,
        "ram_gb": 3,
        "supports_tools": True,
        "tier": "recommended",
    },
    {
        "id": "qwen2.5-3b",
        "name": "Qwen 2.5 3B",
        "file": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "hf_repo": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "hf_file": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "size_bytes": 2_147_483_648,
        "ram_gb": 4,
        "supports_tools": True,
        "tier": "best",
    },
]

# ---------------------------------------------------------------------------
# Models directory
# ---------------------------------------------------------------------------

MODELS_DIR = Path(
    os.environ.get("MODELS_DIR", os.path.expanduser("~/.contextuai-solo/models"))
)
CHAT_DIR = MODELS_DIR / "chat"
CHAT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# In-memory download progress tracking
# ---------------------------------------------------------------------------

_download_progress: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_model(model_id: str) -> Dict[str, Any]:
    """Look up a model by id in the catalog."""
    for m in AVAILABLE_MODELS:
        if m["id"] == model_id:
            return m
    raise HTTPException(status_code=404, detail=f"Unknown model id: {model_id}")


def _is_downloaded(model: Dict[str, Any]) -> bool:
    """Check whether the GGUF file exists on disk."""
    return (CHAT_DIR / model["file"]).is_file()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ModelIdRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/available")
async def list_available_models():
    """Return the full model catalog with a `downloaded` flag for each entry."""
    results = []
    for m in AVAILABLE_MODELS:
        results.append({**m, "downloaded": _is_downloaded(m)})
    return results


@router.get("/downloaded")
async def list_downloaded_models():
    """Return only models whose GGUF file is present on disk."""
    results = []
    # Check catalog models
    for m in AVAILABLE_MODELS:
        if _is_downloaded(m):
            results.append({**m, "downloaded": True})
    # Also list any extra .gguf files not in the catalog
    catalog_files = {m["file"] for m in AVAILABLE_MODELS}
    for path in CHAT_DIR.glob("*.gguf"):
        if path.name not in catalog_files:
            results.append(
                {
                    "id": path.stem,
                    "name": path.stem,
                    "file": path.name,
                    "hf_repo": None,
                    "hf_file": None,
                    "size_bytes": path.stat().st_size,
                    "ram_gb": None,
                    "supports_tools": None,
                    "tier": None,
                    "downloaded": True,
                }
            )
    return results


@router.get("/status")
async def get_model_status():
    """Return the currently loaded model info, or null."""
    try:
        from services.local_model_service import local_model_service

        status = local_model_service.get_status()
        return status
    except ImportError:
        logger.debug("LocalModelService not available")
        return None
    except Exception as exc:
        logger.error(f"Error getting model status: {exc}")
        return None


@router.post("/download", status_code=202)
async def start_download(body: ModelIdRequest):
    """Start a background download of a model from HuggingFace. Returns immediately."""
    if not HF_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="huggingface_hub is not installed. Install it with: pip install huggingface-hub",
        )

    model = _find_model(body.model_id)

    # Already downloaded?
    if _is_downloaded(model):
        return {"message": "Model already downloaded", "model_id": body.model_id}

    # Already downloading?
    existing = _download_progress.get(body.model_id)
    if existing and existing.get("status") == "downloading":
        return {"message": "Download already in progress", "model_id": body.model_id}

    # Initialise progress entry
    _download_progress[body.model_id] = {
        "model_id": body.model_id,
        "percent": 0.0,
        "bytes_downloaded": 0,
        "bytes_total": model["size_bytes"],
        "status": "downloading",
    }

    # Launch background download
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _download_model_sync, model)

    return {"message": "Download started", "model_id": body.model_id}


def _download_model_sync(model: Dict[str, Any]) -> None:
    """Synchronous download executed in a thread.

    hf_hub_download doesn't expose a progress callback, so we poll the
    target file size from a second thread to track progress.
    """
    import threading

    model_id = model["id"]
    target_file = CHAT_DIR / model["file"]
    expected_size = model["size_bytes"]
    stop_polling = threading.Event()

    def _poll_progress():
        """Check file size on disk every 0.5s to update progress.

        hf_hub_download stores temp files as hash-named .incomplete files
        inside .cache/huggingface/download/, not next to the target.
        We scan that directory for .incomplete files to track bytes.
        """
        cache_dir = CHAT_DIR / ".cache" / "huggingface" / "download"
        while not stop_polling.is_set():
            current = 0
            # Check if final file already exists
            if target_file.exists():
                try:
                    current = target_file.stat().st_size
                except OSError:
                    pass
            else:
                # Scan cache dir for .incomplete files (hf uses hash names)
                try:
                    if cache_dir.exists():
                        for f in cache_dir.iterdir():
                            if f.suffix == ".incomplete" and f.is_file():
                                try:
                                    current = max(current, f.stat().st_size)
                                except OSError:
                                    pass
                except OSError:
                    pass

            if expected_size > 0:
                pct = round(min(current / expected_size, 1.0) * 100, 1)
            else:
                pct = 0.0
            _download_progress[model_id] = {
                "model_id": model_id,
                "percent": pct,
                "bytes_downloaded": current,
                "bytes_total": expected_size,
                "status": "downloading",
            }
            stop_polling.wait(0.5)

    poller = threading.Thread(target=_poll_progress, daemon=True)
    poller.start()

    try:
        logger.info(f"Starting download: {model['name']} from {model['hf_repo']}")

        hf_hub_download(
            repo_id=model["hf_repo"],
            filename=model["hf_file"],
            local_dir=str(CHAT_DIR),
        )

        stop_polling.set()
        poller.join(timeout=2)

        _download_progress[model_id] = {
            "model_id": model_id,
            "percent": 100.0,
            "bytes_downloaded": expected_size,
            "bytes_total": expected_size,
            "status": "complete",
        }
        logger.info(f"Download complete: {model['name']}")

        # Seed a model config into the database so it appears in the chat dropdown
        _seed_local_model_config(model)

    except Exception as exc:
        stop_polling.set()
        poller.join(timeout=2)
        logger.error(f"Download failed for {model['name']}: {exc}")
        _download_progress[model_id] = {
            "model_id": model_id,
            "percent": _download_progress.get(model_id, {}).get("percent", 0.0),
            "bytes_downloaded": _download_progress.get(model_id, {}).get(
                "bytes_downloaded", 0
            ),
            "bytes_total": expected_size,
            "status": "error",
            "error": str(exc),
        }


def _seed_local_model_config(model: Dict[str, Any]) -> None:
    """Insert a model config into the DB so the chat page can see it."""
    import asyncio

    async def _do_seed():
        try:
            import database
            db = await database.get_database()
            collection = db["models"]
            model_id = f"local-{model['id']}"
            existing = await collection.find_one({"_id": model_id})
            if existing:
                return
            doc = {
                "_id": model_id,
                "name": model["name"],
                "provider": "local",
                "model": model_id,
                "max_tokens": "4096",
                "enabled": True,
                "description": f"Local {model['name']} model (GGUF, runs on CPU)",
                "capabilities": ["chat"],
                "input_cost": 0,
                "output_cost": 0,
                "context_window": 4096,
                "supports_vision": False,
                "supports_function_calling": model.get("supports_tools", False),
                "model_metadata": {
                    "runtime": "local",
                    "local_model_file": model["file"],
                    "ram_gb": model.get("ram_gb"),
                    "tier": model.get("tier"),
                },
            }
            await collection.insert_one(doc)
            logger.info(f"Seeded model config for local model: {model['name']}")
        except Exception as exc:
            logger.error(f"Failed to seed model config: {exc}")

    # Run async seed from sync context
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_do_seed(), loop).result(timeout=10)
        else:
            loop.run_until_complete(_do_seed())
    except Exception as exc:
        logger.error(f"Failed to run model config seeding: {exc}")


@router.get("/download/progress")
async def download_progress():
    """SSE endpoint streaming download progress for all active downloads."""
    if not SSE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="sse_starlette is not installed. Install it with: pip install sse-starlette",
        )

    async def event_generator():
        while True:
            if _download_progress:
                for model_id, progress in list(_download_progress.items()):
                    yield {
                        "event": "progress",
                        "data": json.dumps(progress),
                    }
                    # Clean up completed/errored entries after sending once
                    if progress.get("status") in ("complete", "error"):
                        _download_progress.pop(model_id, None)

            # If no active downloads remain, send a heartbeat then stop
            active = [
                p
                for p in _download_progress.values()
                if p.get("status") == "downloading"
            ]
            if not _download_progress and not active:
                yield {"event": "done", "data": json.dumps({"status": "no_active_downloads"})}
                break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@router.post("/load")
async def load_model(body: ModelIdRequest):
    """Load a downloaded model into RAM via LocalModelService."""
    model = _find_model(body.model_id)

    if not _is_downloaded(model):
        raise HTTPException(
            status_code=400,
            detail=f"Model {body.model_id} is not downloaded. Download it first.",
        )

    try:
        from services.local_model_service import local_model_service

        model_path = str(CHAT_DIR / model["file"])
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, local_model_service.load_model, model_path, body.model_id)
        return {"message": f"Model {model['name']} loaded", "model_id": body.model_id}
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="LocalModelService is not available. Ensure llama-cpp-python is installed.",
        )
    except Exception as exc:
        logger.error(f"Failed to load model {body.model_id}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/unload")
async def unload_model():
    """Unload the currently loaded model to free RAM."""
    try:
        from services.local_model_service import local_model_service

        local_model_service.unload_model()
        return {"message": "Model unloaded"}
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="LocalModelService is not available.",
        )
    except Exception as exc:
        logger.error(f"Failed to unload model: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{model_id}")
async def delete_model(model_id: str):
    """Delete a downloaded GGUF file from disk."""
    model = _find_model(model_id)

    file_path = CHAT_DIR / model["file"]
    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Model file not found: {model['file']}",
        )

    # Unload first if currently loaded
    try:
        from services.local_model_service import local_model_service

        status = local_model_service.get_status()
        if status and status.get("loaded_model_id") == model_id:
            local_model_service.unload_model()
            logger.info(f"Unloaded model {model_id} before deletion")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning(f"Could not check/unload model before deletion: {exc}")

    try:
        file_path.unlink()
        logger.info(f"Deleted model file: {file_path}")

        # Also remove the DB config so it disappears from chat dropdown
        try:
            import database
            db = await database.get_database()
            await db["models"].delete_one({"_id": f"local-{model_id}"})
            logger.info(f"Removed model config for local-{model_id}")
        except Exception as db_exc:
            logger.warning(f"Could not remove model config: {db_exc}")

        return {"message": f"Model {model['name']} deleted", "model_id": model_id}
    except Exception as exc:
        logger.error(f"Failed to delete {file_path}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync")
async def sync_local_models():
    """Sync downloaded models into the DB so they appear in the chat dropdown.

    Scans disk for downloaded GGUF files and ensures each has a
    corresponding model config in the 'models' collection.
    """
    try:
        import database
        db = await database.get_database()
        collection = db["models"]
        synced = 0

        for model in AVAILABLE_MODELS:
            if not _is_downloaded(model):
                continue
            model_id = f"local-{model['id']}"
            existing = await collection.find_one({"_id": model_id})
            if existing:
                continue
            doc = {
                "_id": model_id,
                "name": model["name"],
                "provider": "local",
                "model": model_id,
                "max_tokens": "4096",
                "enabled": True,
                "description": f"Local {model['name']} model (GGUF, runs on CPU)",
                "capabilities": ["chat"],
                "input_cost": 0,
                "output_cost": 0,
                "context_window": 4096,
                "supports_vision": False,
                "supports_function_calling": model.get("supports_tools", False),
                "model_metadata": {
                    "runtime": "local",
                    "local_model_file": model["file"],
                    "ram_gb": model.get("ram_gb"),
                    "tier": model.get("tier"),
                },
            }
            await collection.insert_one(doc)
            synced += 1
            logger.info(f"Synced model config: {model['name']}")

        return {"synced": synced, "message": f"Synced {synced} model config(s)"}
    except Exception as exc:
        logger.error(f"Failed to sync local models: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
