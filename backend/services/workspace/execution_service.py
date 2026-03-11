"""
Execution Service for AI Team Workspace Feature

Provides business logic for managing workspace project executions,
including starting, pausing, resuming, and cancelling executions.
"""

import logging
from typing import Dict, Any, Optional

from repositories.workspace_project_repository import WorkspaceProjectRepository
from repositories.workspace_execution_repository import WorkspaceExecutionRepository
from repositories.workspace_job_repository import WorkspaceJobRepository

# Configure logging
logger = logging.getLogger(__name__)


class ExecutionService:
    """
    Service for workspace execution management.

    Provides methods for controlling project executions through their lifecycle:
    start, pause, resume, cancel, and status checks.
    """

    # Valid execution statuses
    VALID_STATUSES = ["pending", "running", "paused", "completed", "failed", "cancelled"]

    # Job type for workspace executions
    JOB_TYPE = "execute_workspace_project"

    async def start_execution(
        self,
        project_id: str,
        user_id: str,
        project_repo: WorkspaceProjectRepository,
        execution_repo: WorkspaceExecutionRepository,
        job_repo: WorkspaceJobRepository
    ) -> Dict[str, Any]:
        """
        Start a new execution for a workspace project.

        Creates an execution record and queues a background job for processing.

        Args:
            project_id: ID of the project to execute
            user_id: ID of the user initiating the execution
            project_repo: WorkspaceProjectRepository instance
            execution_repo: WorkspaceExecutionRepository instance
            job_repo: WorkspaceJobRepository instance

        Returns:
            Dictionary with 'success' boolean, 'execution' data or 'error'
        """
        try:
            logger.info(f"Starting execution for project {project_id} by user {user_id}")

            # Verify project exists and belongs to user
            project = await project_repo.get_by_id(project_id)
            if not project:
                logger.warning(f"Project not found: {project_id}")
                return {
                    "success": False,
                    "error": "Project not found"
                }

            if project.get("user_id") != user_id:
                logger.warning(f"User {user_id} not authorized for project {project_id}")
                return {
                    "success": False,
                    "error": "Not authorized to execute this project"
                }

            # Check project status
            if project.get("status") not in ["active", "paused"]:
                logger.warning(f"Project {project_id} has invalid status: {project.get('status')}")
                return {
                    "success": False,
                    "error": f"Cannot execute project with status '{project.get('status')}'"
                }

            # Create execution record
            execution = await execution_repo.create(
                project_id=project_id,
                user_id=user_id
            )

            if not execution:
                logger.error(f"Failed to create execution for project {project_id}")
                return {
                    "success": False,
                    "error": "Failed to create execution record"
                }

            execution_id = execution.get("execution_id")
            logger.info(f"Created execution {execution_id} for project {project_id}")

            # Queue background job
            job_payload = {
                "execution_id": execution_id,
                "project_id": project_id,
                "user_id": user_id,
                "team_agent_ids": project.get("team_agent_ids", []),
                "project_config": project.get("config", {})
            }

            job = await job_repo.create_job(
                job_type=self.JOB_TYPE,
                payload=job_payload,
                priority=1,  # Normal priority
                max_retries=2  # Allow 2 retries for workspace executions
            )

            if not job:
                # Rollback execution
                await execution_repo.update_status(execution_id, "failed", "Failed to queue job")
                logger.error(f"Failed to queue job for execution {execution_id}")
                return {
                    "success": False,
                    "error": "Failed to queue execution job"
                }

            job_id = job.get("job_id")
            logger.info(f"Queued job {job_id} for execution {execution_id}")

            # Update project execution count
            await project_repo.increment_execution_count(project_id)

            return {
                "success": True,
                "execution": execution,
                "job_id": job_id
            }

        except Exception as e:
            logger.error(f"Error starting execution: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def pause_execution(
        self,
        execution_id: str,
        execution_repo: WorkspaceExecutionRepository,
        job_repo: WorkspaceJobRepository
    ) -> Dict[str, Any]:
        """
        Pause a running execution.

        Sets the execution status to 'paused' and marks the job for pause.

        Args:
            execution_id: ID of the execution to pause
            execution_repo: WorkspaceExecutionRepository instance
            job_repo: WorkspaceJobRepository instance

        Returns:
            Dictionary with 'success' boolean and result or 'error'
        """
        try:
            logger.info(f"Pausing execution {execution_id}")

            # Get execution
            execution = await execution_repo.get_by_id(execution_id)
            if not execution:
                logger.warning(f"Execution not found: {execution_id}")
                return {
                    "success": False,
                    "error": "Execution not found"
                }

            # Check if execution can be paused
            current_status = execution.get("status")
            if current_status != "running":
                logger.warning(f"Cannot pause execution with status '{current_status}'")
                return {
                    "success": False,
                    "error": f"Cannot pause execution with status '{current_status}'"
                }

            # Update execution status
            updated = await execution_repo.update_status(execution_id, "paused")
            if not updated:
                logger.error(f"Failed to update execution status to paused")
                return {
                    "success": False,
                    "error": "Failed to update execution status"
                }

            # Add pause event
            await execution_repo.add_event(
                execution_id=execution_id,
                event_type="execution_paused",
                event_data={"reason": "User requested pause"}
            )

            logger.info(f"Execution {execution_id} paused successfully")

            return {
                "success": True,
                "execution": updated
            }

        except Exception as e:
            logger.error(f"Error pausing execution: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def resume_execution(
        self,
        execution_id: str,
        execution_repo: WorkspaceExecutionRepository,
        job_repo: WorkspaceJobRepository
    ) -> Dict[str, Any]:
        """
        Resume a paused execution.

        Sets the execution status back to 'running' and creates a new job to continue.

        Args:
            execution_id: ID of the execution to resume
            execution_repo: WorkspaceExecutionRepository instance
            job_repo: WorkspaceJobRepository instance

        Returns:
            Dictionary with 'success' boolean and result or 'error'
        """
        try:
            logger.info(f"Resuming execution {execution_id}")

            # Get execution
            execution = await execution_repo.get_by_id(execution_id)
            if not execution:
                logger.warning(f"Execution not found: {execution_id}")
                return {
                    "success": False,
                    "error": "Execution not found"
                }

            # Check if execution can be resumed
            current_status = execution.get("status")
            if current_status != "paused":
                logger.warning(f"Cannot resume execution with status '{current_status}'")
                return {
                    "success": False,
                    "error": f"Cannot resume execution with status '{current_status}'"
                }

            # Update execution status
            updated = await execution_repo.update_status(execution_id, "running")
            if not updated:
                logger.error(f"Failed to update execution status to running")
                return {
                    "success": False,
                    "error": "Failed to update execution status"
                }

            # Create new job to continue execution
            job_payload = {
                "execution_id": execution_id,
                "project_id": execution.get("project_id"),
                "user_id": execution.get("user_id"),
                "resume": True,
                "last_completed_step": self._get_last_completed_step(execution)
            }

            job = await job_repo.create_job(
                job_type=self.JOB_TYPE,
                payload=job_payload,
                priority=2,  # Higher priority for resumed executions
                max_retries=2
            )

            if not job:
                # Rollback status
                await execution_repo.update_status(execution_id, "paused")
                logger.error(f"Failed to queue resume job for execution {execution_id}")
                return {
                    "success": False,
                    "error": "Failed to queue resume job"
                }

            # Add resume event
            await execution_repo.add_event(
                execution_id=execution_id,
                event_type="execution_resumed",
                event_data={"job_id": job.get("job_id")}
            )

            logger.info(f"Execution {execution_id} resumed with job {job.get('job_id')}")

            return {
                "success": True,
                "execution": updated,
                "job_id": job.get("job_id")
            }

        except Exception as e:
            logger.error(f"Error resuming execution: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def cancel_execution(
        self,
        execution_id: str,
        execution_repo: WorkspaceExecutionRepository,
        job_repo: WorkspaceJobRepository
    ) -> Dict[str, Any]:
        """
        Cancel a pending or running execution.

        Sets the execution status to 'cancelled' and cancels any associated jobs.

        Args:
            execution_id: ID of the execution to cancel
            execution_repo: WorkspaceExecutionRepository instance
            job_repo: WorkspaceJobRepository instance

        Returns:
            Dictionary with 'success' boolean and result or 'error'
        """
        try:
            logger.info(f"Cancelling execution {execution_id}")

            # Get execution
            execution = await execution_repo.get_by_id(execution_id)
            if not execution:
                logger.warning(f"Execution not found: {execution_id}")
                return {
                    "success": False,
                    "error": "Execution not found"
                }

            # Check if execution can be cancelled
            current_status = execution.get("status")
            if current_status in ["completed", "failed", "cancelled"]:
                logger.warning(f"Cannot cancel execution with status '{current_status}'")
                return {
                    "success": False,
                    "error": f"Cannot cancel execution with status '{current_status}'"
                }

            # Update execution status
            updated = await execution_repo.update_status(execution_id, "cancelled")
            if not updated:
                logger.error(f"Failed to update execution status to cancelled")
                return {
                    "success": False,
                    "error": "Failed to update execution status"
                }

            # Add cancellation event
            await execution_repo.add_event(
                execution_id=execution_id,
                event_type="execution_cancelled",
                event_data={"reason": "User requested cancellation"}
            )

            logger.info(f"Execution {execution_id} cancelled successfully")

            return {
                "success": True,
                "execution": updated
            }

        except Exception as e:
            logger.error(f"Error cancelling execution: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_execution_status(
        self,
        execution_id: str,
        execution_repo: WorkspaceExecutionRepository
    ) -> Dict[str, Any]:
        """
        Get the current status of an execution.

        Args:
            execution_id: ID of the execution
            execution_repo: WorkspaceExecutionRepository instance

        Returns:
            Dictionary with execution status, progress, and metrics
        """
        try:
            logger.debug(f"Getting status for execution {execution_id}")

            execution = await execution_repo.get_by_id(execution_id)
            if not execution:
                logger.warning(f"Execution not found: {execution_id}")
                return {
                    "success": False,
                    "error": "Execution not found"
                }

            # Calculate progress
            steps = execution.get("steps", [])
            total_steps = len(steps)
            completed_steps = len([s for s in steps if s.get("status") == "completed"])

            progress_percentage = 0
            if total_steps > 0:
                progress_percentage = int((completed_steps / total_steps) * 100)

            # Get current step
            current_step = None
            for step in steps:
                if step.get("status") == "running":
                    current_step = step
                    break

            return {
                "success": True,
                "execution_id": execution_id,
                "status": execution.get("status"),
                "progress_percentage": progress_percentage,
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "current_step": current_step,
                "metrics": execution.get("metrics", {}),
                "started_at": execution.get("started_at"),
                "completed_at": execution.get("completed_at"),
                "error": execution.get("error")
            }

        except Exception as e:
            logger.error(f"Error getting execution status: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _get_last_completed_step(self, execution: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get the last completed step from an execution.

        Args:
            execution: Execution document

        Returns:
            Last completed step or None
        """
        steps = execution.get("steps", [])
        completed_steps = [s for s in steps if s.get("status") == "completed"]

        if completed_steps:
            # Sort by step_index and return last
            completed_steps.sort(key=lambda s: s.get("step_index", 0))
            return completed_steps[-1]

        return None


# Create singleton instance
execution_service = ExecutionService()
