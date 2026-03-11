"""
Crews Router — CRUD API for crew configurations, runs, and memory.

Endpoints:
  POST   /api/v1/crews              — Create a crew
  GET    /api/v1/crews              — List user's crews
  GET    /api/v1/crews/{crew_id}    — Get crew details
  PATCH  /api/v1/crews/{crew_id}    — Update crew
  DELETE /api/v1/crews/{crew_id}    — Soft-delete crew
  POST   /api/v1/crews/{crew_id}/run        — Start a crew run
  GET    /api/v1/crews/{crew_id}/runs       — List runs for a crew
  GET    /api/v1/crews/runs/{run_id}        — Get run details
  POST   /api/v1/crews/runs/{run_id}/cancel — Cancel a run
  POST   /api/v1/crews/{crew_id}/memory     — Add a memory entry
  GET    /api/v1/crews/{crew_id}/memory     — List memories
  GET    /api/v1/crews/{crew_id}/memory/search — Search memories
  GET    /api/v1/crews/{crew_id}/memory/context — Get run context prompt
  DELETE /api/v1/crews/{crew_id}/memory/{memory_id} — Delete a memory
  DELETE /api/v1/crews/{crew_id}/memory     — Clear all memories
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from services.auth_service import get_current_user
from models.crew_models import (
    CreateCrewRequest,
    UpdateCrewRequest,
    RunCrewRequest,
    CrewResponse,
    CrewListItem,
    CrewListResponse,
    CrewRunResponse,
    CrewRunListItem,
    CrewRunListResponse,
)
from repositories.crew_repository import CrewRepository, CrewRunRepository
from repositories.crew_memory_repository import CrewMemoryRepository
from repositories.workspace_agent_repository import WorkspaceAgentRepository
from services.crew_service import CrewService, map_category_to_role
from services.crew_memory_service import CrewMemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/crews", tags=["crews"])


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------

async def get_crew_service(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> CrewService:
    """Inject CrewService with repositories."""
    return CrewService(
        CrewRepository(db),
        CrewRunRepository(db),
        WorkspaceAgentRepository(db),
    )


async def get_agent_repo(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> WorkspaceAgentRepository:
    """Inject WorkspaceAgentRepository for library-agent browsing."""
    return WorkspaceAgentRepository(db)


async def get_memory_service(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> CrewMemoryService:
    """Inject CrewMemoryService."""
    return CrewMemoryService(CrewMemoryRepository(db))


def _get_user_id(user: dict) -> str:
    """Extract user_id from auth context."""
    return user.get("user_id") or user.get("sub")


# ------------------------------------------------------------------
# Crew CRUD
# ------------------------------------------------------------------

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_crew(
    request: CreateCrewRequest,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
):
    """Create a new crew configuration."""
    user_id = _get_user_id(user)
    try:
        crew = await svc.create_crew(user_id, request)
        return {"status": "success", "data": CrewResponse(**crew).model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/")
async def list_crews(
    crew_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
):
    """List crews belonging to the current user."""
    user_id = _get_user_id(user)
    crews, total = await svc.list_crews(user_id, status=crew_status, page=page, page_size=page_size)
    items = []
    for c in crews:
        item_data = {k: v for k, v in c.items() if k in CrewListItem.model_fields}
        item_data["agent_count"] = c.get("agent_count", len(c.get("agents", [])))
        items.append(CrewListItem(**item_data))
    return CrewListResponse(crews=items, total_count=total, page=page, page_size=page_size).model_dump()


# ------------------------------------------------------------------
# Library Agent Browsing (must be before /{crew_id} to avoid collision)
# ------------------------------------------------------------------

@router.get("/library-agents")
async def list_library_agents(
    category: Optional[str] = Query(None, description="Filter by agent category"),
    search: Optional[str] = Query(None, description="Text search on name/description"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repo),
):
    """List workspace agents available for crew assignment, with suggested role mapping."""
    query_filter: dict = {"is_active": True}
    if category:
        query_filter["category"] = category
    if search:
        query_filter["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
        ]

    skip = (page - 1) * page_size
    agents = await agent_repo.get_all(
        filter=query_filter, skip=skip, limit=page_size, sort=[("name", 1)]
    )
    total = await agent_repo.count(query_filter)

    items = []
    for a in agents:
        role, custom_role = map_category_to_role(a.get("category", ""))
        items.append({
            "agent_id": a.get("agent_id"),
            "name": a.get("name"),
            "description": a.get("description", ""),
            "category": a.get("category", ""),
            "capabilities": a.get("capabilities", []),
            "icon": a.get("icon"),
            "suggested_role": role.value,
            "suggested_custom_role": custom_role,
            "estimated_cost_usd": a.get("estimated_cost_usd", 0),
            "usage_count": a.get("usage_count", 0),
        })

    return {
        "status": "success",
        "data": items,
        "total_count": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/library-agents/{agent_id}")
async def get_library_agent_detail(
    agent_id: str,
    user: dict = Depends(get_current_user),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repo),
):
    """Get full workspace agent detail including system_prompt for snapshotting into a crew."""
    agent = await agent_repo.get_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library agent not found")

    role, custom_role = map_category_to_role(agent.get("category", ""))
    return {
        "status": "success",
        "data": {
            "agent_id": agent.get("agent_id"),
            "name": agent.get("name"),
            "description": agent.get("description", ""),
            "category": agent.get("category", ""),
            "capabilities": agent.get("capabilities", []),
            "icon": agent.get("icon"),
            "system_prompt": agent.get("system_prompt", ""),
            "suggested_role": role.value,
            "suggested_custom_role": custom_role,
            "estimated_cost_usd": agent.get("estimated_cost_usd", 0),
            "usage_count": agent.get("usage_count", 0),
            "default_config": agent.get("default_config"),
        },
    }


@router.get("/{crew_id}")
async def get_crew(
    crew_id: str,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
):
    """Get full details of a crew."""
    user_id = _get_user_id(user)
    crew = await svc.get_crew(crew_id, user_id)
    if not crew:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew not found")
    return {"status": "success", "data": CrewResponse(**crew).model_dump()}


@router.patch("/{crew_id}")
async def update_crew(
    crew_id: str,
    request: UpdateCrewRequest,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
):
    """Update a crew configuration."""
    user_id = _get_user_id(user)
    try:
        crew = await svc.update_crew(crew_id, user_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not crew:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew not found")
    return {"status": "success", "data": CrewResponse(**crew).model_dump()}


@router.delete("/{crew_id}", status_code=status.HTTP_200_OK)
async def delete_crew(
    crew_id: str,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
):
    """Soft-delete a crew."""
    user_id = _get_user_id(user)
    deleted = await svc.delete_crew(crew_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew not found")
    return {"status": "success", "message": "Crew deleted"}


# ------------------------------------------------------------------
# Crew Runs
# ------------------------------------------------------------------

@router.post("/{crew_id}/run", status_code=status.HTTP_201_CREATED)
async def start_crew_run(
    crew_id: str,
    request: RunCrewRequest = None,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
):
    """Start a new execution of a crew."""
    user_id = _get_user_id(user)
    if request is None:
        request = RunCrewRequest()
    try:
        run = await svc.start_run(crew_id, user_id, request)
        return {"status": "success", "data": CrewRunResponse(**run).model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{crew_id}/runs")
async def list_crew_runs(
    crew_id: str,
    run_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
):
    """List execution runs for a crew."""
    user_id = _get_user_id(user)
    try:
        runs, total = await svc.list_runs(crew_id, user_id, status=run_status, page=page, page_size=page_size)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    items = [CrewRunListItem(**{k: v for k, v in r.items() if k in CrewRunListItem.model_fields}) for r in runs]
    return CrewRunListResponse(runs=items, total_count=total, page=page, page_size=page_size).model_dump()


@router.get("/runs/{run_id}")
async def get_crew_run(
    run_id: str,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
):
    """Get details of a specific crew run."""
    user_id = _get_user_id(user)
    run = await svc.get_run(run_id, user_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {"status": "success", "data": CrewRunResponse(**run).model_dump()}


@router.post("/runs/{run_id}/cancel")
async def cancel_crew_run(
    run_id: str,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
):
    """Cancel a pending or running crew execution."""
    user_id = _get_user_id(user)
    try:
        run = await svc.cancel_run(run_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {"status": "success", "data": CrewRunResponse(**run).model_dump()}


# ------------------------------------------------------------------
# Crew Memory
# ------------------------------------------------------------------

class AddMemoryRequest(BaseModel):
    """Request to add a memory entry."""
    content: str = Field(..., min_length=1, max_length=10000)
    key: Optional[str] = Field(None, max_length=200)
    category: str = Field(default="general")
    tags: List[str] = Field(default_factory=list)
    importance: str = Field(default="normal")
    ttl_hours: Optional[int] = Field(None, ge=1, le=8760)
    source_run_id: Optional[str] = None
    source_agent_id: Optional[str] = None
    source_agent_name: Optional[str] = None


@router.post("/{crew_id}/memory", status_code=status.HTTP_201_CREATED)
async def add_crew_memory(
    crew_id: str,
    request: AddMemoryRequest,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
    mem_svc: CrewMemoryService = Depends(get_memory_service),
):
    """Add a memory entry to a crew."""
    user_id = _get_user_id(user)
    crew = await svc.get_crew(crew_id, user_id)
    if not crew:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew not found")
    try:
        memory = await mem_svc.add_memory(
            crew_id,
            request.content,
            key=request.key,
            category=request.category,
            source_run_id=request.source_run_id,
            source_agent_id=request.source_agent_id,
            source_agent_name=request.source_agent_name,
            tags=request.tags,
            importance=request.importance,
            ttl_hours=request.ttl_hours,
        )
        return {"status": "success", "data": memory}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{crew_id}/memory")
async def list_crew_memories(
    crew_id: str,
    category: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    importance: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
    mem_svc: CrewMemoryService = Depends(get_memory_service),
):
    """List memories for a crew."""
    user_id = _get_user_id(user)
    crew = await svc.get_crew(crew_id, user_id)
    if not crew:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew not found")
    memories, total = await mem_svc.list_memories(
        crew_id, category=category, agent_id=agent_id,
        importance=importance, page=page, page_size=page_size,
    )
    return {"status": "success", "data": {"memories": memories, "total": total, "page": page, "page_size": page_size}}


@router.get("/{crew_id}/memory/search")
async def search_crew_memories(
    crew_id: str,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
    mem_svc: CrewMemoryService = Depends(get_memory_service),
):
    """Search crew memories by text content."""
    user_id = _get_user_id(user)
    crew = await svc.get_crew(crew_id, user_id)
    if not crew:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew not found")
    results = await mem_svc.search_memories(crew_id, q, limit=limit)
    return {"status": "success", "data": {"memories": results, "total": len(results)}}


@router.get("/{crew_id}/memory/context")
async def get_crew_memory_context(
    crew_id: str,
    max_entries: int = Query(30, ge=1, le=100),
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
    mem_svc: CrewMemoryService = Depends(get_memory_service),
):
    """Get formatted memory context prompt for a crew run."""
    user_id = _get_user_id(user)
    crew = await svc.get_crew(crew_id, user_id)
    if not crew:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew not found")
    prompt = await mem_svc.format_context_prompt(crew_id, max_entries=max_entries)
    return {"status": "success", "data": {"context_prompt": prompt, "has_memories": prompt is not None}}


@router.delete("/{crew_id}/memory/{memory_id}")
async def delete_crew_memory(
    crew_id: str,
    memory_id: str,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
    mem_svc: CrewMemoryService = Depends(get_memory_service),
):
    """Delete a specific memory entry."""
    user_id = _get_user_id(user)
    crew = await svc.get_crew(crew_id, user_id)
    if not crew:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew not found")
    deleted = await mem_svc.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return {"status": "success", "message": "Memory deleted"}


@router.delete("/{crew_id}/memory")
async def clear_crew_memories(
    crew_id: str,
    user: dict = Depends(get_current_user),
    svc: CrewService = Depends(get_crew_service),
    mem_svc: CrewMemoryService = Depends(get_memory_service),
):
    """Clear all memories for a crew."""
    user_id = _get_user_id(user)
    crew = await svc.get_crew(crew_id, user_id)
    if not crew:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew not found")
    count = await mem_svc.clear_crew_memories(crew_id)
    return {"status": "success", "message": f"Cleared {count} memories"}
