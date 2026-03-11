"""
Workspace Checkpoint Repository for AI Team Workspace Feature

Repository class for managing workspace checkpoints in MongoDB.
Provides methods for creating and managing human-in-the-loop checkpoints.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class WorkspaceCheckpointRepository(BaseRepository):
    """
    Repository for workspace checkpoints.

    Manages the 'workspace_checkpoints' collection in MongoDB, providing methods for
    creating, retrieving, and resolving human-in-the-loop checkpoints.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for workspace checkpoints
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the WorkspaceCheckpointRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "workspace_checkpoints")

    async def create(
        self,
        execution_id: str,
        project_id: str,
        step_id: str,
        agent_id: str,
        checkpoint_type: str,
        title: str,
        description: str,
        options: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        auto_resolve_timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create a new checkpoint for human review.

        Args:
            execution_id: ID of the execution
            project_id: ID of the project
            step_id: ID of the step that triggered the checkpoint
            agent_id: ID of the agent that triggered the checkpoint
            checkpoint_type: Type of checkpoint ('approval', 'decision', 'review', 'input')
            title: Title of the checkpoint
            description: Description of what needs to be reviewed/decided
            options: List of available options/actions
            context: Optional context data for the checkpoint
            auto_resolve_timeout: Optional timeout in seconds for auto-resolution

        Returns:
            Created checkpoint document with id field
        """
        checkpoint_data = {
            "checkpoint_id": str(uuid.uuid4()),
            "execution_id": execution_id,
            "project_id": project_id,
            "step_id": step_id,
            "agent_id": agent_id,
            "checkpoint_type": checkpoint_type,
            "title": title,
            "description": description,
            "options": options,
            "context": context or {},
            "status": "pending",
            "resolution": None,
            "feedback": None,
            "resolved_at": None,
            "resolved_by": None,
            "auto_resolve_timeout": auto_resolve_timeout,
            "expires_at": None
        }

        # Calculate expiration if timeout is set
        if auto_resolve_timeout:
            from datetime import timedelta
            expires_at = datetime.utcnow() + timedelta(seconds=auto_resolve_timeout)
            checkpoint_data["expires_at"] = expires_at.isoformat()

        return await super().create(checkpoint_data)

    async def get_by_id(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a checkpoint by its ID.

        Args:
            checkpoint_id: The checkpoint's unique identifier (checkpoint_id field)

        Returns:
            Checkpoint document with id field, or None if not found
        """
        # First try by checkpoint_id field
        checkpoint = await self.get_one({"checkpoint_id": checkpoint_id})
        if checkpoint:
            return checkpoint

        # Fall back to MongoDB _id
        try:
            return await super().get_by_id(checkpoint_id)
        except ValueError:
            return None

    async def get_pending_for_project(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve pending checkpoints for a specific project.

        Args:
            project_id: ID of the project
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of pending checkpoint documents sorted by created_at ascending
        """
        return await self.get_all(
            filter={"project_id": project_id, "status": "pending"},
            skip=skip,
            limit=limit,
            sort=[("created_at", 1)]  # Oldest first
        )

    async def resolve(
        self,
        checkpoint_id: str,
        resolution: str,
        feedback: Optional[str] = None,
        resolved_by: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a checkpoint with user decision.

        Args:
            checkpoint_id: The checkpoint's unique identifier
            resolution: The selected resolution/option
            feedback: Optional feedback from the user
            resolved_by: Optional user ID who resolved the checkpoint

        Returns:
            Updated checkpoint document, or None if not found
        """
        checkpoint = await self.get_one({"checkpoint_id": checkpoint_id})
        if not checkpoint:
            try:
                checkpoint = await super().get_by_id(checkpoint_id)
            except ValueError:
                return None

        if not checkpoint:
            return None

        mongo_id = checkpoint["id"]
        now = datetime.utcnow().isoformat()

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$set": {
                    "status": "resolved",
                    "resolution": resolution,
                    "feedback": feedback,
                    "resolved_at": now,
                    "resolved_by": resolved_by,
                    "updated_at": now
                }
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def get_project_checkpoints(
        self,
        project_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all checkpoints for a project.

        Args:
            project_id: ID of the project
            status: Optional status filter ('pending', 'resolved', 'expired', 'cancelled')
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of checkpoint documents sorted by created_at descending
        """
        filter_query: Dict[str, Any] = {"project_id": project_id}

        if status:
            filter_query["status"] = status

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def get_execution_checkpoints(
        self,
        execution_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all checkpoints for an execution.

        Args:
            execution_id: ID of the execution
            status: Optional status filter
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of checkpoint documents sorted by created_at ascending
        """
        filter_query: Dict[str, Any] = {"execution_id": execution_id}

        if status:
            filter_query["status"] = status

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("created_at", 1)]
        )

    async def cancel(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        Cancel a pending checkpoint.

        Args:
            checkpoint_id: The checkpoint's unique identifier

        Returns:
            Updated checkpoint document, or None if not found
        """
        checkpoint = await self.get_one({"checkpoint_id": checkpoint_id, "status": "pending"})
        if not checkpoint:
            return None

        mongo_id = checkpoint["id"]
        now = datetime.utcnow().isoformat()

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$set": {
                    "status": "cancelled",
                    "updated_at": now
                }
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def expire_overdue(self) -> int:
        """
        Mark expired checkpoints as expired based on expires_at.

        Returns:
            Number of checkpoints marked as expired
        """
        now = datetime.utcnow().isoformat()

        result = await self.collection.update_many(
            {
                "status": "pending",
                "expires_at": {"$lt": now, "$ne": None}
            },
            {
                "$set": {
                    "status": "expired",
                    "updated_at": now
                }
            }
        )

        return result.modified_count

    async def get_pending_count_for_project(self, project_id: str) -> int:
        """
        Count pending checkpoints for a project.

        Args:
            project_id: ID of the project

        Returns:
            Number of pending checkpoints
        """
        return await self.count({"project_id": project_id, "status": "pending"})

    async def get_by_step(self, step_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve checkpoint for a specific step.

        Args:
            step_id: ID of the step

        Returns:
            Checkpoint document, or None if not found
        """
        return await self.get_one({"step_id": step_id})
