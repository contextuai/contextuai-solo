"""
Workspace Execution Repository for AI Team Workspace Feature

Repository class for managing workspace executions in MongoDB.
Provides methods for tracking project executions, steps, and events.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class WorkspaceExecutionRepository(BaseRepository):
    """
    Repository for workspace executions.

    Manages the 'workspace_executions' collection in MongoDB, providing methods for
    creating, tracking, and managing project execution runs.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for workspace executions
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the WorkspaceExecutionRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "workspace_executions")

    async def create(
        self,
        project_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Create a new workspace execution.

        Args:
            project_id: ID of the project being executed
            user_id: ID of the user initiating the execution

        Returns:
            Created execution document with id field
        """
        execution_data = {
            "execution_id": str(uuid.uuid4()),
            "project_id": project_id,
            "user_id": user_id,
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "steps": [],
            "events": [],
            "result": None,
            "error": None,
            "metrics": {
                "total_tokens": 0,
                "total_cost": 0.0,
                "duration_ms": 0
            }
        }

        return await super().create(execution_data)

    async def get_by_id(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an execution by its ID.

        Args:
            execution_id: The execution's unique identifier (execution_id field)

        Returns:
            Execution document with id field, or None if not found
        """
        # First try by execution_id field
        execution = await self.get_one({"execution_id": execution_id})
        if execution:
            return execution

        # Fall back to MongoDB _id
        try:
            return await super().get_by_id(execution_id)
        except ValueError:
            return None

    async def get_project_executions(
        self,
        project_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve executions for a specific project.

        Args:
            project_id: ID of the project
            limit: Maximum number of executions to return
            offset: Number of executions to skip (for pagination)

        Returns:
            List of execution documents sorted by created_at descending
        """
        return await self.get_all(
            filter={"project_id": project_id},
            skip=offset,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def update_status(
        self,
        execution_id: str,
        status: str,
        error: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update the status of an execution.

        Args:
            execution_id: The execution's unique identifier
            status: New status ('pending', 'running', 'completed', 'failed', 'cancelled')
            error: Optional error message if status is 'failed'

        Returns:
            Updated execution document, or None if not found
        """
        execution = await self.get_one({"execution_id": execution_id})
        if not execution:
            try:
                execution = await super().get_by_id(execution_id)
            except ValueError:
                return None

        if not execution:
            return None

        mongo_id = execution["id"]
        now = datetime.utcnow().isoformat()

        update_data: Dict[str, Any] = {
            "status": status,
            "updated_at": now
        }

        if status == "running" and not execution.get("started_at"):
            update_data["started_at"] = now

        if status in ("completed", "failed", "cancelled"):
            update_data["completed_at"] = now
            if execution.get("started_at"):
                started = datetime.fromisoformat(execution["started_at"])
                completed = datetime.fromisoformat(now)
                update_data["metrics.duration_ms"] = int((completed - started).total_seconds() * 1000)

        if error:
            update_data["error"] = error

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {"$set": update_data},
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def add_step(
        self,
        execution_id: str,
        step_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Add a step to the execution.

        Args:
            execution_id: The execution's unique identifier
            step_data: Step information including agent_id, action, status, etc.

        Returns:
            Updated execution document, or None if not found
        """
        execution = await self.get_one({"execution_id": execution_id})
        if not execution:
            try:
                execution = await super().get_by_id(execution_id)
            except ValueError:
                return None

        if not execution:
            return None

        mongo_id = execution["id"]
        now = datetime.utcnow().isoformat()

        step = {
            "step_id": str(uuid.uuid4()),
            "step_index": len(execution.get("steps", [])),
            "created_at": now,
            "status": "pending",
            **step_data
        }

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$push": {"steps": step},
                "$set": {"updated_at": now}
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def update_step(
        self,
        execution_id: str,
        step_id: str,
        update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a specific step in the execution.

        Args:
            execution_id: The execution's unique identifier
            step_id: The step's unique identifier
            update_data: Fields to update on the step

        Returns:
            Updated execution document, or None if not found
        """
        execution = await self.get_one({"execution_id": execution_id})
        if not execution:
            try:
                execution = await super().get_by_id(execution_id)
            except ValueError:
                return None

        if not execution:
            return None

        mongo_id = execution["id"]
        now = datetime.utcnow().isoformat()

        # Build update operations for the specific step
        set_operations: Dict[str, Any] = {"updated_at": now}
        for key, value in update_data.items():
            set_operations[f"steps.$[elem].{key}"] = value
        set_operations["steps.$[elem].updated_at"] = now

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {"$set": set_operations},
            array_filters=[{"elem.step_id": step_id}],
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def add_event(
        self,
        execution_id: str,
        event_type: str,
        event_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Add an event to the execution timeline.

        Args:
            execution_id: The execution's unique identifier
            event_type: Type of event ('agent_started', 'agent_completed', 'checkpoint', etc.)
            event_data: Event-specific data

        Returns:
            Updated execution document, or None if not found
        """
        execution = await self.get_one({"execution_id": execution_id})
        if not execution:
            try:
                execution = await super().get_by_id(execution_id)
            except ValueError:
                return None

        if not execution:
            return None

        mongo_id = execution["id"]
        now = datetime.utcnow().isoformat()

        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "timestamp": now,
            **event_data
        }

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$push": {"events": event},
                "$set": {"updated_at": now}
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def get_events_after(
        self,
        execution_id: str,
        after_timestamp: str
    ) -> List[Dict[str, Any]]:
        """
        Get events after a specific timestamp for real-time updates.

        Args:
            execution_id: The execution's unique identifier
            after_timestamp: ISO timestamp to filter events after

        Returns:
            List of events after the specified timestamp
        """
        execution = await self.get_one({"execution_id": execution_id})
        if not execution:
            try:
                execution = await super().get_by_id(execution_id)
            except ValueError:
                return []

        if not execution:
            return []

        events = execution.get("events", [])
        return [e for e in events if e.get("timestamp", "") > after_timestamp]

    async def get_user_executions(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve executions for a specific user.

        Args:
            user_id: ID of the user
            status: Optional status filter
            limit: Maximum number of executions to return
            offset: Number of executions to skip (for pagination)

        Returns:
            List of execution documents sorted by created_at descending
        """
        filter_query: Dict[str, Any] = {"user_id": user_id}

        if status:
            filter_query["status"] = status

        return await self.get_all(
            filter=filter_query,
            skip=offset,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def update_metrics(
        self,
        execution_id: str,
        tokens: int = 0,
        cost: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """
        Update execution metrics (tokens used, cost).

        Args:
            execution_id: The execution's unique identifier
            tokens: Number of tokens to add
            cost: Cost to add

        Returns:
            Updated execution document, or None if not found
        """
        execution = await self.get_one({"execution_id": execution_id})
        if not execution:
            try:
                execution = await super().get_by_id(execution_id)
            except ValueError:
                return None

        if not execution:
            return None

        mongo_id = execution["id"]
        now = datetime.utcnow().isoformat()

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$inc": {
                    "metrics.total_tokens": tokens,
                    "metrics.total_cost": cost
                },
                "$set": {"updated_at": now}
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def update_by_execution_id(
        self,
        execution_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an execution by its execution_id (UUID), not MongoDB ObjectId.

        Args:
            execution_id: The execution's UUID
            data: Fields to update (partial update supported)

        Returns:
            Updated execution document, or None if not found
        """
        now = datetime.utcnow().isoformat()
        data["updated_at"] = now

        result = await self.collection.find_one_and_update(
            {"execution_id": execution_id},
            {"$set": data},
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def set_result(
        self,
        execution_id: str,
        result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Set the final result of an execution.

        Args:
            execution_id: The execution's unique identifier
            result: The execution result data

        Returns:
            Updated execution document, or None if not found
        """
        execution = await self.get_one({"execution_id": execution_id})
        if not execution:
            try:
                execution = await super().get_by_id(execution_id)
            except ValueError:
                return None

        if not execution:
            return None

        mongo_id = execution["id"]
        now = datetime.utcnow().isoformat()

        db_result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$set": {
                    "result": result,
                    "updated_at": now
                }
            },
            return_document=True
        )

        return self._convert_id(db_result) if db_result else None
