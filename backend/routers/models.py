"""
Models API — exposes the 'models' collection to the frontend.
"""

import logging
from typing import Dict, Any, List

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_db
from repositories.model_repository import ModelRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["models"])


@router.get("/models/")
async def list_models(db: AsyncIOMotorDatabase = Depends(get_db)):
    """Return all enabled model configs (used by chat model dropdown)."""
    repo = ModelRepository(db)
    models = await repo.get_enabled_models()
    return {"models": models}


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
