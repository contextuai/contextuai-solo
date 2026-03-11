"""
Crew Service — Business logic for crew lifecycle management.

Handles creation, updates, validation, and run initiation.
Actual agent execution is delegated to the CrewOrchestrator (Task #23).
"""

import logging
from typing import Optional, Dict, Any, List, Tuple

from models.crew_models import (
    CreateCrewRequest,
    UpdateCrewRequest,
    RunCrewRequest,
    CrewStatus,
    CrewRunStatus,
    CrewAgentRole,
    ExecutionMode,
)
from repositories.crew_repository import CrewRepository, CrewRunRepository
from repositories.workspace_agent_repository import WorkspaceAgentRepository

logger = logging.getLogger(__name__)

MAX_CREWS_PER_USER = 50

# ----------------------------------------------------------------
# Workspace agent category → crew agent role mapping
# ----------------------------------------------------------------
CATEGORY_TO_ROLE: Dict[str, CrewAgentRole] = {
    "code_generation": CrewAgentRole.DEVELOPER,
    "engineering": CrewAgentRole.DEVELOPER,
    "devops": CrewAgentRole.DEVELOPER,
    "migration": CrewAgentRole.DEVELOPER,
    "code_quality": CrewAgentRole.REVIEWER,
    "documentation": CrewAgentRole.WRITER,
    "design": CrewAgentRole.DESIGNER,
    "data_analytics": CrewAgentRole.ANALYST,
    "product_management": CrewAgentRole.STRATEGIST,
    "c_suite": CrewAgentRole.COORDINATOR,
}


def map_category_to_role(category: str) -> Tuple[CrewAgentRole, Optional[str]]:
    """Map a workspace agent category to a crew agent role.

    Returns:
        Tuple of (role, custom_role).  custom_role is set only when role is CUSTOM.
    """
    role = CATEGORY_TO_ROLE.get(category)
    if role:
        return role, None
    # Fallback: CUSTOM with a readable label derived from the category
    label = category.replace("_", " ").title()
    return CrewAgentRole.CUSTOM, label


class CrewService:
    """Service layer for crew operations."""

    def __init__(
        self,
        crew_repo: CrewRepository,
        run_repo: CrewRunRepository,
        agent_repo: Optional[WorkspaceAgentRepository] = None,
    ):
        self.crew_repo = crew_repo
        self.run_repo = run_repo
        self.agent_repo = agent_repo

    # ------------------------------------------------------------------
    # Crew CRUD
    # ------------------------------------------------------------------

    async def create_crew(self, user_id: str, request: CreateCrewRequest) -> Dict[str, Any]:
        """Create a new crew configuration."""
        # Check crew limit
        existing, _ = await self.crew_repo.get_user_crews(user_id, limit=0)
        _, total = await self.crew_repo.get_user_crews(user_id, limit=1)
        if total >= MAX_CREWS_PER_USER:
            raise ValueError(f"Maximum of {MAX_CREWS_PER_USER} crews per user reached")

        # Check for duplicate name
        existing_crew = await self.crew_repo.get_by_name(user_id, request.name)
        if existing_crew:
            raise ValueError(f"A crew named '{request.name}' already exists")

        # Validate library_agent_id references exist (if any)
        if self.agent_repo:
            lib_ids = [
                a.library_agent_id
                for a in request.agents
                if a.library_agent_id
            ]
            if lib_ids:
                found = await self.agent_repo.get_by_ids(lib_ids)
                found_ids = {a.get("agent_id") for a in found}
                missing = set(lib_ids) - found_ids
                if missing:
                    raise ValueError(
                        f"Library agent(s) not found: {', '.join(missing)}"
                    )

        # Build crew document
        crew_data = request.model_dump(exclude_none=True)

        # Convert nested Pydantic models to dicts
        if "execution_config" in crew_data:
            crew_data["execution_config"] = request.execution_config.model_dump()
        if request.schedule:
            crew_data["schedule"] = request.schedule.model_dump()
        crew_data["agents"] = [a.model_dump() for a in request.agents]
        crew_data["distribution_channels"] = [d.model_dump() for d in request.distribution_channels]

        crew = await self.crew_repo.create_crew(user_id, crew_data)
        logger.info(f"Created crew '{request.name}' (crew_id={crew['crew_id']}) for user {user_id}")
        return crew

    async def get_crew(self, crew_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a crew by ID, verifying ownership."""
        crew = await self.crew_repo.get_by_crew_id(crew_id)
        if not crew:
            return None
        if crew["user_id"] != user_id:
            return None
        return crew

    async def list_crews(
        self,
        user_id: str,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List crews for a user with pagination."""
        offset = (page - 1) * page_size
        crews, total = await self.crew_repo.get_user_crews(
            user_id, status=status, limit=page_size, offset=offset
        )
        # Add agent_count for list items
        for crew in crews:
            crew["agent_count"] = len(crew.get("agents", []))
        return crews, total

    async def update_crew(
        self, crew_id: str, user_id: str, request: UpdateCrewRequest
    ) -> Optional[Dict[str, Any]]:
        """Update a crew, verifying ownership."""
        crew = await self.get_crew(crew_id, user_id)
        if not crew:
            return None

        update_data = request.model_dump(exclude_none=True)

        # Convert nested models
        if request.agents is not None:
            update_data["agents"] = [a.model_dump() for a in request.agents]
        if request.execution_config is not None:
            update_data["execution_config"] = request.execution_config.model_dump()
        if request.schedule is not None:
            update_data["schedule"] = request.schedule.model_dump()
        if request.distribution_channels is not None:
            update_data["distribution_channels"] = [d.model_dump() for d in request.distribution_channels]

        # Check duplicate name if changing
        if request.name and request.name != crew["name"]:
            existing = await self.crew_repo.get_by_name(user_id, request.name)
            if existing:
                raise ValueError(f"A crew named '{request.name}' already exists")

        updated = await self.crew_repo.update_crew(crew_id, update_data)
        if updated:
            logger.info(f"Updated crew {crew_id}")
        return updated

    async def delete_crew(self, crew_id: str, user_id: str) -> bool:
        """Soft-delete a crew, verifying ownership."""
        crew = await self.get_crew(crew_id, user_id)
        if not crew:
            return False
        deleted = await self.crew_repo.soft_delete_crew(crew_id)
        if deleted:
            logger.info(f"Soft-deleted crew {crew_id}")
        return deleted

    # ------------------------------------------------------------------
    # Crew Runs
    # ------------------------------------------------------------------

    async def start_run(
        self, crew_id: str, user_id: str, request: RunCrewRequest
    ) -> Dict[str, Any]:
        """
        Initiate a new crew execution run.

        Creates the run record with agent states. Actual execution
        will be handled by the CrewOrchestrator (Task #23) via Celery.
        """
        crew = await self.get_crew(crew_id, user_id)
        if not crew:
            raise ValueError("Crew not found or access denied")

        if crew["status"] != CrewStatus.ACTIVE.value:
            raise ValueError(f"Cannot run crew in '{crew['status']}' status")

        # Build agent states from crew config
        exec_config = crew.get("execution_config", {})
        mode = exec_config.get("mode", ExecutionMode.SEQUENTIAL.value)

        agent_states = []
        if mode == ExecutionMode.AUTONOMOUS.value:
            # Autonomous mode: single coordinator agent state
            agent_states.append({
                "agent_id": "coordinator",
                "name": "Coordinator",
                "role": "coordinator",
                "status": CrewRunStatus.PENDING.value,
                "started_at": None,
                "completed_at": None,
                "output": None,
                "error": None,
                "tokens_used": 0,
                "cost_usd": 0.0,
                "iteration": 0,
            })
        else:
            for agent_cfg in crew.get("agents", []):
                agent_states.append({
                    "agent_id": agent_cfg.get("agent_id"),
                    "name": agent_cfg.get("name"),
                    "role": agent_cfg.get("role", "custom"),
                    "status": CrewRunStatus.PENDING.value,
                    "started_at": None,
                    "completed_at": None,
                    "output": None,
                    "error": None,
                    "tokens_used": 0,
                    "cost_usd": 0.0,
                    "iteration": 0,
                })

        run_data = {
            "input": request.input,
            "input_data": request.input_data if request.input_data else None,
            "agents": agent_states,
        }

        run = await self.run_repo.create_run(crew_id, user_id, run_data)
        logger.info(f"Created run {run['run_id']} for crew {crew_id}")

        # Dispatch to Celery for async execution
        try:
            from tasks.crew_tasks import execute_crew_run
            execute_crew_run.delay(run["run_id"])
            logger.info(f"Dispatched crew run {run['run_id']} to Celery")
        except Exception as e:
            logger.warning(f"Failed to dispatch to Celery (will need manual execution): {e}")

        return run

    async def get_run(self, run_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a run by ID, verifying ownership."""
        run = await self.run_repo.get_by_run_id(run_id)
        if not run:
            return None
        if run["user_id"] != user_id:
            return None
        return run

    async def list_runs(
        self,
        crew_id: str,
        user_id: str,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List runs for a specific crew with pagination."""
        # Verify crew ownership
        crew = await self.get_crew(crew_id, user_id)
        if not crew:
            raise ValueError("Crew not found or access denied")

        offset = (page - 1) * page_size
        return await self.run_repo.get_crew_runs(
            crew_id, status=status, limit=page_size, offset=offset
        )

    async def cancel_run(self, run_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Cancel a pending or running crew run."""
        run = await self.get_run(run_id, user_id)
        if not run:
            return None

        if run["status"] not in (CrewRunStatus.PENDING.value, CrewRunStatus.RUNNING.value):
            raise ValueError(f"Cannot cancel run in '{run['status']}' status")

        updated = await self.run_repo.update_run(run_id, {
            "status": CrewRunStatus.CANCELLED.value,
        })
        if updated:
            logger.info(f"Cancelled run {run_id}")
        return updated
