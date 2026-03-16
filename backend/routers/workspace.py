"""
AI Team Workspace REST API Router
Provides endpoints for managing workspace projects, executions, agents, templates, and usage
"""

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import StreamingResponse
from typing import Optional, List
import logging
import uuid
import os
import json
import asyncio
from datetime import datetime

from database import get_database

from repositories import (
    WorkspaceProjectRepository,
    WorkspaceExecutionRepository,
    WorkspaceAgentRepository,
    WorkspaceTemplateRepository,
    WorkspaceCheckpointRepository,
    WorkspaceUsageRepository,
    WorkspaceJobRepository,
)

from models.workspace_enums import (
    ProjectStatus,
    AgentCategory,
    ComplexityLevel,
    CheckpointAction,
    ProjectType,
)

from models.workspace_models import (
    # Project models
    CreateProjectRequest,
    UpdateProjectRequest,
    ProjectResponse,
    ProjectListItem,
    ProjectListResponse,
    ProjectConfig,
    AgentSummary,
    # Execution models
    ExecutionResponse,
    AgentExecutionStep,
    SSEProgressEvent,
    # Checkpoint models
    CheckpointRequest,
    CheckpointResponse,
    # Agent models
    AgentBlueprint,
    AgentListResponse,
    # Custom agent models
    CreateCustomAgentRequest,
    UpdateCustomAgentRequest,
    CustomAgentPreview,
    CustomAgentResponse,
    # Template models
    CreateTemplateRequest,
    TemplateResponse,
    TeamTemplate,
    TemplateListResponse,
    # Usage models
    CostEstimateRequest,
    CostEstimateResponse,
    CostBreakdown,
    UsageResponse,
    # Workshop models
    WorkshopConfig,
    # Library models
    LibraryCatalogEntry,
    LibraryAgentDetail,
    LibraryImportRequest,
    LibraryBulkImportRequest,
    LibraryCatalogResponse,
    LibrarySyncResult,
    # Admin models
    AdminAgentUpdate,
    AdminAgentCreate,
    # Export models
    ExportRequest,
)

from services.workspace.agent_builder_service import build_agent_blueprint
from services.workspace.agent_library_service import AgentLibraryService
from services.workspace.document_service import DocumentGenerationService

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")


# =============================================================================
# Dependencies
# =============================================================================

async def get_user_id(request: Request) -> str:
    """
    Extract user_id from request headers or query params.
    In production, this would validate JWT tokens or session cookies.
    """
    # Try header first
    user_id = request.headers.get('x-user-id')

    # Try query param as fallback
    if not user_id:
        user_id = request.query_params.get('user_id')

    # For development, allow default user
    if not user_id:
        if ENVIRONMENT in ("dev", "development", "desktop"):
            user_id = "desktop-user" if ENVIRONMENT == "desktop" else "dev-user-123"
            logger.warning(f"No user_id provided, using default: {user_id}")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")

    return user_id


async def get_project_repository() -> WorkspaceProjectRepository:
    """Dependency to get WorkspaceProjectRepository instance"""
    db = await get_database()
    return WorkspaceProjectRepository(db)


async def get_execution_repository() -> WorkspaceExecutionRepository:
    """Dependency to get WorkspaceExecutionRepository instance"""
    db = await get_database()
    return WorkspaceExecutionRepository(db)


async def get_agent_repository() -> WorkspaceAgentRepository:
    """Dependency to get WorkspaceAgentRepository instance"""
    db = await get_database()
    return WorkspaceAgentRepository(db)


async def get_template_repository() -> WorkspaceTemplateRepository:
    """Dependency to get WorkspaceTemplateRepository instance"""
    db = await get_database()
    return WorkspaceTemplateRepository(db)


async def get_checkpoint_repository() -> WorkspaceCheckpointRepository:
    """Dependency to get WorkspaceCheckpointRepository instance"""
    db = await get_database()
    return WorkspaceCheckpointRepository(db)


async def get_usage_repository() -> WorkspaceUsageRepository:
    """Dependency to get WorkspaceUsageRepository instance"""
    db = await get_database()
    return WorkspaceUsageRepository(db)


async def get_job_repository() -> WorkspaceJobRepository:
    """Dependency to get WorkspaceJobRepository instance"""
    db = await get_database()
    return WorkspaceJobRepository(db)


# =============================================================================
# Helper Functions
# =============================================================================

def project_to_response(project_data: dict, agents: List[dict] = None) -> ProjectResponse:
    """Convert MongoDB project document to ProjectResponse model"""
    # Build team agents list
    team_agents = []
    if agents:
        for agent in agents:
            team_agents.append(AgentSummary(
                agent_id=agent.get("agent_id", ""),
                name=agent.get("name", "Unknown"),
                category=agent.get("category", AgentCategory.CODE_GENERATION),
                icon=agent.get("icon"),
                estimated_cost_usd=agent.get("estimated_cost_usd", 0.01),
                is_enabled=agent.get("is_active", True)
            ))

    # Parse config
    config_data = project_data.get("config", {})
    config = ProjectConfig(
        enable_checkpoints=config_data.get("enable_checkpoints", True),
        auto_create_pr=config_data.get("auto_create_pr", False),
        github_repo_url=config_data.get("github_repo_url"),
        generate_docs=config_data.get("generate_docs", True),
        generate_tests=config_data.get("generate_tests", True),
        output_format=config_data.get("output_format", "markdown")
    )

    name = project_data.get("name", project_data.get("title", ""))
    agent_ids = project_data.get("team_agent_ids", project_data.get("selected_agents", []))
    # Normalize status - map unknown values to 'draft'
    raw_status = project_data.get("status", "draft")
    valid_statuses = {s.value for s in ProjectStatus}
    status = raw_status if raw_status in valid_statuses else ProjectStatus.DRAFT.value

    # Parse workshop config if present
    ws_config_data = project_data.get("workshop_config")
    ws_config = None
    if ws_config_data and isinstance(ws_config_data, dict):
        ws_config = WorkshopConfig(**ws_config_data)

    return ProjectResponse(
        project_id=project_data.get("project_id", ""),
        name=name,
        title=project_data.get("title", name),
        description=project_data.get("description", ""),
        tech_stack=project_data.get("tech_stack", []),
        complexity=project_data.get("complexity", ComplexityLevel.MEDIUM),
        status=status,
        team_agents=team_agents,
        selected_agents=agent_ids,
        template_id=project_data.get("template_id"),
        config=config,
        project_type=project_data.get("project_type", ProjectType.BUILD),
        workshop_config=ws_config,
        user_id=project_data.get("user_id", ""),
        created_at=project_data.get("created_at", ""),
        updated_at=project_data.get("updated_at", ""),
        started_at=project_data.get("started_at"),
        completed_at=project_data.get("completed_at"),
        estimated_cost_usd=project_data.get("estimated_cost_usd", 0.0),
        actual_cost_usd=project_data.get("actual_cost_usd", 0.0),
        progress_percent=project_data.get("progress_percent", 0)
    )


def project_to_list_item(project_data: dict) -> ProjectListItem:
    """Convert MongoDB project document to ProjectListItem model"""
    agent_ids = project_data.get("team_agent_ids", project_data.get("selected_agents", []))
    name = project_data.get("name", project_data.get("title", ""))
    # Normalize status - map unknown values to 'draft'
    raw_status = project_data.get("status", "draft")
    valid_statuses = {s.value for s in ProjectStatus}
    status = raw_status if raw_status in valid_statuses else ProjectStatus.DRAFT.value
    return ProjectListItem(
        project_id=project_data.get("project_id", ""),
        name=name,
        title=project_data.get("title", name),
        description=project_data.get("description", ""),
        complexity=project_data.get("complexity", ComplexityLevel.MEDIUM),
        status=status,
        project_type=project_data.get("project_type", ProjectType.BUILD),
        team_agent_count=len(agent_ids),
        selected_agents=agent_ids,
        created_at=project_data.get("created_at", ""),
        updated_at=project_data.get("updated_at", ""),
        started_at=project_data.get("started_at"),
        completed_at=project_data.get("completed_at"),
        progress_percent=project_data.get("progress_percent", 0),
        estimated_cost_usd=project_data.get("estimated_cost_usd", 0.0),
        actual_cost_usd=project_data.get("actual_cost_usd", 0.0)
    )


def agent_to_blueprint(agent_data: dict) -> AgentBlueprint:
    """Convert MongoDB agent document to AgentBlueprint model"""
    return AgentBlueprint(
        agent_id=agent_data.get("agent_id", ""),
        name=agent_data.get("name", ""),
        description=agent_data.get("description", ""),
        category=agent_data.get("category", AgentCategory.CODE_GENERATION),
        icon=agent_data.get("icon"),
        capabilities=agent_data.get("capabilities", []),
        default_config=agent_data.get("config"),
        estimated_tokens=agent_data.get("estimated_tokens", 1000),
        estimated_cost_usd=agent_data.get("estimated_cost_usd", 0.01),
        is_system=agent_data.get("is_system", False),
        created_by=agent_data.get("created_by"),
        is_enabled=agent_data.get("is_active", True),
        source=agent_data.get("source"),
        created_at=agent_data.get("created_at"),
        updated_at=agent_data.get("updated_at")
    )


def template_to_response(template_data: dict, agents: List[dict] = None) -> TemplateResponse:
    """Convert MongoDB template document to TemplateResponse model"""
    agent_summaries = []
    if agents:
        for agent in agents:
            agent_summaries.append(AgentSummary(
                agent_id=agent.get("agent_id", ""),
                name=agent.get("name", "Unknown"),
                category=agent.get("category", AgentCategory.CODE_GENERATION),
                icon=agent.get("icon"),
                estimated_cost_usd=agent.get("estimated_cost_usd", 0.01),
                is_enabled=agent.get("is_active", True)
            ))

    return TemplateResponse(
        template_id=template_data.get("template_id", ""),
        name=template_data.get("name", ""),
        description=template_data.get("description", ""),
        icon=template_data.get("icon"),
        agents=agent_summaries,
        estimated_cost_usd=template_data.get("estimated_cost_usd", 0.0),
        estimated_time_minutes=template_data.get("estimated_time_minutes", 0),
        is_system=template_data.get("is_system", False),
        user_id=template_data.get("user_id"),
        usage_count=template_data.get("usage_count", 0),
        tags=template_data.get("tags", []),
        created_at=template_data.get("created_at"),
        updated_at=template_data.get("updated_at")
    )


# =============================================================================
# Project Endpoints
# =============================================================================

@router.post("/projects", status_code=201)
async def create_project(
    request_body: CreateProjectRequest,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository),
    template_repo: WorkspaceTemplateRepository = Depends(get_template_repository)
):
    """
    Create a new workspace project.

    **Request Body:**
    - name: Project name
    - description: Project description and requirements
    - tech_stack: List of technologies
    - complexity: Project complexity level
    - team_agent_ids: List of agent IDs for the team
    - template_id: Optional template ID to use as base
    - config: Project configuration options

    **Returns:**
    - Created project with full details
    """
    try:
        # Resolve frontend/backend field aliases
        project_name = request_body.resolved_name
        agent_ids = request_body.resolved_agent_ids
        tmpl_id = request_body.resolved_template_id

        logger.info(f"Creating project for user {user_id}: {project_name}")

        # If template_id provided, apply template defaults
        if tmpl_id:
            template = await template_repo.get_by_id(tmpl_id)
            if template:
                await template_repo.increment_usage_count(tmpl_id)

        # Validate agent IDs exist
        agents = []
        if agent_ids:
            agents = await agent_repo.get_by_ids(agent_ids)
            if len(agents) != len(agent_ids):
                found_ids = {a.get("agent_id") for a in agents}
                missing = [aid for aid in agent_ids if aid not in found_ids]
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid agent IDs: {missing}"
                )

        # Prepare config dict
        config_dict = None
        if request_body.config:
            config_dict = request_body.config.model_dump()

        # Prepare workshop config dict
        ws_config_dict = None
        if request_body.workshop_config:
            ws_config_dict = request_body.workshop_config.model_dump()

        # Validate model_id if provided
        model_id = None
        if request_body.model_id:
            from services.claude_models import validate_model_id
            model_id = validate_model_id(request_body.model_id)

        # Create project
        project = await project_repo.create(
            user_id=user_id,
            name=project_name,
            description=request_body.description,
            tech_stack=request_body.tech_stack,
            complexity=request_body.complexity.value,
            team_agent_ids=agent_ids,
            template_id=tmpl_id,
            config=config_dict,
            project_type=request_body.project_type.value if request_body.project_type else "build",
            workshop_config=ws_config_dict,
            model_id=model_id
        )

        logger.info(f"Project {project.get('project_id')} created successfully")

        return {"success": True, "project": project_to_response(project, agents)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    status: Optional[str] = Query(None, description="Filter by project status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository)
):
    """
    List user's workspace projects with optional filtering and pagination.

    **Query Parameters:**
    - status: Filter by project status
    - page: Page number (default: 1)
    - page_size: Items per page (1-100, default: 20)

    **Returns:**
    - List of projects with pagination metadata
    """
    try:
        logger.info(f"Listing projects for user {user_id}, status={status}, page={page}")

        offset = (page - 1) * page_size

        # Get projects
        projects_data = await project_repo.get_user_projects(
            user_id=user_id,
            status=status,
            limit=page_size,
            offset=offset
        )

        # Get total count
        total_count = await project_repo.count_by_user(user_id)

        # Convert to list items
        projects = [project_to_list_item(p) for p in projects_data]

        logger.info(f"Returning {len(projects)} projects (total: {total_count})")

        return ProjectListResponse(
            success=True,
            projects=projects,
            total_count=total_count,
            page=page,
            page_size=page_size,
            last_updated=datetime.utcnow().isoformat() + "Z"
        )

    except Exception as e:
        logger.error(f"Failed to list projects: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {str(e)}")


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Get detailed information about a specific project.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Returns:**
    - Complete project details including team agents
    """
    try:
        logger.info(f"Getting project {project_id} for user {user_id}")

        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Get team agents
        agents = []
        team_agent_ids = project_data.get("team_agent_ids", project_data.get("selected_agents", []))
        if team_agent_ids:
            agents = await agent_repo.get_by_ids(team_agent_ids)

        return {"success": True, "project": project_to_response(project_data, agents)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get project: {str(e)}")


@router.put("/projects/{project_id}")
async def update_project(
    project_id: str,
    request_body: UpdateProjectRequest,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Update an existing project.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Request Body:**
    - Any combination of: name, description, tech_stack, complexity, team_agent_ids, config, status

    **Returns:**
    - Updated project details
    """
    try:
        logger.info(f"Updating project {project_id} for user {user_id}")

        # Get current project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Build update data
        update_data = {}

        if request_body.name is not None:
            update_data["name"] = request_body.name
        if request_body.description is not None:
            update_data["description"] = request_body.description
        if request_body.tech_stack is not None:
            update_data["tech_stack"] = request_body.tech_stack
        if request_body.complexity is not None:
            update_data["complexity"] = request_body.complexity.value
        if request_body.team_agent_ids is not None:
            # Validate agent IDs
            if request_body.team_agent_ids:
                agents = await agent_repo.get_by_ids(request_body.team_agent_ids)
                if len(agents) != len(request_body.team_agent_ids):
                    raise HTTPException(status_code=400, detail="Invalid agent IDs provided")
            update_data["team_agent_ids"] = request_body.team_agent_ids
        if request_body.config is not None:
            update_data["config"] = request_body.config.model_dump()
        if request_body.status is not None:
            update_data["status"] = request_body.status.value

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Update project
        updated_project = await project_repo.update(project_id, update_data)

        if not updated_project:
            raise HTTPException(status_code=500, detail="Failed to update project")

        # Get team agents for response
        agents = []
        team_agent_ids = updated_project.get("team_agent_ids", [])
        if team_agent_ids:
            agents = await agent_repo.get_by_ids(team_agent_ids)

        logger.info(f"Project {project_id} updated successfully")

        return {"success": True, "project": project_to_response(updated_project, agents)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update project: {str(e)}")


@router.delete("/projects/{project_id}", status_code=200)
async def delete_project(
    project_id: str,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository)
):
    """
    Soft delete a project.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Returns:**
    - Success message
    """
    try:
        logger.info(f"Deleting project {project_id} for user {user_id}")

        # Get current project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Soft delete
        result = await project_repo.soft_delete(project_id)

        if not result:
            raise HTTPException(status_code=500, detail="Failed to delete project")

        logger.info(f"Project {project_id} deleted successfully")

        return {
            "success": True,
            "message": f"Project {project_id} deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")


# =============================================================================
# Execution Endpoints
# =============================================================================

@router.post("/projects/{project_id}/execute", status_code=201)
async def start_execution(
    project_id: str,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    execution_repo: WorkspaceExecutionRepository = Depends(get_execution_repository),
    job_repo: WorkspaceJobRepository = Depends(get_job_repository)
):
    """
    Start project execution.

    Creates a background job and returns the execution_id for tracking.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Returns:**
    - execution_id: ID to track execution progress
    - job_id: Background job ID
    """
    try:
        logger.info(f"Starting execution for project {project_id} by user {user_id}")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Check if project is in valid state
        current_status = project_data.get("status")
        if current_status in [ProjectStatus.RUNNING.value, ProjectStatus.QUEUED.value]:
            raise HTTPException(
                status_code=400,
                detail=f"Project is already {current_status}"
            )

        # Create execution record
        execution = await execution_repo.create(
            project_id=project_id,
            user_id=user_id
        )

        execution_id = execution.get("execution_id")

        # Create background job
        job = await job_repo.create_job(
            job_type="execute_project",
            payload={
                "project_id": project_id,
                "execution_id": execution_id,
                "user_id": user_id
            },
            priority=1
        )

        # Update project status
        await project_repo.update(project_id, {"status": ProjectStatus.QUEUED.value})
        await project_repo.increment_execution_count(project_id)

        # Desktop mode: execute via orchestrator directly (no Celery)
        try:
            import asyncio
            from database import get_database
            from services.workspace.orchestrator import WorkspaceOrchestrator

            async def _run_in_background():
                try:
                    db = await get_database()
                    orchestrator = WorkspaceOrchestrator(db)
                    await orchestrator.execute_project(project_id, execution_id, user_id)
                except Exception as exc:
                    logger.error(f"Background execution failed for project {project_id}: {exc}")

            asyncio.get_event_loop().create_task(_run_in_background())
            logger.info(f"Project {project_id} execution started (desktop mode)")
        except Exception as e:
            logger.error(f"Execution dispatch failed for project {project_id}: {e}")
            await project_repo.update(project_id, {"status": "failed", "error_message": str(e)})
            raise HTTPException(status_code=503, detail=f"Task dispatch failed: {str(e)}")

        logger.info(f"Execution {execution_id} created for project {project_id}")

        return {
            "success": True,
            "execution_id": execution_id,
            "job_id": job.get("job_id"),
            "status": "queued",
            "message": "Project execution started"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start execution for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start execution: {str(e)}")


@router.post("/projects/{project_id}/pause", status_code=200)
async def pause_execution(
    project_id: str,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    execution_repo: WorkspaceExecutionRepository = Depends(get_execution_repository)
):
    """
    Pause project execution.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Returns:**
    - Success message with updated status
    """
    try:
        logger.info(f"Pausing execution for project {project_id} by user {user_id}")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Check if project can be paused
        current_status = project_data.get("status")
        if current_status != ProjectStatus.RUNNING.value:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot pause project with status '{current_status}'"
            )

        # Update project status
        await project_repo.update(project_id, {"status": ProjectStatus.PAUSED.value})

        logger.info(f"Project {project_id} paused successfully")

        return {
            "success": True,
            "message": f"Project {project_id} paused",
            "status": ProjectStatus.PAUSED.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to pause execution: {str(e)}")


@router.post("/projects/{project_id}/resume", status_code=200)
async def resume_execution(
    project_id: str,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    job_repo: WorkspaceJobRepository = Depends(get_job_repository)
):
    """
    Resume paused project execution.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Returns:**
    - Success message with updated status
    """
    try:
        logger.info(f"Resuming execution for project {project_id} by user {user_id}")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Check if project can be resumed
        current_status = project_data.get("status")
        if current_status not in [ProjectStatus.PAUSED.value, ProjectStatus.CHECKPOINT.value]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot resume project with status '{current_status}'"
            )

        # Create resume job
        job = await job_repo.create_job(
            job_type="resume_project",
            payload={
                "project_id": project_id,
                "user_id": user_id
            },
            priority=1
        )

        # Update project status
        await project_repo.update(project_id, {"status": ProjectStatus.QUEUED.value})

        # Find the latest paused execution for this project
        resume_execution_id = None
        try:
            executions = await execution_repo.get_by_project(project_id)
            paused = [e for e in executions if e.get("status") in ("paused", "checkpoint")]
            if paused:
                resume_execution_id = paused[0].get("execution_id")
        except Exception:
            pass

        # Desktop mode: resume via orchestrator directly
        try:
            import asyncio
            from database import get_database
            from services.workspace.orchestrator import WorkspaceOrchestrator

            async def _resume_in_background():
                try:
                    db = await get_database()
                    orchestrator = WorkspaceOrchestrator(db)
                    await orchestrator.resume_project(project_id, resume_execution_id)
                except Exception as exc:
                    logger.error(f"Background resume failed for project {project_id}: {exc}")

            asyncio.get_event_loop().create_task(_resume_in_background())
            logger.info(f"Project {project_id} resume started (desktop mode)")
        except Exception as e:
            logger.error(f"Resume dispatch failed for project {project_id}: {e}")

        logger.info(f"Project {project_id} resume queued")

        return {
            "success": True,
            "message": f"Project {project_id} resume queued",
            "job_id": job.get("job_id"),
            "status": ProjectStatus.QUEUED.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to resume execution: {str(e)}")


@router.post("/projects/{project_id}/cancel", status_code=200)
async def cancel_execution(
    project_id: str,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    execution_repo: WorkspaceExecutionRepository = Depends(get_execution_repository)
):
    """
    Cancel project execution.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Returns:**
    - Success message with cancelled status
    """
    try:
        logger.info(f"Cancelling execution for project {project_id} by user {user_id}")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Check if project can be cancelled
        current_status = project_data.get("status")
        if current_status in [ProjectStatus.COMPLETED.value, ProjectStatus.FAILED.value, ProjectStatus.CANCELLED.value]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel project with status '{current_status}'"
            )

        # Update project status
        await project_repo.update(project_id, {"status": ProjectStatus.CANCELLED.value})

        # Get and cancel any running executions
        executions = await execution_repo.get_project_executions(project_id, limit=1)
        if executions:
            latest_execution = executions[0]
            if latest_execution.get("status") in ["pending", "running"]:
                await execution_repo.update_status(
                    latest_execution.get("execution_id"),
                    "cancelled",
                    "Cancelled by user"
                )

        logger.info(f"Project {project_id} cancelled successfully")

        return {
            "success": True,
            "message": f"Project {project_id} cancelled",
            "status": ProjectStatus.CANCELLED.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel execution: {str(e)}")


@router.get("/projects/{project_id}/stream")
async def stream_execution(
    project_id: str,
    execution_id: Optional[str] = Query(None, description="Specific execution ID to stream"),
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    execution_repo: WorkspaceExecutionRepository = Depends(get_execution_repository)
):
    """
    Stream execution progress via Server-Sent Events (SSE).

    **Path Parameters:**
    - project_id: Unique project identifier

    **Query Parameters:**
    - execution_id: Optional specific execution ID to stream

    **Returns:**
    - SSE stream with progress events
    """
    try:
        logger.info(f"Starting SSE stream for project {project_id}")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Get execution ID
        target_execution_id = execution_id
        if not target_execution_id:
            # Get latest execution
            executions = await execution_repo.get_project_executions(project_id, limit=1)
            if not executions:
                raise HTTPException(status_code=404, detail="No executions found for project")
            target_execution_id = executions[0].get("execution_id")

        async def event_generator():
            last_timestamp = None
            poll_count = 0
            max_polls = 3600  # 1 hour max at 1 second intervals

            while poll_count < max_polls:
                try:
                    # Get new events
                    if last_timestamp:
                        events = await execution_repo.get_events_after(target_execution_id, last_timestamp)
                    else:
                        # Get all events on first poll
                        execution = await execution_repo.get_by_id(target_execution_id)
                        events = execution.get("events", []) if execution else []

                    # Send events
                    for event in events:
                        event_data = {
                            "type": event.get("event_type", "update"),
                            "agent_id": event.get("agent_id"),
                            "agent_name": event.get("agent_name"),
                            "progress_percent": event.get("progress_percent", 0),
                            "message": event.get("message", ""),
                            "data": event.get("data"),
                            "cost_so_far_usd": event.get("cost_so_far_usd", 0.0),
                            "tokens_so_far": event.get("tokens_so_far", 0),
                            "timestamp": event.get("timestamp", datetime.utcnow().isoformat())
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                        last_timestamp = event.get("timestamp")

                    # Check if execution is complete
                    execution = await execution_repo.get_by_id(target_execution_id)
                    if execution:
                        status = execution.get("status")
                        if status in ["completed", "failed", "cancelled"]:
                            done_event = {
                                "type": "done",
                                "status": status,
                                "message": f"Execution {status}",
                                "timestamp": datetime.utcnow().isoformat()
                            }
                            yield f"data: {json.dumps(done_event)}\n\n"
                            break

                    await asyncio.sleep(1)
                    poll_count += 1

                except Exception as e:
                    error_event = {
                        "type": "error",
                        "message": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    yield f"data: {json.dumps(error_event)}\n\n"
                    break

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start SSE stream for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start stream: {str(e)}")


@router.get("/projects/{project_id}/execution/latest")
async def get_latest_execution(
    project_id: str,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    execution_repo: WorkspaceExecutionRepository = Depends(get_execution_repository)
):
    """
    Get the latest execution for a project, including workshop results and cost metrics.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Returns:**
    - Full execution document with context (workshop_result), metrics, and per-agent details
    """
    try:
        logger.info(f"Getting latest execution for project {project_id}")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Get the latest execution
        executions = await execution_repo.get_project_executions(
            project_id=project_id,
            limit=1
        )

        if not executions:
            raise HTTPException(status_code=404, detail="No executions found for this project")

        exec_data = executions[0]
        metrics = exec_data.get("metrics", {})

        # Build per-agent details from steps
        agents = []
        for step in exec_data.get("steps", []):
            agents.append({
                "agent_id": step.get("agent_id"),
                "agent_name": step.get("agent_name"),
                "status": step.get("status"),
                "tokens_used": step.get("tokens_used", 0),
                "cost_usd": step.get("cost_usd", 0.0),
                "started_at": step.get("started_at"),
                "completed_at": step.get("completed_at"),
                "output_summary": step.get("output_summary"),
            })

        execution_response = {
            "execution_id": exec_data.get("execution_id"),
            "project_id": exec_data.get("project_id"),
            "status": exec_data.get("status", "unknown"),
            "steps": exec_data.get("steps", []),
            "agents": agents,
            "current_agent_id": exec_data.get("current_agent_id"),
            "context": exec_data.get("context"),
            "result": exec_data.get("result"),
            "total_tokens": metrics.get("total_tokens", 0),
            "total_cost_usd": metrics.get("total_cost", 0.0),
            "progress_percent": exec_data.get("progress_percent", 100 if exec_data.get("status") == "completed" else 0),
            "started_at": exec_data.get("started_at", exec_data.get("created_at", "")),
            "completed_at": exec_data.get("completed_at"),
            "error_message": exec_data.get("error"),
        }

        return {
            "success": True,
            "execution": execution_response
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get latest execution for project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest execution: {str(e)}")


@router.get("/projects/{project_id}/executions")
async def get_execution_history(
    project_id: str,
    limit: int = Query(20, ge=1, le=100, description="Number of executions to return"),
    offset: int = Query(0, ge=0, description="Number of executions to skip"),
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    execution_repo: WorkspaceExecutionRepository = Depends(get_execution_repository)
):
    """
    Get execution history for a project.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Query Parameters:**
    - limit: Number of executions to return (1-100, default: 20)
    - offset: Number of executions to skip (default: 0)

    **Returns:**
    - List of execution summaries
    """
    try:
        logger.info(f"Getting execution history for project {project_id}")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Get executions
        executions = await execution_repo.get_project_executions(
            project_id=project_id,
            limit=limit,
            offset=offset
        )

        return {
            "success": True,
            "executions": executions,
            "count": len(executions),
            "limit": limit,
            "offset": offset
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get execution history: {str(e)}")


# =============================================================================
# Checkpoint Endpoints
# =============================================================================

@router.get("/projects/{project_id}/checkpoints")
async def list_checkpoints(
    project_id: str,
    status: Optional[str] = Query(None, description="Filter by checkpoint status"),
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    checkpoint_repo: WorkspaceCheckpointRepository = Depends(get_checkpoint_repository)
):
    """
    List checkpoints for a project.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Query Parameters:**
    - status: Filter by status (pending, resolved, expired, cancelled)

    **Returns:**
    - List of checkpoints
    """
    try:
        logger.info(f"Listing checkpoints for project {project_id}")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Get checkpoints
        checkpoints = await checkpoint_repo.get_project_checkpoints(
            project_id=project_id,
            status=status
        )

        return {
            "success": True,
            "checkpoints": checkpoints,
            "count": len(checkpoints)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list checkpoints: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list checkpoints: {str(e)}")


@router.post("/projects/{project_id}/checkpoints/{checkpoint_id}", status_code=200)
async def respond_to_checkpoint(
    project_id: str,
    checkpoint_id: str,
    request_body: CheckpointRequest,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
    checkpoint_repo: WorkspaceCheckpointRepository = Depends(get_checkpoint_repository),
    job_repo: WorkspaceJobRepository = Depends(get_job_repository)
):
    """
    Respond to a checkpoint.

    **Path Parameters:**
    - project_id: Unique project identifier
    - checkpoint_id: Checkpoint identifier

    **Request Body:**
    - checkpoint_id: Checkpoint ID (must match path)
    - action: Action to take (approve, reject, modify)
    - modifications: Optional modifications for modify action
    - feedback: Optional user feedback

    **Returns:**
    - Updated checkpoint status
    """
    try:
        logger.info(f"Responding to checkpoint {checkpoint_id} for project {project_id}")

        # Validate checkpoint_id matches
        if request_body.checkpoint_id != checkpoint_id:
            raise HTTPException(status_code=400, detail="Checkpoint ID mismatch")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Get checkpoint
        checkpoint = await checkpoint_repo.get_by_id(checkpoint_id)

        if not checkpoint:
            raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")

        if checkpoint.get("project_id") != project_id:
            raise HTTPException(status_code=400, detail="Checkpoint does not belong to this project")

        if checkpoint.get("status") != "pending":
            raise HTTPException(status_code=400, detail="Checkpoint is not pending")

        # Resolve checkpoint
        resolution = request_body.action.value
        updated_checkpoint = await checkpoint_repo.resolve(
            checkpoint_id=checkpoint_id,
            resolution=resolution,
            feedback=request_body.feedback,
            resolved_by=user_id
        )

        # Handle checkpoint resolution
        if request_body.action == CheckpointAction.APPROVE:
            # Find the execution for this checkpoint to get execution_id
            checkpoint_execution_id = checkpoint.get("execution_id")
            await project_repo.update(project_id, {"status": ProjectStatus.QUEUED.value})

            # Desktop mode: resume via orchestrator
            try:
                import asyncio
                from database import get_database
                from services.workspace.orchestrator import WorkspaceOrchestrator

                async def _checkpoint_resume():
                    try:
                        db = await get_database()
                        orchestrator = WorkspaceOrchestrator(db)
                        await orchestrator.resume_project(project_id, checkpoint_execution_id)
                    except Exception as exc:
                        logger.error(f"Checkpoint resume failed: {exc}")

                asyncio.get_event_loop().create_task(_checkpoint_resume())
                logger.info(f"Checkpoint approved, resume started for {project_id}")
            except Exception as e:
                logger.error(f"Resume dispatch failed for checkpoint: {e}")

        elif request_body.action == CheckpointAction.REJECT:
            await project_repo.update(project_id, {"status": ProjectStatus.CANCELLED.value})
            # Also cancel the execution
            checkpoint_execution_id = checkpoint.get("execution_id")
            if checkpoint_execution_id:
                await execution_repo.update_status(checkpoint_execution_id, "cancelled")

        elif request_body.action == CheckpointAction.MODIFY:
            # Store modifications and resume with modifications in context
            checkpoint_execution_id = checkpoint.get("execution_id")
            await project_repo.update(project_id, {"status": ProjectStatus.QUEUED.value})

            try:
                import asyncio
                from database import get_database
                from services.workspace.orchestrator import WorkspaceOrchestrator

                async def _checkpoint_modify_resume():
                    try:
                        db = await get_database()
                        orchestrator = WorkspaceOrchestrator(db)
                        await orchestrator.resume_project(project_id, checkpoint_execution_id)
                    except Exception as exc:
                        logger.error(f"Checkpoint modify resume failed: {exc}")

                asyncio.get_event_loop().create_task(_checkpoint_modify_resume())
            except Exception as e:
                logger.error(f"Resume dispatch failed for checkpoint modify: {e}")
                await job_repo.create_job(
                    job_type="reprocess_checkpoint",
                    payload={"project_id": project_id, "checkpoint_id": checkpoint_id,
                             "modifications": request_body.modifications, "user_id": user_id},
                    priority=1
                )

        logger.info(f"Checkpoint {checkpoint_id} resolved with action: {resolution}")

        return {
            "success": True,
            "message": f"Checkpoint {resolution}",
            "checkpoint": updated_checkpoint
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to respond to checkpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to respond to checkpoint: {str(e)}")


# =============================================================================
# Agent Endpoints
# =============================================================================

@router.get("/agents", response_model=AgentListResponse)
async def list_agents(
    category: Optional[str] = Query(None, description="Filter by agent category"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    List all available agents.

    **Query Parameters:**
    - category: Filter by agent category
    - page: Page number (default: 1)
    - page_size: Items per page (1-100, default: 20)

    **Returns:**
    - List of agents with pagination metadata
    """
    try:
        logger.info(f"Listing agents, category={category}")

        offset = (page - 1) * page_size

        # Get agents
        if category:
            agents_data = await agent_repo.get_by_category(
                category=category,
                skip=offset,
                limit=page_size
            )
        else:
            agents_data = await agent_repo.get_all_active()
            # Apply pagination manually for get_all_active
            agents_data = agents_data[offset:offset + page_size]

        # Get total count (approximate for pagination)
        all_active = await agent_repo.get_all_active()
        if category:
            total_count = len([a for a in all_active if a.get("category") == category])
        else:
            total_count = len(all_active)

        # Convert to models
        agents = [agent_to_blueprint(a) for a in agents_data]

        return AgentListResponse(
            success=True,
            agents=agents,
            total_count=total_count,
            page=page,
            page_size=page_size,
            last_updated=datetime.utcnow().isoformat() + "Z"
        )

    except Exception as e:
        logger.error(f"Failed to list agents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {str(e)}")


@router.get("/agents/custom")
async def list_custom_agents(
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    List the user's custom (non-system) agents.

    **Returns:**
    - List of custom agents created by the current user
    """
    try:
        logger.info(f"Listing custom agents for user {user_id}")

        agents_data = await agent_repo.get_custom_agents(user_id)
        agents = [agent_to_blueprint(a) for a in agents_data]

        return {
            "success": True,
            "agents": agents,
            "total_count": len(agents)
        }

    except Exception as e:
        logger.error(f"Failed to list custom agents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list custom agents: {str(e)}")


@router.get("/agents/admin")
async def list_admin_agents(
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    List all agents with admin metadata (source, edit history).
    Admin/powerUser only.
    """
    try:
        logger.info(f"Admin listing all agents for user {user_id}")
        all_agents = await agent_repo.get_all_active()
        agents = [agent_to_blueprint(a) for a in all_agents]
        return {"success": True, "agents": agents, "total_count": len(agents)}
    except Exception as e:
        logger.error(f"Failed to list admin agents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {str(e)}")


@router.post("/agents/admin", status_code=201)
async def create_admin_agent(
    request_body: AdminAgentCreate,
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Create a new agent directly (admin). No .md file backing.
    """
    try:
        logger.info(f"Admin creating agent '{request_body.name}' by user {user_id}")
        agent = await agent_repo.create(
            name=request_body.name,
            description=request_body.description,
            category=request_body.category,
            capabilities=request_body.capabilities,
            system_prompt=request_body.system_prompt,
            model_id="claude-sonnet",
            config={
                "icon": request_body.icon or "bot",
                "estimated_tokens": request_body.estimated_tokens or 2000,
                "estimated_cost_usd": request_body.estimated_cost_usd or 0.02,
            }
        )
        await agent_repo.update(agent.get("agent_id"), {
            "is_system": False,
            "created_by": user_id,
            "source": "admin_edit",
            "icon": request_body.icon or "bot",
            "estimated_tokens": request_body.estimated_tokens or 2000,
            "estimated_cost_usd": request_body.estimated_cost_usd or 0.02,
        })
        agent = await agent_repo.get_by_id(agent.get("agent_id"))
        return {"success": True, "agent": agent_to_blueprint(agent)}
    except Exception as e:
        logger.error(f"Failed to create admin agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")


@router.get("/agents/{agent_id}", response_model=AgentBlueprint)
async def get_agent(
    agent_id: str,
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Get detailed information about a specific agent.

    **Path Parameters:**
    - agent_id: Unique agent identifier

    **Returns:**
    - Complete agent details
    """
    try:
        logger.info(f"Getting agent {agent_id}")

        agent_data = await agent_repo.get_by_id(agent_id)

        if not agent_data:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        return agent_to_blueprint(agent_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get agent: {str(e)}")


# =============================================================================
# Custom Agent Endpoints
# =============================================================================

@router.post("/agents", status_code=201)
async def create_custom_agent(
    request_body: CreateCustomAgentRequest,
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Create a custom agent from a natural language description.

    Only admin and powerUser roles can create custom agents.
    Uses the agent builder service to generate a blueprint from the description.

    **Request Body:**
    - name: Agent display name
    - description: Natural language description of what the agent should do
    - category: Optional category (auto-detected if not provided)
    - capabilities: Optional capabilities (auto-extracted if not provided)

    **Returns:**
    - Created agent with full blueprint details
    """
    try:
        logger.info(f"Creating custom agent '{request_body.name}' for user {user_id}")

        # Generate blueprint from description
        blueprint = build_agent_blueprint(
            name=request_body.name,
            description=request_body.description,
            category=request_body.category,
            capabilities=request_body.capabilities,
        )

        # Save to database
        agent = await agent_repo.create(
            name=blueprint["name"],
            description=blueprint["description"],
            category=blueprint["category"],
            capabilities=blueprint["capabilities"],
            system_prompt=blueprint["system_prompt"],
            model_id=blueprint["model_id"],
            config={
                "icon": blueprint["icon"],
                "estimated_tokens": blueprint["estimated_tokens"],
                "estimated_cost_usd": blueprint["estimated_cost_usd"],
            }
        )

        # Add custom agent metadata
        await agent_repo.update(agent.get("agent_id"), {
            "is_system": False,
            "created_by": user_id,
            "icon": blueprint["icon"],
            "estimated_tokens": blueprint["estimated_tokens"],
            "estimated_cost_usd": blueprint["estimated_cost_usd"],
        })

        # Re-fetch to get updated document
        agent = await agent_repo.get_by_id(agent.get("agent_id"))

        logger.info(f"Custom agent '{request_body.name}' created: {agent.get('agent_id')}")

        return CustomAgentResponse(
            success=True,
            agent=agent_to_blueprint(agent)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create custom agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create custom agent: {str(e)}")


@router.post("/agents/preview")
async def preview_custom_agent(
    request_body: CreateCustomAgentRequest
):
    """
    Preview a generated agent blueprint without saving.

    Returns the blueprint that would be created so the user can review
    before confirming creation.

    **Request Body:**
    - name: Agent display name
    - description: Natural language description
    - category: Optional category
    - capabilities: Optional capabilities

    **Returns:**
    - Preview of the generated blueprint
    """
    try:
        logger.info(f"Previewing custom agent: {request_body.name}")

        blueprint = build_agent_blueprint(
            name=request_body.name,
            description=request_body.description,
            category=request_body.category,
            capabilities=request_body.capabilities,
        )

        return CustomAgentPreview(
            name=blueprint["name"],
            description=blueprint["description"],
            category=blueprint["category"],
            icon=blueprint["icon"],
            capabilities=blueprint["capabilities"],
            system_prompt=blueprint["system_prompt"],
            model_id=blueprint["model_id"],
            estimated_tokens=blueprint["estimated_tokens"],
            estimated_cost_usd=blueprint["estimated_cost_usd"],
        )

    except Exception as e:
        logger.error(f"Failed to preview custom agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to preview agent: {str(e)}")


@router.put("/agents/{agent_id}")
async def update_custom_agent(
    agent_id: str,
    request_body: UpdateCustomAgentRequest,
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Update a custom (non-system) agent.

    Only the agent creator can update their custom agents.
    System agents cannot be modified.

    **Path Parameters:**
    - agent_id: Unique agent identifier

    **Request Body:**
    - Any combination of: name, description, category, capabilities, is_active

    **Returns:**
    - Updated agent with full details
    """
    try:
        logger.info(f"Updating custom agent {agent_id} for user {user_id}")

        # Get current agent
        agent_data = await agent_repo.get_by_id(agent_id)

        if not agent_data:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Prevent modification of system agents
        if agent_data.get("is_system", True):
            raise HTTPException(status_code=403, detail="Cannot modify system agents")

        # Verify ownership
        if agent_data.get("created_by") != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this agent")

        # Build update data
        update_data = {}

        if request_body.name is not None:
            update_data["name"] = request_body.name
        if request_body.description is not None:
            update_data["description"] = request_body.description
            # Re-generate blueprint for updated description
            blueprint = build_agent_blueprint(
                name=request_body.name or agent_data.get("name", ""),
                description=request_body.description,
                category=request_body.category or agent_data.get("category"),
                capabilities=request_body.capabilities,
            )
            update_data["system_prompt"] = blueprint["system_prompt"]
            update_data["capabilities"] = blueprint["capabilities"]
            update_data["category"] = blueprint["category"]
            update_data["icon"] = blueprint["icon"]
        else:
            if request_body.category is not None:
                update_data["category"] = request_body.category
            if request_body.capabilities is not None:
                update_data["capabilities"] = request_body.capabilities
        if request_body.is_active is not None:
            update_data["is_active"] = request_body.is_active

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Update agent
        updated_agent = await agent_repo.update(agent_id, update_data)

        if not updated_agent:
            raise HTTPException(status_code=500, detail="Failed to update agent")

        logger.info(f"Custom agent {agent_id} updated successfully")

        return CustomAgentResponse(
            success=True,
            agent=agent_to_blueprint(updated_agent)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update custom agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update agent: {str(e)}")


@router.delete("/agents/{agent_id}", status_code=200)
async def delete_custom_agent(
    agent_id: str,
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Soft-delete a custom (non-system) agent.

    Only the agent creator can delete their custom agents.
    System agents cannot be deleted.

    **Path Parameters:**
    - agent_id: Unique agent identifier

    **Returns:**
    - Success message
    """
    try:
        logger.info(f"Deleting custom agent {agent_id} for user {user_id}")

        # Get current agent
        agent_data = await agent_repo.get_by_id(agent_id)

        if not agent_data:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        # Prevent deletion of system agents
        if agent_data.get("is_system", True):
            raise HTTPException(status_code=403, detail="Cannot delete system agents")

        # Verify ownership
        if agent_data.get("created_by") != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this agent")

        # Soft delete (deactivate)
        result = await agent_repo.deactivate(agent_id)

        if not result:
            raise HTTPException(status_code=500, detail="Failed to delete agent")

        logger.info(f"Custom agent {agent_id} deleted successfully")

        return {
            "success": True,
            "message": f"Agent {agent_id} deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete custom agent {agent_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete agent: {str(e)}")


# =============================================================================
# Template Endpoints
# =============================================================================

@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    user_id: str = Depends(get_user_id),
    template_repo: WorkspaceTemplateRepository = Depends(get_template_repository)
):
    """
    List all available templates (system + user's own).

    **Query Parameters:**
    - page: Page number (default: 1)
    - page_size: Items per page (1-100, default: 20)

    **Returns:**
    - List of templates with pagination metadata
    """
    try:
        logger.info(f"Listing templates for user {user_id}")

        offset = (page - 1) * page_size

        # Get all available templates
        templates_data = await template_repo.get_all_available(
            user_id=user_id,
            skip=offset,
            limit=page_size
        )

        # Convert to models
        templates = []
        for t in templates_data:
            t_agent_ids = t.get("team_agent_ids", [])
            templates.append(TeamTemplate(
                template_id=t.get("template_id", ""),
                name=t.get("name", ""),
                description=t.get("description", ""),
                icon=t.get("icon"),
                agent_ids=t_agent_ids,
                team_agent_ids=t_agent_ids,
                estimated_cost_usd=t.get("estimated_cost_usd", 0.0),
                estimated_time_minutes=t.get("estimated_time_minutes", 0),
                is_system=t.get("is_system", False),
                user_id=t.get("user_id"),
                usage_count=t.get("usage_count", 0),
                tags=t.get("tags", []),
                created_at=t.get("created_at"),
                updated_at=t.get("updated_at")
            ))

        # Estimate total count
        all_templates = await template_repo.get_all_available(user_id=user_id, limit=1000)
        total_count = len(all_templates)

        return TemplateListResponse(
            success=True,
            templates=templates,
            total_count=total_count,
            page=page,
            page_size=page_size,
            last_updated=datetime.utcnow().isoformat() + "Z"
        )

    except Exception as e:
        logger.error(f"Failed to list templates: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    user_id: str = Depends(get_user_id),
    template_repo: WorkspaceTemplateRepository = Depends(get_template_repository),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Get detailed information about a specific template.

    **Path Parameters:**
    - template_id: Unique template identifier

    **Returns:**
    - Complete template details with resolved agent information
    """
    try:
        logger.info(f"Getting template {template_id}")

        template_data = await template_repo.get_by_id(template_id)

        if not template_data:
            raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

        # Verify access (system templates accessible to all, user templates only to owner)
        if not template_data.get("is_system") and template_data.get("user_id") != user_id:
            if ENVIRONMENT != "dev":
                raise HTTPException(status_code=403, detail="Access denied to this template")

        # Get agents
        agents = []
        agent_ids = template_data.get("team_agent_ids", [])
        if agent_ids:
            agents = await agent_repo.get_by_ids(agent_ids)

        return template_to_response(template_data, agents)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get template {template_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    request_body: CreateTemplateRequest,
    user_id: str = Depends(get_user_id),
    template_repo: WorkspaceTemplateRepository = Depends(get_template_repository),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Create a new user template.

    **Request Body:**
    - name: Template name
    - description: Template description
    - icon: Optional icon identifier
    - agent_ids: List of agent IDs
    - tags: Optional list of tags

    **Returns:**
    - Created template with full details
    """
    try:
        logger.info(f"Creating template for user {user_id}: {request_body.name}")

        # Validate agent IDs
        agents = []
        if request_body.agent_ids:
            agents = await agent_repo.get_by_ids(request_body.agent_ids)
            if len(agents) != len(request_body.agent_ids):
                raise HTTPException(status_code=400, detail="Invalid agent IDs provided")

        # Calculate estimated cost
        estimated_cost = sum(a.get("estimated_cost_usd", 0.01) for a in agents)

        # Create template
        template = await template_repo.create(
            name=request_body.name,
            description=request_body.description,
            category="custom",
            tech_stack=[],
            complexity="medium",
            team_agent_ids=request_body.agent_ids,
            config={},
            user_id=user_id,
            is_system=False
        )

        # Update estimated cost
        await template_repo.update(template.get("template_id"), {
            "icon": request_body.icon,
            "tags": request_body.tags,
            "estimated_cost_usd": estimated_cost,
            "estimated_time_minutes": len(agents) * 5  # Rough estimate
        })

        # Get updated template
        updated_template = await template_repo.get_by_id(template.get("template_id"))

        logger.info(f"Template {template.get('template_id')} created successfully")

        return template_to_response(updated_template, agents)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create template: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create template: {str(e)}")


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    request_body: CreateTemplateRequest,
    user_id: str = Depends(get_user_id),
    template_repo: WorkspaceTemplateRepository = Depends(get_template_repository),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Update an existing template.

    **Path Parameters:**
    - template_id: Unique template identifier

    **Request Body:**
    - name: Template name
    - description: Template description
    - icon: Optional icon identifier
    - agent_ids: List of agent IDs
    - tags: Optional list of tags

    **Returns:**
    - Updated template details
    """
    try:
        logger.info(f"Updating template {template_id} for user {user_id}")

        # Get template
        template_data = await template_repo.get_by_id(template_id)

        if not template_data:
            raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

        # Verify ownership (can only update own templates)
        if template_data.get("is_system"):
            raise HTTPException(status_code=403, detail="Cannot modify system templates")

        if template_data.get("user_id") != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this template")

        # Validate agent IDs
        agents = []
        if request_body.agent_ids:
            agents = await agent_repo.get_by_ids(request_body.agent_ids)
            if len(agents) != len(request_body.agent_ids):
                raise HTTPException(status_code=400, detail="Invalid agent IDs provided")

        # Calculate estimated cost
        estimated_cost = sum(a.get("estimated_cost_usd", 0.01) for a in agents)

        # Update template
        update_data = {
            "name": request_body.name,
            "description": request_body.description,
            "icon": request_body.icon,
            "team_agent_ids": request_body.agent_ids,
            "tags": request_body.tags,
            "estimated_cost_usd": estimated_cost,
            "estimated_time_minutes": len(agents) * 5
        }

        updated_template = await template_repo.update(template_id, update_data)

        if not updated_template:
            raise HTTPException(status_code=500, detail="Failed to update template")

        logger.info(f"Template {template_id} updated successfully")

        return template_to_response(updated_template, agents)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update template {template_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")


@router.delete("/templates/{template_id}", status_code=200)
async def delete_template(
    template_id: str,
    user_id: str = Depends(get_user_id),
    template_repo: WorkspaceTemplateRepository = Depends(get_template_repository)
):
    """
    Delete a template.

    **Path Parameters:**
    - template_id: Unique template identifier

    **Returns:**
    - Success message
    """
    try:
        logger.info(f"Deleting template {template_id} for user {user_id}")

        # Get template
        template_data = await template_repo.get_by_id(template_id)

        if not template_data:
            raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

        # Verify ownership
        if template_data.get("is_system"):
            raise HTTPException(status_code=403, detail="Cannot delete system templates")

        if template_data.get("user_id") != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this template")

        # Delete template
        result = await template_repo.delete(template_id)

        if not result:
            raise HTTPException(status_code=500, detail="Failed to delete template")

        logger.info(f"Template {template_id} deleted successfully")

        return {
            "success": True,
            "message": f"Template {template_id} deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete template {template_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}")


# =============================================================================
# Artifact Endpoints
# =============================================================================

@router.get("/projects/{project_id}/artifacts")
async def list_artifacts(
    project_id: str,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository)
):
    """
    List artifacts for a project.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Returns:**
    - List of artifacts (placeholder implementation)
    """
    try:
        logger.info(f"Listing artifacts for project {project_id}")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        from services.workspace.artifact_service import artifact_service

        files = await artifact_service.list_files(project_id)
        return {
            "success": True,
            "artifacts": files,
            "count": len(files)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list artifacts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list artifacts: {str(e)}")


@router.post("/projects/{project_id}/artifacts/download")
async def download_artifacts(
    project_id: str,
    artifact_ids: Optional[List[str]] = None,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository)
):
    """
    Download project artifacts as ZIP.

    **Path Parameters:**
    - project_id: Unique project identifier

    **Request Body:**
    - artifact_ids: Optional list of specific artifact IDs to download

    **Returns:**
    - Download URL (placeholder implementation)
    """
    try:
        logger.info(f"Generating download for project {project_id} artifacts")

        # Get project
        project_data = await project_repo.get_by_id(project_id)

        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        # Validate user access
        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        from fastapi.responses import FileResponse
        from services.workspace.artifact_service import artifact_service

        zip_result = await artifact_service.create_zip(project_id)
        if not zip_result.get("success"):
            raise HTTPException(status_code=404, detail=zip_result.get("error", "No artifacts found"))
        return FileResponse(
            zip_result["path"],
            filename=zip_result["filename"],
            media_type="application/zip"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate artifact download: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate download: {str(e)}")


@router.get("/projects/{project_id}/artifacts/{filename:path}")
async def get_artifact_content(
    project_id: str,
    filename: str,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository),
):
    """Get individual artifact file content."""
    try:
        project_data = await project_repo.get_by_id(project_id)
        if not project_data:
            raise HTTPException(status_code=404, detail="Project not found")

        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        from services.workspace.artifact_service import artifact_service

        result = await artifact_service.read_file(project_id, filename)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "File not found"))

        return {
            "success": True,
            "content": result["content"],
            "filename": filename,
            "size": result.get("size", len(result.get("content", "")))
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get artifact content: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get artifact: {str(e)}")


# =============================================================================
# Usage Endpoints
# =============================================================================

@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    user_id: str = Depends(get_user_id),
    usage_repo: WorkspaceUsageRepository = Depends(get_usage_repository)
):
    """
    Get user's usage statistics.

    **Returns:**
    - Usage stats including credits, costs, and execution counts
    """
    try:
        logger.info(f"Getting usage for user {user_id}")

        month = datetime.utcnow().strftime("%Y-%m")
        usage = await usage_repo.get_user_usage(user_id, month)

        if not usage:
            # Initialize usage if not exists
            usage = await usage_repo.initialize_usage(
                user_id=user_id,
                plan_type="free",
                credits_allocated=100  # Default free tier credits
            )

        # Calculate remaining credits
        credits_allocated = usage.get("credits_allocated", 0)
        credits_used = usage.get("credits_used", 0)
        credits_remaining = max(0, credits_allocated - credits_used)

        # Get usage history for this period
        usage_this_period = {
            "projects_created": 0,  # Would query projects collection
            "agents_invoked": 0,     # Would aggregate from executions
            "tokens_used": 0         # Would aggregate from executions
        }

        return UsageResponse(
            user_id=user_id,
            credits_allocated=credits_allocated,
            credits_used=credits_used,
            credits_remaining=credits_remaining,
            execution_count=usage.get("execution_count", 0),
            total_cost_usd=usage.get("total_cost", 0.0),
            total_tokens_used=0,  # Would aggregate from executions
            plan_type=usage.get("plan_type", "free"),
            reset_date=f"{month}-01T00:00:00Z",
            usage_this_period=usage_this_period
        )

    except Exception as e:
        logger.error(f"Failed to get usage: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get usage: {str(e)}")


@router.post("/seed", status_code=200)
async def seed_workspace_data():
    """
    Seed or re-seed workspace data (agents, templates, sample projects).
    Only available in dev environment.
    """
    if ENVIRONMENT not in ("dev", "development", "desktop"):
        raise HTTPException(status_code=403, detail="Seeding only available in dev environment")

    try:
        from services.workspace.seed_data import seed_all
        db = await get_database()
        result = await seed_all(db)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Failed to seed workspace data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to seed: {str(e)}")


@router.post("/usage/cost-estimate", response_model=CostEstimateResponse)
async def estimate_cost(
    request_body: CostEstimateRequest,
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository),
    usage_repo: WorkspaceUsageRepository = Depends(get_usage_repository)
):
    """
    Estimate cost for a project configuration.

    **Request Body:**
    - agent_ids: List of agent IDs
    - complexity: Project complexity level
    - include_documentation: Include docs generation in estimate
    - include_tests: Include test generation in estimate

    **Returns:**
    - Cost estimate with breakdown
    """
    try:
        logger.info(f"Estimating cost for user {user_id}")

        # Get agents
        agents = await agent_repo.get_by_ids(request_body.agent_ids)

        if len(agents) != len(request_body.agent_ids):
            found_ids = {a.get("agent_id") for a in agents}
            missing = [aid for aid in request_body.agent_ids if aid not in found_ids]
            raise HTTPException(status_code=400, detail=f"Invalid agent IDs: {missing}")

        # Complexity multiplier
        complexity_multipliers = {
            ComplexityLevel.SIMPLE: 0.5,
            ComplexityLevel.MEDIUM: 1.0,
            ComplexityLevel.COMPLEX: 2.0,
            ComplexityLevel.ENTERPRISE: 4.0
        }
        multiplier = complexity_multipliers.get(request_body.complexity, 1.0)

        # Calculate costs
        cost_breakdown = []
        total_cost = 0.0
        total_tokens = 0

        for agent in agents:
            base_cost = agent.get("estimated_cost_usd", 0.01)
            base_tokens = agent.get("estimated_tokens", 1000)

            adjusted_cost = base_cost * multiplier
            adjusted_tokens = int(base_tokens * multiplier)

            cost_breakdown.append(CostBreakdown(
                agent_id=agent.get("agent_id", ""),
                agent_name=agent.get("name", "Unknown"),
                estimated_tokens=adjusted_tokens,
                estimated_cost_usd=round(adjusted_cost, 4)
            ))

            total_cost += adjusted_cost
            total_tokens += adjusted_tokens

        # Add documentation cost if enabled
        if request_body.include_documentation:
            doc_cost = 0.02 * multiplier
            doc_tokens = int(2000 * multiplier)
            cost_breakdown.append(CostBreakdown(
                agent_id="docs-generation",
                agent_name="Documentation Generation",
                estimated_tokens=doc_tokens,
                estimated_cost_usd=round(doc_cost, 4)
            ))
            total_cost += doc_cost
            total_tokens += doc_tokens

        # Add test generation cost if enabled
        if request_body.include_tests:
            test_cost = 0.03 * multiplier
            test_tokens = int(3000 * multiplier)
            cost_breakdown.append(CostBreakdown(
                agent_id="test-generation",
                agent_name="Test Generation",
                estimated_tokens=test_tokens,
                estimated_cost_usd=round(test_cost, 4)
            ))
            total_cost += test_cost
            total_tokens += test_tokens

        # Get user's remaining credits
        remaining_credits = await usage_repo.get_remaining_credits(user_id)

        # Convert cost to credits (1 credit = $0.01)
        credits_required = int(total_cost * 100)

        # Estimate time (5 minutes per agent, adjusted for complexity)
        estimated_time = int(len(agents) * 5 * multiplier)

        return CostEstimateResponse(
            estimated_cost_usd=round(total_cost, 4),
            cost_breakdown=cost_breakdown,
            estimated_time_minutes=estimated_time,
            estimated_tokens=total_tokens,
            credits_required=credits_required,
            user_credits_remaining=remaining_credits,
            can_execute=remaining_credits >= credits_required,
            complexity_multiplier=multiplier
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to estimate cost: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to estimate cost: {str(e)}")


# =============================================================================
# Library Catalog Endpoints
# =============================================================================

@router.get("/library")
async def get_library_catalog(
    category: Optional[str] = Query(None, description="Filter by category folder name"),
):
    """
    Browse the agent library catalog (reads .md files).

    **Query Parameters:**
    - category: Optional category filter (e.g. 'c-suite', 'startup-venture')

    **Returns:**
    - List of catalog entries with agent metadata
    """
    try:
        logger.info(f"Getting library catalog, category={category}")
        library = AgentLibraryService()
        catalog = await library.get_catalog(category=category)
        return {
            "success": True,
            "agents": catalog["agents"],
            "total_count": catalog["total_count"],
            "categories": catalog["categories"]
        }
    except Exception as e:
        logger.error(f"Failed to get library catalog: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get catalog: {str(e)}")


@router.get("/library/search")
async def search_library(
    q: str = Query(..., min_length=1, description="Search query"),
):
    """
    Search the agent library catalog.

    **Query Parameters:**
    - q: Search query string

    **Returns:**
    - Matching catalog entries
    """
    try:
        logger.info(f"Searching library for: {q}")
        library = AgentLibraryService()
        results = await library.search_catalog(q)
        return {
            "success": True,
            "agents": results["agents"],
            "total_count": results["total_count"],
            "query": q
        }
    except Exception as e:
        logger.error(f"Failed to search library: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to search: {str(e)}")


@router.post("/library/import")
async def import_library_agent(
    request_body: LibraryImportRequest,
    user_id: str = Depends(get_user_id),
):
    """
    Import a single agent from the library into MongoDB.

    **Request Body:**
    - category: Category folder name
    - slug: Agent slug

    **Returns:**
    - Imported agent blueprint
    """
    try:
        logger.info(f"Importing library agent {request_body.category}/{request_body.slug}")
        agent_repo = WorkspaceAgentRepository(await get_database())
        library = AgentLibraryService()
        agent = await library.import_agent(
            category=request_body.category,
            slug=request_body.slug,
            user_id=user_id,
            agent_repo=agent_repo
        )
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found in library")
        return {"success": True, "agent": agent}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import library agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to import agent: {str(e)}")


@router.post("/library/import/bulk")
async def import_library_agents_bulk(
    request_body: LibraryBulkImportRequest,
    user_id: str = Depends(get_user_id),
):
    """
    Bulk import multiple agents from the library.

    **Request Body:**
    - imports: List of {category, slug} pairs

    **Returns:**
    - List of imported agent blueprints
    """
    try:
        logger.info(f"Bulk importing {len(request_body.imports)} library agents")
        agent_repo = WorkspaceAgentRepository(await get_database())
        library = AgentLibraryService()
        agents = await library.import_bulk(
            imports=[imp.model_dump() for imp in request_body.imports],
            user_id=user_id,
            agent_repo=agent_repo
        )
        return {"success": True, "agents": agents, "imported_count": len(agents)}
    except Exception as e:
        logger.error(f"Failed to bulk import: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to bulk import: {str(e)}")


@router.post("/library/sync")
async def sync_library(
    user_id: str = Depends(get_user_id),
):
    """
    Re-sync all .md files from the agent library to MongoDB.
    Admin only - re-reads all .md files and upserts to workspace_agents.

    **Returns:**
    - Sync result with created/updated/skipped counts
    """
    try:
        logger.info(f"Syncing agent library to DB by user {user_id}")
        agent_repo = WorkspaceAgentRepository(await get_database())
        library = AgentLibraryService()
        result = await library.sync_library_to_db(agent_repo)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Failed to sync library: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to sync library: {str(e)}")


@router.get("/library/{category}/{slug}")
async def get_library_agent_detail(
    category: str,
    slug: str,
):
    """
    Get full detail for a specific library agent (.md content).

    **Path Parameters:**
    - category: Category folder name (e.g. 'c-suite')
    - slug: Agent slug (e.g. 'ceo')

    **Returns:**
    - Full agent detail with parsed sections
    """
    try:
        logger.info(f"Getting library agent detail: {category}/{slug}")
        library = AgentLibraryService()
        detail = await library.get_agent_detail(category, slug)
        if not detail:
            raise HTTPException(status_code=404, detail=f"Agent {category}/{slug} not found")
        return {"success": True, "agent": detail}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get library agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get agent: {str(e)}")


# =============================================================================
# Agent Admin Endpoints (update/delete/reset)
# =============================================================================

@router.put("/agents/{agent_id}/admin")
async def update_admin_agent(
    agent_id: str,
    request_body: AdminAgentUpdate,
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Admin edit of any agent (name, description, system_prompt, etc.).
    Sets source to 'admin_edit'.
    """
    try:
        logger.info(f"Admin updating agent {agent_id} by user {user_id}")
        agent_data = await agent_repo.get_by_id(agent_id)
        if not agent_data:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        update_data = {"source": "admin_edit"}
        if request_body.name is not None:
            update_data["name"] = request_body.name
        if request_body.description is not None:
            update_data["description"] = request_body.description
        if request_body.system_prompt is not None:
            update_data["system_prompt"] = request_body.system_prompt
        if request_body.category is not None:
            update_data["category"] = request_body.category
        if request_body.capabilities is not None:
            update_data["capabilities"] = request_body.capabilities
        if request_body.icon is not None:
            update_data["icon"] = request_body.icon
        if request_body.estimated_tokens is not None:
            update_data["estimated_tokens"] = request_body.estimated_tokens
        if request_body.estimated_cost_usd is not None:
            update_data["estimated_cost_usd"] = request_body.estimated_cost_usd
        if request_body.is_active is not None:
            update_data["is_active"] = request_body.is_active

        updated = await agent_repo.update(agent_id, update_data)
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update agent")

        return {"success": True, "agent": agent_to_blueprint(updated)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to admin update agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update agent: {str(e)}")


@router.delete("/agents/{agent_id}/admin")
async def delete_admin_agent(
    agent_id: str,
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Admin deactivate an agent.
    """
    try:
        logger.info(f"Admin deactivating agent {agent_id} by user {user_id}")
        agent_data = await agent_repo.get_by_id(agent_id)
        if not agent_data:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        result = await agent_repo.deactivate(agent_id)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to deactivate agent")

        return {"success": True, "message": f"Agent {agent_id} deactivated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to admin delete agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to deactivate agent: {str(e)}")


@router.post("/agents/{agent_id}/admin/reset")
async def reset_agent_to_library(
    agent_id: str,
    user_id: str = Depends(get_user_id),
    agent_repo: WorkspaceAgentRepository = Depends(get_agent_repository)
):
    """
    Reset an agent to its original library version (re-read from .md file).
    Only works for agents with source='library' or 'admin_edit'.
    """
    try:
        logger.info(f"Resetting agent {agent_id} to library version by user {user_id}")
        agent_data = await agent_repo.get_by_id(agent_id)
        if not agent_data:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        source = agent_data.get("source", "")
        if source not in ("library", "admin_edit"):
            raise HTTPException(
                status_code=400,
                detail="Can only reset library-sourced agents"
            )

        # Re-import from library
        library = AgentLibraryService()
        # Try to find the agent in the library by agent_id
        catalog = await library.get_catalog()
        matching = [a for a in catalog["agents"] if a.get("slug") == agent_id]
        if not matching:
            raise HTTPException(status_code=404, detail="Agent not found in library catalog")

        entry = matching[0]
        imported = await library.import_agent(
            category=entry["category"],
            slug=entry["slug"],
            user_id=user_id,
            agent_repo=agent_repo
        )
        if not imported:
            raise HTTPException(status_code=500, detail="Failed to re-import from library")

        return {"success": True, "agent": imported, "message": "Agent reset to library version"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset agent: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset agent: {str(e)}")


# =============================================================================
# Export Endpoints
# =============================================================================

@router.post("/projects/{project_id}/export")
async def export_project(
    project_id: str,
    request_body: ExportRequest,
    user_id: str = Depends(get_user_id),
    project_repo: WorkspaceProjectRepository = Depends(get_project_repository)
):
    """
    Export project output as PDF, PPTX, or HTML.

    **Path Parameters:**
    - project_id: Project identifier

    **Request Body:**
    - format: 'pdf', 'pptx', or 'html'
    - template: 'report', 'brief', or 'slides'

    **Returns:**
    - Binary file download
    """
    try:
        logger.info(f"Exporting project {project_id} as {request_body.format}")

        project_data = await project_repo.get_by_id(project_id)
        if not project_data:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        if project_data.get('user_id') != user_id and ENVIRONMENT != "dev":
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Read the compiled output from artifacts
        from services.workspace.artifact_service import artifact_service
        files = await artifact_service.list_files(project_id)
        if not files:
            raise HTTPException(status_code=404, detail="No artifacts found for export")

        # Find the workshop output markdown file
        md_file = None
        for f in files:
            if f["filename"].endswith(".md"):
                md_file = f["filename"]
                break

        if not md_file:
            raise HTTPException(status_code=404, detail="No markdown output found for export")

        file_result = await artifact_service.read_file(project_id, md_file)
        if not file_result.get("success"):
            raise HTTPException(status_code=500, detail="Failed to read output file")

        content = file_result["content"]
        project_name = project_data.get("name", "Export")
        doc_service = DocumentGenerationService()

        if request_body.format == "pdf":
            output_bytes = doc_service.markdown_to_pdf(
                content=content,
                template=request_body.template,
                title=project_name,
            )
            media_type = "application/pdf"
            filename = f"{project_name.replace(' ', '_')}.pdf"
        elif request_body.format == "pptx":
            output_bytes = doc_service.markdown_to_pptx(
                content=content,
                template=request_body.template,
                title=project_name,
            )
            media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            filename = f"{project_name.replace(' ', '_')}.pptx"
        elif request_body.format == "html":
            output_bytes = doc_service.markdown_to_html(
                content=content,
                template=request_body.template,
                title=project_name,
            )
            media_type = "text/html"
            filename = f"{project_name.replace(' ', '_')}.html"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {request_body.format}")

        from fastapi.responses import Response
        return Response(
            content=output_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to export: {str(e)}")
