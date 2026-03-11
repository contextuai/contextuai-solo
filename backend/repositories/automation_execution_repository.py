"""
Automation Execution Repository for Execution History

Repository class for managing automation execution records in MongoDB.
Provides methods for tracking execution history and status updates.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class AutomationExecutionRepository(BaseRepository):
    """
    Repository for automation execution records.

    Manages the 'automation_executions' collection in MongoDB, providing methods for
    creating and tracking automation execution history.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for execution records
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the AutomationExecutionRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "automation_executions")

    async def create_execution(
        self,
        automation_id: str,
        user_id: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new execution record.

        Args:
            automation_id: ID of the automation being executed
            user_id: ID of the user triggering the execution
            parameters: Optional parameters passed to the automation

        Returns:
            Created execution document with id field
        """
        execution_data = {
            "execution_id": str(uuid.uuid4()),
            "automation_id": automation_id,
            "user_id": user_id,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "duration_ms": None,
            "parameters": parameters or {},
            "steps": [],
            "result": None,
            "error": None,
            "total_steps": 0,
            "successful_steps": 0,
            "failed_steps": 0
        }

        return await super().create(execution_data)

    async def update_execution(
        self,
        execution_id: str,
        status: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        result: Optional[str] = None,
        error: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update an execution record with results.

        Args:
            execution_id: The execution's unique identifier
            status: Execution status ('running', 'success', 'failed', 'partial')
            steps: List of step execution details
            result: Final aggregated result
            error: Error message if execution failed

        Returns:
            Updated execution document, or None if not found
        """
        # Find the execution first
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

        # Calculate duration if completing
        duration_ms = None
        if status in ["success", "failed", "partial"] and execution.get("started_at"):
            started = datetime.fromisoformat(execution["started_at"].rstrip("Z"))
            ended = datetime.utcnow()
            duration_ms = int((ended - started).total_seconds() * 1000)

        # Calculate step counts
        successful_steps = 0
        failed_steps = 0
        if steps:
            for step in steps:
                if step.get("status") == "success":
                    successful_steps += 1
                elif step.get("status") == "failed":
                    failed_steps += 1

        update_data = {
            "status": status,
            "updated_at": now
        }

        if status in ["success", "failed", "partial"]:
            update_data["completed_at"] = now

        if duration_ms is not None:
            update_data["duration_ms"] = duration_ms

        if steps is not None:
            update_data["steps"] = steps
            update_data["total_steps"] = len(steps)
            update_data["successful_steps"] = successful_steps
            update_data["failed_steps"] = failed_steps

        if result is not None:
            update_data["result"] = result

        if error is not None:
            update_data["error"] = error

        return await super().update(mongo_id, update_data)

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

    async def get_automation_history(
        self,
        automation_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Retrieve execution history for a specific automation.

        Args:
            automation_id: ID of the automation
            limit: Maximum number of executions to return

        Returns:
            List of execution documents sorted by started_at descending
        """
        return await self.get_all(
            filter={"automation_id": automation_id},
            limit=limit,
            sort=[("started_at", -1)]
        )

    async def get_user_executions(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Retrieve execution history for a specific user.

        Args:
            user_id: ID of the user
            limit: Maximum number of executions to return

        Returns:
            List of execution documents sorted by started_at descending
        """
        return await self.get_all(
            filter={"user_id": user_id},
            limit=limit,
            sort=[("started_at", -1)]
        )

    async def get_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve executions by status.

        Args:
            status: The execution status ('running', 'success', 'failed', 'partial')
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of execution documents matching the status
        """
        return await self.get_all(
            filter={"status": status},
            skip=skip,
            limit=limit,
            sort=[("started_at", -1)]
        )

    async def get_running_executions(self) -> List[Dict[str, Any]]:
        """
        Retrieve all currently running executions.

        Returns:
            List of running execution documents
        """
        return await self.get_all(
            filter={"status": "running"},
            sort=[("started_at", 1)]
        )

    async def add_step(
        self,
        execution_id: str,
        step: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Add a step to an execution's step list.

        Args:
            execution_id: The execution's unique identifier
            step: Step execution details

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

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$push": {"steps": step},
                "$inc": {"total_steps": 1},
                "$set": {"updated_at": datetime.utcnow().isoformat()}
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def get_execution_stats(
        self,
        automation_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get execution statistics for an automation.

        Args:
            automation_id: ID of the automation
            start_date: Optional start date filter (ISO format)
            end_date: Optional end date filter (ISO format)

        Returns:
            Dictionary with execution statistics
        """
        filter_query: Dict[str, Any] = {"automation_id": automation_id}

        if start_date or end_date:
            filter_query["started_at"] = {}
            if start_date:
                filter_query["started_at"]["$gte"] = start_date
            if end_date:
                filter_query["started_at"]["$lte"] = end_date

        total = await self.count(filter_query)

        success_filter = {**filter_query, "status": "success"}
        failed_filter = {**filter_query, "status": "failed"}
        partial_filter = {**filter_query, "status": "partial"}

        success_count = await self.count(success_filter)
        failed_count = await self.count(failed_filter)
        partial_count = await self.count(partial_filter)

        # Calculate average duration using aggregation
        pipeline = [
            {"$match": {**filter_query, "duration_ms": {"$exists": True, "$ne": None}}},
            {"$group": {
                "_id": None,
                "avg_duration_ms": {"$avg": "$duration_ms"},
                "min_duration_ms": {"$min": "$duration_ms"},
                "max_duration_ms": {"$max": "$duration_ms"}
            }}
        ]

        duration_stats = await self.aggregate(pipeline, convert_ids=False)

        return {
            "total_executions": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "partial_count": partial_count,
            "success_rate": (success_count / total * 100) if total > 0 else 0,
            "avg_duration_ms": duration_stats[0].get("avg_duration_ms", 0) if duration_stats else 0,
            "min_duration_ms": duration_stats[0].get("min_duration_ms", 0) if duration_stats else 0,
            "max_duration_ms": duration_stats[0].get("max_duration_ms", 0) if duration_stats else 0
        }

    async def get_recent_failures(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve recent failed executions.

        Args:
            limit: Maximum number of failures to return

        Returns:
            List of failed execution documents
        """
        return await self.get_all(
            filter={"status": {"$in": ["failed", "partial"]}},
            limit=limit,
            sort=[("started_at", -1)]
        )

    async def cleanup_old_executions(
        self,
        days: int = 90
    ) -> int:
        """
        Delete execution records older than specified days.

        Args:
            days: Number of days to keep executions

        Returns:
            Number of deleted records
        """
        from datetime import timedelta

        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        return await self.delete_many({"started_at": {"$lt": cutoff_date}})

    async def count_by_automation(self, automation_id: str) -> int:
        """
        Count executions for a specific automation.

        Args:
            automation_id: ID of the automation

        Returns:
            Number of executions for the automation
        """
        return await self.count({"automation_id": automation_id})

    async def get_user_execution_summary(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get execution summary for a user.

        Args:
            user_id: ID of the user

        Returns:
            Dictionary with user execution summary
        """
        total = await self.count({"user_id": user_id})
        success = await self.count({"user_id": user_id, "status": "success"})
        failed = await self.count({"user_id": user_id, "status": {"$in": ["failed", "partial"]}})

        return {
            "total_executions": total,
            "successful": success,
            "failed": failed,
            "success_rate": (success / total * 100) if total > 0 else 0
        }
