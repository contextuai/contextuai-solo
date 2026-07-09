"""Unified Memory Layer REST API (SPEC-14 PR-A).

Endpoints
---------
- GET    /api/v1/memory/facts?scope=&status=&q=   — list / text-or-semantic search facts
- POST   /api/v1/memory/facts                     — add a manual fact
- GET    /api/v1/memory/facts/{id}                — read a fact
- PUT    /api/v1/memory/facts/{id}                — edit a fact (re-embeds if text changes)
- DELETE /api/v1/memory/facts/{id}                — delete a fact
- POST   /api/v1/memory/facts/{id}/pin            — pin/unpin a fact
- POST   /api/v1/memory/search                    — semantic search (recall primitive)
- GET    /api/v1/memory/export                    — full JSON export
- GET    /api/v1/memory/settings                  — kill switch + scope toggles
- PUT    /api/v1/memory/settings                  — update settings

PR-A scope only: no automatic extraction (PR-C) and no prompt-injection
wiring (PR-B) — this router only covers the manual store + panel needs.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from database import get_database
from models.memory_models import (
    MemoryFactCreate,
    MemoryFactPin,
    MemoryFactUpdate,
    MemorySearchRequest,
    MemorySettingsUpdate,
)
from repositories.memory_repository import MemoryRepository
from repositories.memory_settings_repository import MemorySettingsRepository
from services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


def _memory_repo(db=Depends(get_database)) -> MemoryRepository:
    return MemoryRepository(db)


def _settings_repo(db=Depends(get_database)) -> MemorySettingsRepository:
    return MemorySettingsRepository(db)


def _memory_service(
    memory_repo: MemoryRepository = Depends(_memory_repo),
    settings_repo: MemorySettingsRepository = Depends(_settings_repo),
) -> MemoryService:
    return MemoryService(memory_repo, settings_repo)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------

@router.get("/facts")
async def list_facts(
    scope: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    service: MemoryService = Depends(_memory_service),
) -> Dict[str, Any]:
    items = await service.list_facts(scope=scope, status=status, q=q)
    return {"items": items}


@router.post("/facts")
async def create_fact(
    payload: MemoryFactCreate, service: MemoryService = Depends(_memory_service)
) -> Dict[str, Any]:
    item = await service.add_fact(payload)
    return {"item": item}


@router.get("/facts/{fact_id}")
async def get_fact(
    fact_id: str, service: MemoryService = Depends(_memory_service)
) -> Dict[str, Any]:
    item = await service.get_fact(fact_id)
    if not item:
        raise HTTPException(404, "Fact not found")
    return {"item": item}


@router.put("/facts/{fact_id}")
async def update_fact(
    fact_id: str,
    payload: MemoryFactUpdate,
    service: MemoryService = Depends(_memory_service),
) -> Dict[str, Any]:
    item = await service.update_fact(fact_id, payload)
    if not item:
        raise HTTPException(404, "Fact not found")
    return {"item": item}


@router.delete("/facts/{fact_id}")
async def delete_fact(
    fact_id: str, service: MemoryService = Depends(_memory_service)
) -> Dict[str, Any]:
    existing = await service.get_fact(fact_id)
    if not existing:
        raise HTTPException(404, "Fact not found")
    await service.delete_fact(fact_id)
    return {"deleted": True}


@router.post("/facts/{fact_id}/pin")
async def pin_fact(
    fact_id: str,
    payload: MemoryFactPin,
    service: MemoryService = Depends(_memory_service),
) -> Dict[str, Any]:
    item = await service.set_pinned(fact_id, payload.pinned)
    if not item:
        raise HTTPException(404, "Fact not found")
    return {"item": item}


# ---------------------------------------------------------------------------
# Search / export
# ---------------------------------------------------------------------------

@router.post("/search")
async def search_facts(
    payload: MemorySearchRequest, service: MemoryService = Depends(_memory_service)
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = await service.search(payload)
    return {"query": payload.query, "items": results}


@router.get("/export")
async def export_facts(service: MemoryService = Depends(_memory_service)) -> Dict[str, Any]:
    return await service.export_all()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_settings(service: MemoryService = Depends(_memory_service)) -> Dict[str, Any]:
    return await service.get_settings()


@router.put("/settings")
async def update_settings(
    payload: MemorySettingsUpdate, service: MemoryService = Depends(_memory_service)
) -> Dict[str, Any]:
    return await service.update_settings(payload)
