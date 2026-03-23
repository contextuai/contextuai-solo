"""
Blueprints Router — CRUD API for blueprint library and custom blueprints.

Endpoints:
  GET    /api/v1/blueprints/library              — Browse .md catalog
  GET    /api/v1/blueprints/library/search        — Full-text search .md files
  GET    /api/v1/blueprints/library/{cat}/{slug}  — Get full detail from .md
  POST   /api/v1/blueprints/library/sync          — Re-read files, upsert to DB
  GET    /api/v1/blueprints                       — List all from DB
  GET    /api/v1/blueprints/{blueprint_id}        — Get by ID from DB
  POST   /api/v1/blueprints                       — Create custom blueprint
  PATCH  /api/v1/blueprints/{blueprint_id}        — Update custom blueprint
  DELETE /api/v1/blueprints/{blueprint_id}        — Soft-delete blueprint
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from services.auth_service import get_current_user
from models.blueprint_models import (
    CreateBlueprintRequest,
    UpdateBlueprintRequest,
    BlueprintResponse,
    BlueprintListItem,
    BlueprintListResponse,
)
from repositories.blueprint_repository import BlueprintRepository
from services.blueprint_library_service import BlueprintLibraryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/blueprints", tags=["blueprints"])


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------

async def get_blueprint_repo(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> BlueprintRepository:
    return BlueprintRepository(db)


def get_library_service() -> BlueprintLibraryService:
    return BlueprintLibraryService()


def _get_user_id(user: dict) -> str:
    return user.get("user_id") or user.get("sub") or "desktop-user"


# ------------------------------------------------------------------
# Library endpoints (file-based)
# ------------------------------------------------------------------

@router.get("/library")
async def get_library_catalog(
    category: Optional[str] = Query(None, description="Filter by category"),
    svc: BlueprintLibraryService = Depends(get_library_service),
):
    """Browse blueprint .md files as catalog entries."""
    catalog = await svc.get_catalog(category=category)
    return {"status": "success", **catalog}


@router.get("/library/search")
async def search_library(
    q: str = Query(..., min_length=1, description="Search query"),
    svc: BlueprintLibraryService = Depends(get_library_service),
):
    """Full-text search over blueprint library files."""
    results = await svc.search_catalog(q)
    return {"status": "success", **results}


@router.get("/library/{category}/{slug}")
async def get_library_detail(
    category: str,
    slug: str,
    svc: BlueprintLibraryService = Depends(get_library_service),
):
    """Get full parsed content for a specific blueprint from the .md library."""
    detail = await svc.get_detail(category, slug)
    if not detail:
        raise HTTPException(status_code=404, detail="Blueprint not found in library")
    return {"status": "success", "data": detail}


@router.post("/library/sync")
async def sync_library(
    db: AsyncIOMotorDatabase = Depends(get_database),
    user: dict = Depends(get_current_user),
    svc: BlueprintLibraryService = Depends(get_library_service),
):
    """Re-read all .md files and upsert to the blueprints collection."""
    collection = db["blueprints"]
    seeded = await svc.sync_library_to_db(collection)
    return {"status": "success", "message": f"Synced {seeded} new blueprint(s)"}


# ------------------------------------------------------------------
# DB endpoints (system + custom blueprints)
# ------------------------------------------------------------------

@router.get("/")
async def list_blueprints(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="Filter: library, custom"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    repo: BlueprintRepository = Depends(get_blueprint_repo),
):
    """List all blueprints from DB with optional filters."""
    user_id = _get_user_id(user)
    offset = (page - 1) * page_size

    docs, total = await repo.get_user_blueprints(
        user_id=user_id,
        category=category,
        search=search,
        source=source,
        limit=page_size,
        offset=offset,
    )

    items = [
        BlueprintListItem(
            id=doc.get("id"),
            blueprint_id=doc.get("blueprint_id", doc.get("id", "")),
            name=doc.get("name", ""),
            description=doc.get("description"),
            category=doc.get("category", "general"),
            category_label=doc.get("category_label"),
            tags=doc.get("tags", []),
            source=doc.get("source", "custom"),
            is_system=doc.get("is_system", False),
            usage_count=doc.get("usage_count", 0),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        ).model_dump()
        for doc in docs
    ]

    return {
        "status": "success",
        "blueprints": items,
        "total_count": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{blueprint_id}")
async def get_blueprint(
    blueprint_id: str,
    user: dict = Depends(get_current_user),
    repo: BlueprintRepository = Depends(get_blueprint_repo),
):
    """Get a blueprint by ID from DB."""
    doc = await repo.get_by_blueprint_id(blueprint_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    resp = BlueprintResponse(
        id=doc.get("id"),
        blueprint_id=doc.get("blueprint_id", doc.get("id", "")),
        name=doc.get("name", ""),
        description=doc.get("description"),
        category=doc.get("category", "general"),
        category_label=doc.get("category_label"),
        content=doc.get("content", ""),
        tags=doc.get("tags", []),
        recommended_agents=doc.get("recommended_agents", []),
        sections=doc.get("sections", {}),
        source=doc.get("source", "custom"),
        is_system=doc.get("is_system", False),
        usage_count=doc.get("usage_count", 0),
        created_by=doc.get("created_by"),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )

    return {"status": "success", "data": resp.model_dump()}


@router.post("/", status_code=201)
async def create_blueprint(
    request: CreateBlueprintRequest,
    user: dict = Depends(get_current_user),
    repo: BlueprintRepository = Depends(get_blueprint_repo),
):
    """Create a custom blueprint."""
    user_id = _get_user_id(user)

    data = {
        "name": request.name,
        "description": request.description,
        "category": request.category.value,
        "category_label": BlueprintLibraryService.CATEGORY_LABELS.get(
            request.category.value, request.category.value
        ),
        "content": request.content,
        "tags": request.tags,
        "recommended_agents": [],
        "sections": {},
    }

    doc = await repo.create_blueprint(user_id, data)

    return {
        "status": "success",
        "data": BlueprintResponse(
            id=doc.get("id"),
            blueprint_id=doc["blueprint_id"],
            name=doc["name"],
            description=doc.get("description"),
            category=doc["category"],
            category_label=doc.get("category_label"),
            content=doc.get("content", ""),
            tags=doc.get("tags", []),
            source="custom",
            is_system=False,
            created_by=user_id,
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        ).model_dump(),
    }


@router.patch("/{blueprint_id}")
async def update_blueprint(
    blueprint_id: str,
    request: UpdateBlueprintRequest,
    user: dict = Depends(get_current_user),
    repo: BlueprintRepository = Depends(get_blueprint_repo),
):
    """Update a custom blueprint."""
    existing = await repo.get_by_blueprint_id(blueprint_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    if existing.get("is_system"):
        raise HTTPException(status_code=403, detail="Cannot edit system blueprints")

    update_data = request.model_dump(exclude_none=True)
    if "category" in update_data:
        update_data["category"] = update_data["category"].value if hasattr(update_data["category"], "value") else update_data["category"]
        update_data["category_label"] = BlueprintLibraryService.CATEGORY_LABELS.get(
            update_data["category"], update_data["category"]
        )

    doc = await repo.update_blueprint(blueprint_id, update_data)
    if not doc:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    return {"status": "success", "data": doc}


@router.delete("/{blueprint_id}")
async def delete_blueprint(
    blueprint_id: str,
    user: dict = Depends(get_current_user),
    repo: BlueprintRepository = Depends(get_blueprint_repo),
):
    """Soft-delete a blueprint."""
    existing = await repo.get_by_blueprint_id(blueprint_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    if existing.get("is_system"):
        raise HTTPException(status_code=403, detail="Cannot delete system blueprints")

    deleted = await repo.soft_delete_blueprint(blueprint_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    return {"status": "success", "message": "Blueprint deleted"}
