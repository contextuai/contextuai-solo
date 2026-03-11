"""Workspace Project Types API - CRUD for project types, workshop types, and output formats."""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

# Import database and repositories
from database import get_database
from repositories import WorkspaceProjectTypeRepository

router = APIRouter(prefix="/api/v1/workspace-project-types", tags=["workspace-project-types"])


# Dependency function to get WorkspaceProjectTypeRepository
async def get_workspace_project_type_repository(
    db: AsyncIOMotorDatabase = Depends(get_database)
) -> WorkspaceProjectTypeRepository:
    """Get WorkspaceProjectTypeRepository instance with database dependency."""
    return WorkspaceProjectTypeRepository(db)


# Pydantic models for validation
class WorkspaceProjectTypeCreate(BaseModel):
    key: str = Field(..., min_length=1, description="Unique key like 'build', 'workshop', 'research'")
    label: str = Field(..., min_length=1, description="Display name")
    description: str = Field(..., description="Description shown in UI")
    icon: str = Field(..., description="Lucide icon name like 'Code', 'Users', 'Search'")
    category: str = Field(..., description="Category: 'project_type', 'workshop_type', or 'output_format'")
    color: Optional[str] = Field(None, description="Hex color for UI")
    sort_order: int = Field(0, description="Display order")
    enabled: bool = Field(True)
    config: Optional[Dict[str, Any]] = Field(None, description="Additional type-specific configuration")


class WorkspaceProjectTypeUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


class WorkspaceProjectTypeResponse(BaseModel):
    success: bool
    project_types: List[Dict[str, Any]]
    total_count: int
    last_updated: str
    source: str = "mongodb"
    error: Optional[str] = None


@router.get("", response_model=WorkspaceProjectTypeResponse)
@router.get("/", response_model=WorkspaceProjectTypeResponse)
async def list_workspace_project_types(
    category: Optional[str] = None,
    enabled: Optional[bool] = None,
    repo: WorkspaceProjectTypeRepository = Depends(get_workspace_project_type_repository)
):
    """List all workspace project types with optional filtering.

    Args:
        category: Filter by category ('project_type', 'workshop_type', 'output_format')
        enabled: Filter by enabled status (true = available, false = disabled)
    """
    try:
        if category:
            project_types = await repo.get_by_category(
                category=category,
                enabled=enabled
            )
        elif enabled is not None:
            project_types = await repo.get_all(filter={"enabled": enabled})
        else:
            project_types = await repo.get_all()

        return WorkspaceProjectTypeResponse(
            success=True,
            project_types=project_types,
            total_count=len(project_types),
            last_updated=datetime.utcnow().isoformat() + "Z"
        )
    except Exception as e:
        return WorkspaceProjectTypeResponse(
            success=False,
            project_types=[],
            total_count=0,
            last_updated=datetime.utcnow().isoformat() + "Z",
            error=str(e)
        )


@router.get("/{project_type_id}", response_model=Dict[str, Any])
async def get_workspace_project_type(
    project_type_id: str,
    repo: WorkspaceProjectTypeRepository = Depends(get_workspace_project_type_repository)
):
    """Get a specific workspace project type by ID or key."""
    try:
        # First try by string key field (e.g., 'build', 'workshop', 'strategy')
        project_type = await repo.get_by_string_id(project_type_id)

        if project_type is None:
            # Try by MongoDB ObjectId
            try:
                project_type = await repo.get_by_id(project_type_id)
            except ValueError:
                pass  # Invalid ObjectId format, that's fine

        if project_type is None:
            raise HTTPException(status_code=404, detail="Workspace project type not found")

        return project_type
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Dict[str, Any])
async def create_workspace_project_type(
    project_type: WorkspaceProjectTypeCreate,
    repo: WorkspaceProjectTypeRepository = Depends(get_workspace_project_type_repository)
):
    """Create a new workspace project type."""
    try:
        # Check if key already exists
        existing = await repo.get_by_string_id(project_type.key)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="Workspace project type with this key already exists"
            )

        # Convert Pydantic model to dict
        project_type_dict = project_type.model_dump()
        project_type_dict["status"] = "active"

        # Create using repository (timestamps are handled by BaseRepository)
        created = await repo.create(project_type_dict)

        return created
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{project_type_id}", response_model=Dict[str, Any])
async def update_workspace_project_type(
    project_type_id: str,
    update_data: WorkspaceProjectTypeUpdate,
    repo: WorkspaceProjectTypeRepository = Depends(get_workspace_project_type_repository)
):
    """Update an existing workspace project type."""
    try:
        # First try to find by string key field
        existing = await repo.get_by_string_id(project_type_id)
        mongo_id = None

        if existing is not None:
            mongo_id = existing.get("id")
        else:
            # Try by MongoDB ObjectId
            try:
                existing = await repo.get_by_id(project_type_id)
                if existing is not None:
                    mongo_id = project_type_id
            except ValueError:
                pass  # Invalid ObjectId format

        if existing is None:
            raise HTTPException(status_code=404, detail="Workspace project type not found")

        # Only include non-None fields for partial update
        update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}

        if not update_dict:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Update using repository (updated_at is handled by BaseRepository)
        updated = await repo.update(mongo_id, update_dict)

        if updated is None:
            raise HTTPException(status_code=404, detail="Workspace project type not found")

        return updated
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid project type ID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{project_type_id}")
async def delete_workspace_project_type(
    project_type_id: str,
    repo: WorkspaceProjectTypeRepository = Depends(get_workspace_project_type_repository)
):
    """Delete a workspace project type."""
    try:
        # First try to find by string key field
        existing = await repo.get_by_string_id(project_type_id)
        mongo_id = None

        if existing is not None:
            mongo_id = existing.get("id")
        else:
            # Try by MongoDB ObjectId
            try:
                existing = await repo.get_by_id(project_type_id)
                if existing is not None:
                    mongo_id = project_type_id
            except ValueError:
                pass  # Invalid ObjectId format

        if existing is None:
            raise HTTPException(status_code=404, detail="Workspace project type not found")

        # Delete using repository
        deleted = await repo.delete(mongo_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Workspace project type not found")

        return {"message": "Workspace project type deleted successfully"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid project type ID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
