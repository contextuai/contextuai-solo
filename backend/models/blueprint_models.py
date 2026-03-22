"""
Blueprint Models — Pydantic models for Blueprint library and API contracts.

Blueprints are reusable workflow guides (markdown files) that provide structured
steps, frameworks, and processes for workspace projects and crew runs.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class BlueprintCategory(str, Enum):
    """Categories for organizing blueprints."""
    STRATEGY = "strategy"
    PRODUCT = "product"
    MARKETING = "marketing"
    CONTENT = "content"
    RESEARCH = "research"
    OPERATIONS = "operations"
    GENERAL = "general"


# =============================================================================
# Request Models
# =============================================================================

class CreateBlueprintRequest(BaseModel):
    """Request to create a custom blueprint."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    category: BlueprintCategory = BlueprintCategory.GENERAL
    content: str = Field(..., min_length=1, description="Markdown content of the blueprint")
    tags: List[str] = Field(default_factory=list)


class UpdateBlueprintRequest(BaseModel):
    """Request to update an existing blueprint."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    category: Optional[BlueprintCategory] = None
    content: Optional[str] = Field(None, min_length=1)
    tags: Optional[List[str]] = None


# =============================================================================
# Response Models
# =============================================================================

class BlueprintResponse(BaseModel):
    """Full blueprint response."""
    id: Optional[str] = None
    blueprint_id: str
    name: str
    description: Optional[str] = None
    category: str
    category_label: Optional[str] = None
    content: str = ""
    tags: List[str] = Field(default_factory=list)
    recommended_agents: List[str] = Field(default_factory=list)
    sections: Dict[str, str] = Field(default_factory=dict)
    source: str = "custom"
    is_system: bool = False
    usage_count: int = 0
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class BlueprintListItem(BaseModel):
    """Lightweight blueprint item for list views."""
    id: Optional[str] = None
    blueprint_id: str
    name: str
    description: Optional[str] = None
    category: str
    category_label: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source: str = "custom"
    is_system: bool = False
    usage_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BlueprintListResponse(BaseModel):
    """Paginated blueprint list response."""
    success: bool = True
    blueprints: List[BlueprintListItem]
    total_count: int
    page: int = 1
    page_size: int = 20
