"""
Models API — exposes the 'models' collection to the frontend.
"""

import logging
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_db
from repositories.model_repository import ModelRepository
from services.default_model_service import DefaultModelService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])


class AiModePreference(BaseModel):
    ai_mode: str  # "local" or "cloud"


@router.get("/models/")
async def list_models(
    mode: Optional[str] = Query(None, description="Filter by AI mode: 'local' or 'cloud'"),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Return enabled model configs, optionally filtered by mode."""
    repo = ModelRepository(db)
    if mode == "local":
        models = await repo.get_enabled_models_by_mode("local")
    elif mode == "cloud":
        models = await repo.get_enabled_models_by_mode("cloud")
    else:
        models = await repo.get_enabled_models()
    return {"models": models}


@router.get("/models/preference")
async def get_ai_mode_preference(db: AsyncIOMotorDatabase = Depends(get_db)):
    """Return the saved AI mode preference."""
    svc = DefaultModelService(db)
    mode = await svc.get_ai_mode_preference()
    return {"ai_mode": mode}


@router.put("/models/preference")
async def set_ai_mode_preference(
    body: AiModePreference,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Save the AI mode preference."""
    if body.ai_mode not in ("local", "cloud"):
        raise HTTPException(status_code=400, detail="ai_mode must be 'local' or 'cloud'")
    svc = DefaultModelService(db)
    await svc.set_ai_mode_preference(body.ai_mode)
    return {"ai_mode": body.ai_mode}


@router.get("/models/{model_id}")
async def get_model(model_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Return a single model config by ID."""
    repo = ModelRepository(db)
    # Try by _id first (works for both ObjectId and string IDs)
    model = await repo.get_one({"_id": model_id})
    if not model:
        try:
            model = await repo.get_by_id(model_id)
        except (ValueError, Exception):
            pass
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model
