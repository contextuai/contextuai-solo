from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

# Import database and repositories
from database import get_database
from repositories import PersonaTypeRepository

router = APIRouter(prefix="/api/v1/persona-types", tags=["persona-types"])


# Dependency function to get PersonaTypeRepository
async def get_persona_type_repository(db: AsyncIOMotorDatabase = Depends(get_database)) -> PersonaTypeRepository:
    """Get PersonaTypeRepository instance with database dependency."""
    return PersonaTypeRepository(db)


# Pydantic models for validation
class CredentialField(BaseModel):
    name: str
    label: str
    placeholder: Optional[str] = None
    type: str = Field(..., pattern="^(text|email|password|number|boolean|textarea|select)$")
    required: bool = True
    options: Optional[List[str]] = None  # For select type dropdown options

class PersonaType(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str
    icon: str
    color: str = Field(..., pattern="^#[0-9A-Fa-f]{6}$")
    category: str
    status: str = Field(default="active", pattern="^(active|inactive)$")
    enabled: bool = Field(default=True, description="Whether this persona type connector is implemented and available")
    credentialFields: List[CredentialField]

class PersonaTypeResponse(BaseModel):
    success: bool
    persona_types: List[Dict[str, Any]]
    total_count: int
    last_updated: str
    source: str = "mongodb"
    error: Optional[str] = None

@router.get("", response_model=PersonaTypeResponse)
@router.get("/", response_model=PersonaTypeResponse)
async def list_persona_types(
    category: Optional[str] = None,
    status: Optional[str] = None,
    enabled: Optional[bool] = None,
    persona_type_repo: PersonaTypeRepository = Depends(get_persona_type_repository)
):
    """List all persona types with optional filtering

    Args:
        category: Filter by category (e.g., "Data & Analytics", "Communication")
        status: Filter by lifecycle status ("active" or "inactive")
        enabled: Filter by implementation status (true = implemented, false = not yet implemented)
    """
    try:
        if category and status:
            # Use repository method for category + status filtering
            persona_types = await persona_type_repo.get_by_category_and_status(
                category=category,
                status=status
            )
        elif category:
            # Query by category
            persona_types = await persona_type_repo.get_by_category(
                category=category,
                status=status
            )
        elif status:
            # Query by status
            filter_query = {"status": status.lower()}
            persona_types = await persona_type_repo.get_all(filter=filter_query)
        else:
            # Get all persona types
            persona_types = await persona_type_repo.get_all()

        # Apply enabled filter if provided
        if enabled is not None:
            persona_types = [p for p in persona_types if p.get("enabled", True) == enabled]

        return PersonaTypeResponse(
            success=True,
            persona_types=persona_types,
            total_count=len(persona_types),
            last_updated=datetime.utcnow().isoformat() + "Z"
        )
    except Exception as e:
        return PersonaTypeResponse(
            success=False,
            persona_types=[],
            total_count=0,
            last_updated=datetime.utcnow().isoformat() + "Z",
            error=str(e)
        )

@router.get("/{persona_type_id}", response_model=Dict[str, Any])
async def get_persona_type(
    persona_type_id: str,
    persona_type_repo: PersonaTypeRepository = Depends(get_persona_type_repository)
):
    """Get a specific persona type by ID"""
    try:
        # First try by string ID field (e.g., 'postgresql_database')
        persona_type = await persona_type_repo.get_by_string_id(persona_type_id)

        if persona_type is None:
            # Try by MongoDB ObjectId
            try:
                persona_type = await persona_type_repo.get_by_id(persona_type_id)
            except ValueError:
                pass  # Invalid ObjectId format, that's fine

        if persona_type is None:
            raise HTTPException(status_code=404, detail="Persona type not found")

        return persona_type
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=Dict[str, Any])
async def create_persona_type(
    persona: PersonaType,
    persona_type_repo: PersonaTypeRepository = Depends(get_persona_type_repository)
):
    """Create a new persona type"""
    try:
        # Check if ID already exists (check by string id field)
        existing = await persona_type_repo.get_by_string_id(persona.id)
        if existing is not None:
            raise HTTPException(status_code=409, detail="Persona type with this ID already exists")

        # Convert Pydantic model to dict
        persona_dict = persona.model_dump()

        # Create using repository (timestamps are handled by BaseRepository)
        created_persona_type = await persona_type_repo.create(persona_dict)

        return created_persona_type
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{persona_type_id}", response_model=Dict[str, Any])
async def update_persona_type(
    persona_type_id: str,
    persona: PersonaType,
    persona_type_repo: PersonaTypeRepository = Depends(get_persona_type_repository)
):
    """Update an existing persona type"""
    try:
        # First try to find by string ID field
        existing_persona_type = await persona_type_repo.get_by_string_id(persona_type_id)
        mongo_id = None

        if existing_persona_type is not None:
            mongo_id = existing_persona_type.get("id")
        else:
            # Try by MongoDB ObjectId
            try:
                existing_persona_type = await persona_type_repo.get_by_id(persona_type_id)
                if existing_persona_type is not None:
                    mongo_id = persona_type_id
            except ValueError:
                pass  # Invalid ObjectId format

        if existing_persona_type is None:
            raise HTTPException(status_code=404, detail="Persona type not found")

        # Convert Pydantic model to dict and ensure ID matches
        persona_dict = persona.model_dump()
        persona_dict["id"] = persona.id  # Keep the string id field

        # Preserve created_at from existing document
        if "created_at" in existing_persona_type:
            persona_dict["created_at"] = existing_persona_type["created_at"]

        # Update using repository (updated_at is handled by BaseRepository)
        updated_persona_type = await persona_type_repo.update(mongo_id, persona_dict)

        if updated_persona_type is None:
            raise HTTPException(status_code=404, detail="Persona type not found")

        return updated_persona_type
    except HTTPException:
        raise
    except ValueError as e:
        # Invalid ObjectId format
        raise HTTPException(status_code=400, detail=f"Invalid persona type ID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{persona_type_id}")
async def delete_persona_type(
    persona_type_id: str,
    persona_type_repo: PersonaTypeRepository = Depends(get_persona_type_repository)
):
    """Delete a persona type"""
    try:
        # First try to find by string ID field
        existing_persona_type = await persona_type_repo.get_by_string_id(persona_type_id)
        mongo_id = None

        if existing_persona_type is not None:
            mongo_id = existing_persona_type.get("id")
        else:
            # Try by MongoDB ObjectId
            try:
                existing_persona_type = await persona_type_repo.get_by_id(persona_type_id)
                if existing_persona_type is not None:
                    mongo_id = persona_type_id
            except ValueError:
                pass  # Invalid ObjectId format

        if existing_persona_type is None:
            raise HTTPException(status_code=404, detail="Persona type not found")

        # Delete using repository
        deleted = await persona_type_repo.delete(mongo_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Persona type not found")

        return {"message": "Persona type deleted successfully"}
    except HTTPException:
        raise
    except ValueError as e:
        # Invalid ObjectId format
        raise HTTPException(status_code=400, detail=f"Invalid persona type ID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
