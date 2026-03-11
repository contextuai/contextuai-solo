"""
Tool management API endpoints.
Provides endpoints to list capabilities, get tool metadata, and test tools.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import logging
import os
from motor.motor_asyncio import AsyncIOMotorDatabase

from services.tools import get_tool_registry
from database import get_database
from repositories import PersonaRepository, PersonaTypeRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


# Dependency functions for repositories
async def get_persona_repository(db: AsyncIOMotorDatabase = Depends(get_database)) -> PersonaRepository:
    """Get PersonaRepository instance with database dependency."""
    return PersonaRepository(db)


async def get_persona_type_repository(db: AsyncIOMotorDatabase = Depends(get_database)) -> PersonaTypeRepository:
    """Get PersonaTypeRepository instance with database dependency."""
    return PersonaTypeRepository(db)


class ToolCapabilitiesResponse(BaseModel):
    """Response model for listing tool capabilities."""
    capabilities: List[str] = Field(..., description="List of available capabilities")
    total: int = Field(..., description="Total number of capabilities")


class ToolMetadataResponse(BaseModel):
    """Response model for tool metadata."""
    capability: str = Field(..., description="Capability name")
    available: bool = Field(..., description="Whether tools are available for this capability")
    tools: List[Dict[str, Any]] = Field(..., description="List of tools and their metadata")


class PersonaToolsResponse(BaseModel):
    """Response model for persona tools."""
    persona_id: str = Field(..., description="Persona ID")
    persona_name: Optional[str] = Field(None, description="Persona name")
    capabilities: List[str] = Field(..., description="Persona capabilities")
    tools_count: int = Field(..., description="Number of tools loaded")
    tools: List[Dict[str, Any]] = Field(..., description="Tool information")


class TestToolRequest(BaseModel):
    """Request model for testing a tool."""
    capability: str = Field(..., description="Capability to test")
    tool_name: str = Field(..., description="Tool name to test")
    method_name: str = Field(..., description="Method to call")
    parameters: Dict[str, Any] = Field(default={}, description="Parameters for the method")


class TestToolResponse(BaseModel):
    """Response model for tool test results."""
    success: bool = Field(..., description="Whether the test succeeded")
    result: Optional[Dict[str, Any]] = Field(None, description="Test result")
    error: Optional[str] = Field(None, description="Error message if failed")


@router.get("/capabilities", response_model=ToolCapabilitiesResponse)
async def list_capabilities():
    """
    List all available tool capabilities.

    Returns a list of capability names that can be assigned to personas.
    """
    try:
        tool_registry = get_tool_registry()
        capabilities = tool_registry.list_all_capabilities()

        logger.info(f"Listed {len(capabilities)} tool capabilities")

        return ToolCapabilitiesResponse(
            capabilities=capabilities,
            total=len(capabilities)
        )

    except Exception as e:
        logger.error(f"Error listing capabilities: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list capabilities: {str(e)}"
        )


@router.get("/capability/{capability}", response_model=ToolMetadataResponse)
async def get_capability_metadata(capability: str):
    """
    Get metadata about tools available for a specific capability.

    Args:
        capability: The capability name to get metadata for

    Returns metadata about available tools for the capability.
    """
    try:
        tool_registry = get_tool_registry()
        metadata = tool_registry.get_tool_metadata(capability)

        if not metadata["available"]:
            logger.warning(f"No tools available for capability: {capability}")

        return ToolMetadataResponse(**metadata)

    except Exception as e:
        logger.error(f"Error getting capability metadata: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get capability metadata: {str(e)}"
        )


@router.get("/persona/{persona_id}", response_model=PersonaToolsResponse)
async def get_persona_tools(
    persona_id: str,
    persona_repo: PersonaRepository = Depends(get_persona_repository),
    persona_type_repo: PersonaTypeRepository = Depends(get_persona_type_repository)
):
    """
    Get tools loaded for a specific persona.

    Args:
        persona_id: The persona ID to get tools for

    Returns information about tools loaded for the persona.
    """
    try:
        tool_registry = get_tool_registry()

        # Get persona instance from MongoDB
        persona_instance = await persona_repo.get_by_id(persona_id, include_credentials=True)
        if not persona_instance:
            raise HTTPException(
                status_code=404,
                detail=f"Persona not found: {persona_id}"
            )

        # Get persona type to retrieve capabilities
        persona_type_id = persona_instance.get("persona_type_id")
        persona_type = None
        capabilities = []

        if persona_type_id:
            # Try to get persona type by string ID first, then by ObjectId
            persona_type = await persona_type_repo.get_by_string_id(persona_type_id)
            if persona_type is None:
                try:
                    persona_type = await persona_type_repo.get_by_id(persona_type_id)
                except ValueError:
                    pass  # Invalid ObjectId format

            if persona_type:
                capabilities = persona_type.get("capabilities", [])

        # Get tools from registry based on persona type
        tools = tool_registry.get_tools_for_persona_type(
            persona_id=persona_id,
            persona_type_id=persona_type_id,
            persona_data=persona_instance
        )

        # Format tool information
        tool_info = []
        for tool in tools:
            if hasattr(tool, '__name__'):
                tool_info.append({
                    "name": tool.__name__,
                    "type": type(tool).__name__,
                    "description": tool.__doc__ or "No description"
                })

        return PersonaToolsResponse(
            persona_id=persona_id,
            persona_name=persona_instance.get("name"),
            capabilities=capabilities,
            tools_count=len(tools),
            tools=tool_info
        )

    except HTTPException:
        raise
    except ValueError as e:
        # Invalid ObjectId format
        raise HTTPException(
            status_code=400,
            detail=f"Invalid persona ID format: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error getting persona tools: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get persona tools: {str(e)}"
        )


@router.post("/test", response_model=TestToolResponse)
async def test_tool(request: TestToolRequest):
    """
    Test a specific tool method (development/debugging endpoint).

    Args:
        request: Test request with capability, tool, method, and parameters

    Returns test execution result.

    Note: This endpoint should be restricted in production.
    """
    import os

    # Only allow in development
    if os.getenv("ENVIRONMENT", "dev") == "prod":
        raise HTTPException(
            status_code=403,
            detail="Tool testing is not available in production"
        )

    try:
        tool_registry = get_tool_registry()

        # Get tool class for capability
        if request.capability not in tool_registry._capability_tool_map:
            return TestToolResponse(
                success=False,
                error=f"Unknown capability: {request.capability}"
            )

        tool_classes = tool_registry._capability_tool_map[request.capability]

        # Find matching tool class
        tool_class = None
        for tc in tool_classes:
            if tc.__name__ == request.tool_name:
                tool_class = tc
                break

        if not tool_class:
            return TestToolResponse(
                success=False,
                error=f"Tool not found: {request.tool_name}"
            )

        # Create tool instance
        tool_instance = tool_class()

        # Get method
        if not hasattr(tool_instance, request.method_name):
            return TestToolResponse(
                success=False,
                error=f"Method not found: {request.method_name}"
            )

        method = getattr(tool_instance, request.method_name)

        # Call method with parameters
        import asyncio
        if asyncio.iscoroutinefunction(method):
            result = await method(**request.parameters)
        else:
            result = method(**request.parameters)

        logger.info(f"Tool test successful: {request.tool_name}.{request.method_name}")

        return TestToolResponse(
            success=True,
            result=result if isinstance(result, dict) else {"result": str(result)}
        )

    except Exception as e:
        logger.error(f"Tool test failed: {e}")
        return TestToolResponse(
            success=False,
            error=f"Test failed: {str(e)}"
        )


@router.get("/", response_model=Dict[str, Any])
async def get_tools_info():
    """
    Get general information about the tools system.

    Returns overview of available tools and capabilities.
    """
    try:
        tool_registry = get_tool_registry()
        capabilities = tool_registry.list_all_capabilities()

        # Count total tools
        total_tools = 0
        capability_summary = {}

        for capability in capabilities:
            metadata = tool_registry.get_tool_metadata(capability)
            tool_count = len(metadata["tools"])
            total_tools += tool_count
            capability_summary[capability] = tool_count

        return {
            "total_capabilities": len(capabilities),
            "total_tools": total_tools,
            "capability_summary": capability_summary,
            "environment": os.getenv("ENVIRONMENT", "dev"),
            "status": "active"
        }

    except Exception as e:
        logger.error(f"Error getting tools info: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get tools information: {str(e)}"
        )


@router.delete("/cache")
async def clear_tool_cache(persona_id: Optional[str] = Query(None, description="Specific persona ID to clear")):
    """
    Clear tool cache for a persona or all personas.

    Args:
        persona_id: Optional specific persona to clear cache for

    Returns success status.
    """
    try:
        tool_registry = get_tool_registry()
        tool_registry.clear_cache(persona_id)

        if persona_id:
            message = f"Cleared tool cache for persona: {persona_id}"
        else:
            message = "Cleared all persona tool caches"

        logger.info(message)

        return {
            "success": True,
            "message": message
        }

    except Exception as e:
        logger.error(f"Error clearing tool cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear tool cache: {str(e)}"
        )
