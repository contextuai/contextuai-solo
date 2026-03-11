"""
Checkpoint Service for AI Team Workspace Feature

Provides business logic for managing human-in-the-loop checkpoints,
including creation, resolution, and blocking status checks.
"""

import logging
from typing import Dict, Any, List, Optional

from repositories.workspace_checkpoint_repository import WorkspaceCheckpointRepository

# Configure logging
logger = logging.getLogger(__name__)


class CheckpointService:
    """
    Service for checkpoint management.

    Provides methods for creating and resolving human-in-the-loop checkpoints
    that pause execution for user review or input.
    """

    # Valid checkpoint types
    CHECKPOINT_TYPES = ["approval", "decision", "review", "input", "confirmation"]

    # Valid checkpoint statuses
    CHECKPOINT_STATUSES = ["pending", "resolved", "expired", "cancelled"]

    # Default auto-resolve timeout (in seconds)
    DEFAULT_TIMEOUT = 3600  # 1 hour

    async def create_checkpoint(
        self,
        execution_id: str,
        project_id: str,
        step_id: str,
        agent_id: str,
        checkpoint_type: str,
        title: str,
        description: str,
        options: List[Dict[str, Any]],
        checkpoint_repo: WorkspaceCheckpointRepository,
        context: Optional[Dict[str, Any]] = None,
        auto_resolve_timeout: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new checkpoint for human review.

        Args:
            execution_id: ID of the current execution
            project_id: ID of the project
            step_id: ID of the step that triggered the checkpoint
            agent_id: ID of the agent that triggered the checkpoint
            checkpoint_type: Type of checkpoint (approval, decision, review, input)
            title: Title of the checkpoint
            description: Description of what needs to be reviewed/decided
            options: List of available options/actions
            checkpoint_repo: WorkspaceCheckpointRepository instance
            context: Optional context data for the checkpoint
            auto_resolve_timeout: Optional timeout in seconds for auto-resolution

        Returns:
            Created checkpoint document or None if creation failed
        """
        try:
            # Validate checkpoint type
            if checkpoint_type not in self.CHECKPOINT_TYPES:
                logger.error(f"Invalid checkpoint type: {checkpoint_type}")
                return None

            # Validate options
            if not options or not isinstance(options, list):
                logger.error("Checkpoint must have at least one option")
                return None

            # Validate each option has required fields
            for idx, option in enumerate(options):
                if not option.get("id") or not option.get("label"):
                    logger.error(f"Option {idx} missing required fields (id, label)")
                    return None

            # Create the checkpoint
            checkpoint = await checkpoint_repo.create(
                execution_id=execution_id,
                project_id=project_id,
                step_id=step_id,
                agent_id=agent_id,
                checkpoint_type=checkpoint_type,
                title=title,
                description=description,
                options=options,
                context=context,
                auto_resolve_timeout=auto_resolve_timeout
            )

            logger.info(
                f"Created checkpoint '{title}' for project {project_id} "
                f"(type={checkpoint_type}, agent={agent_id})"
            )

            return checkpoint

        except Exception as e:
            logger.error(f"Error creating checkpoint: {e}")
            return None

    async def get_pending_checkpoints(
        self,
        project_id: str,
        checkpoint_repo: WorkspaceCheckpointRepository
    ) -> List[Dict[str, Any]]:
        """
        Get all unresolved checkpoints for a project.

        Args:
            project_id: ID of the project
            checkpoint_repo: WorkspaceCheckpointRepository instance

        Returns:
            List of pending checkpoint documents
        """
        try:
            checkpoints = await checkpoint_repo.get_pending_for_project(project_id)
            logger.debug(f"Retrieved {len(checkpoints)} pending checkpoints for project {project_id}")
            return checkpoints

        except Exception as e:
            logger.error(f"Error getting pending checkpoints: {e}")
            return []

    async def resolve_checkpoint(
        self,
        checkpoint_id: str,
        action: str,
        feedback: Optional[str],
        user_id: str,
        checkpoint_repo: WorkspaceCheckpointRepository
    ) -> Dict[str, Any]:
        """
        Handle user response to a checkpoint.

        Args:
            checkpoint_id: ID of the checkpoint to resolve
            action: The action/option selected by the user
            feedback: Optional feedback from the user
            user_id: ID of the user resolving the checkpoint
            checkpoint_repo: WorkspaceCheckpointRepository instance

        Returns:
            Dictionary with 'success' boolean and resolved checkpoint or error
        """
        try:
            # Get the checkpoint first
            checkpoint = await checkpoint_repo.get_by_id(checkpoint_id)
            if not checkpoint:
                logger.warning(f"Checkpoint not found: {checkpoint_id}")
                return {
                    "success": False,
                    "error": "Checkpoint not found"
                }

            # Check if already resolved
            if checkpoint.get("status") != "pending":
                logger.warning(f"Checkpoint {checkpoint_id} already {checkpoint.get('status')}")
                return {
                    "success": False,
                    "error": f"Checkpoint already {checkpoint.get('status')}"
                }

            # Validate action is one of the valid options
            options = checkpoint.get("options", [])
            valid_option_ids = {opt.get("id") for opt in options}
            if action not in valid_option_ids:
                logger.warning(f"Invalid action '{action}' for checkpoint {checkpoint_id}")
                return {
                    "success": False,
                    "error": f"Invalid action. Valid options: {', '.join(valid_option_ids)}"
                }

            # Resolve the checkpoint
            resolved = await checkpoint_repo.resolve(
                checkpoint_id=checkpoint_id,
                resolution=action,
                feedback=feedback,
                resolved_by=user_id
            )

            if resolved:
                logger.info(
                    f"Checkpoint {checkpoint_id} resolved by user {user_id} "
                    f"with action '{action}'"
                )
                return {
                    "success": True,
                    "checkpoint": resolved,
                    "action": action
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to resolve checkpoint"
                }

        except Exception as e:
            logger.error(f"Error resolving checkpoint: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def is_blocked(
        self,
        project_id: str,
        checkpoint_repo: WorkspaceCheckpointRepository
    ) -> bool:
        """
        Check if project is blocked by any pending checkpoint.

        Args:
            project_id: ID of the project
            checkpoint_repo: WorkspaceCheckpointRepository instance

        Returns:
            True if project has pending checkpoints, False otherwise
        """
        try:
            pending_count = await checkpoint_repo.get_pending_count_for_project(project_id)
            is_blocked = pending_count > 0

            if is_blocked:
                logger.debug(f"Project {project_id} is blocked by {pending_count} checkpoint(s)")

            return is_blocked

        except Exception as e:
            logger.error(f"Error checking if project is blocked: {e}")
            return False

    async def get_checkpoint(
        self,
        checkpoint_id: str,
        checkpoint_repo: WorkspaceCheckpointRepository
    ) -> Optional[Dict[str, Any]]:
        """
        Get a checkpoint by ID.

        Args:
            checkpoint_id: ID of the checkpoint
            checkpoint_repo: WorkspaceCheckpointRepository instance

        Returns:
            Checkpoint document or None if not found
        """
        try:
            return await checkpoint_repo.get_by_id(checkpoint_id)

        except Exception as e:
            logger.error(f"Error getting checkpoint: {e}")
            return None

    async def cancel_checkpoint(
        self,
        checkpoint_id: str,
        checkpoint_repo: WorkspaceCheckpointRepository
    ) -> Dict[str, Any]:
        """
        Cancel a pending checkpoint.

        Args:
            checkpoint_id: ID of the checkpoint to cancel
            checkpoint_repo: WorkspaceCheckpointRepository instance

        Returns:
            Dictionary with 'success' boolean and result
        """
        try:
            result = await checkpoint_repo.cancel(checkpoint_id)

            if result:
                logger.info(f"Checkpoint {checkpoint_id} cancelled")
                return {
                    "success": True,
                    "checkpoint": result
                }
            else:
                return {
                    "success": False,
                    "error": "Checkpoint not found or already resolved"
                }

        except Exception as e:
            logger.error(f"Error cancelling checkpoint: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_execution_checkpoints(
        self,
        execution_id: str,
        checkpoint_repo: WorkspaceCheckpointRepository,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all checkpoints for an execution.

        Args:
            execution_id: ID of the execution
            checkpoint_repo: WorkspaceCheckpointRepository instance
            status: Optional status filter

        Returns:
            List of checkpoint documents
        """
        try:
            checkpoints = await checkpoint_repo.get_execution_checkpoints(
                execution_id=execution_id,
                status=status
            )

            logger.debug(
                f"Retrieved {len(checkpoints)} checkpoints for execution {execution_id}"
            )

            return checkpoints

        except Exception as e:
            logger.error(f"Error getting execution checkpoints: {e}")
            return []

    async def expire_overdue_checkpoints(
        self,
        checkpoint_repo: WorkspaceCheckpointRepository
    ) -> int:
        """
        Mark overdue checkpoints as expired.

        Args:
            checkpoint_repo: WorkspaceCheckpointRepository instance

        Returns:
            Number of checkpoints marked as expired
        """
        try:
            count = await checkpoint_repo.expire_overdue()

            if count > 0:
                logger.info(f"Expired {count} overdue checkpoint(s)")

            return count

        except Exception as e:
            logger.error(f"Error expiring overdue checkpoints: {e}")
            return 0

    def build_approval_options(self) -> List[Dict[str, Any]]:
        """
        Build standard options for an approval checkpoint.

        Returns:
            List of approval options
        """
        return [
            {"id": "approve", "label": "Approve", "description": "Approve and continue"},
            {"id": "reject", "label": "Reject", "description": "Reject and stop execution"},
            {"id": "revise", "label": "Request Revision", "description": "Send back for revision"}
        ]

    def build_decision_options(
        self,
        choices: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        Build options for a decision checkpoint.

        Args:
            choices: List of choice dictionaries with 'id', 'label', and optional 'description'

        Returns:
            List of decision options
        """
        return [
            {
                "id": choice.get("id"),
                "label": choice.get("label"),
                "description": choice.get("description", "")
            }
            for choice in choices
        ]


# Create singleton instance
checkpoint_service = CheckpointService()
