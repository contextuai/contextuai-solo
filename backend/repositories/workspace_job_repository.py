"""
Workspace Job Repository for AI Team Workspace Feature

Repository class for managing workspace background jobs in MongoDB.
Provides methods for creating and managing async job processing.
"""

from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta
import uuid

from .base_repository import BaseRepository


class WorkspaceJobRepository(BaseRepository):
    """
    Repository for workspace background jobs.

    Manages the 'workspace_jobs' collection in MongoDB, providing methods for
    creating, claiming, and managing async job processing.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for workspace jobs
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the WorkspaceJobRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "workspace_jobs")

    async def create_job(
        self,
        job_type: str,
        payload: Dict[str, Any],
        priority: int = 0,
        scheduled_at: Optional[str] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Create a new background job.

        Args:
            job_type: Type of job ('execute_project', 'run_agent', 'process_checkpoint', etc.)
            payload: Job-specific payload data
            priority: Job priority (higher = more important)
            scheduled_at: Optional ISO timestamp for scheduled execution
            max_retries: Maximum number of retry attempts

        Returns:
            Created job document with id field
        """
        job_data = {
            "job_id": str(uuid.uuid4()),
            "job_type": job_type,
            "payload": payload,
            "priority": priority,
            "status": "pending",
            "scheduled_at": scheduled_at,
            "started_at": None,
            "completed_at": None,
            "worker_id": None,
            "attempts": 0,
            "max_retries": max_retries,
            "error": None,
            "result": None,
            "locked_until": None
        }

        return await super().create(job_data)

    async def get_pending_job(
        self,
        job_types: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the next pending job for processing.

        Args:
            job_types: Optional list of job types to filter

        Returns:
            Pending job document, or None if no jobs available
        """
        now = datetime.utcnow().isoformat()

        filter_query: Dict[str, Any] = {
            "status": "pending",
            "$or": [
                {"scheduled_at": None},
                {"scheduled_at": {"$lte": now}}
            ],
            "$or": [
                {"locked_until": None},
                {"locked_until": {"$lt": now}}
            ]
        }

        if job_types:
            filter_query["job_type"] = {"$in": job_types}

        # Get highest priority pending job
        jobs = await self.get_all(
            filter=filter_query,
            limit=1,
            sort=[("priority", -1), ("created_at", 1)]
        )

        return jobs[0] if jobs else None

    async def claim_job(
        self,
        job_id: str,
        worker_id: str,
        lock_duration_seconds: int = 300
    ) -> Optional[Dict[str, Any]]:
        """
        Claim a job for processing by a worker.

        Uses atomic update to prevent race conditions.

        Args:
            job_id: The job's unique identifier
            worker_id: ID of the worker claiming the job
            lock_duration_seconds: How long to lock the job

        Returns:
            Claimed job document, or None if job was already claimed
        """
        now = datetime.utcnow()
        locked_until = (now + timedelta(seconds=lock_duration_seconds)).isoformat()
        now_iso = now.isoformat()

        # Atomically claim the job only if it's still pending and not locked
        result = await self.collection.find_one_and_update(
            {
                "job_id": job_id,
                "status": "pending",
                "$or": [
                    {"locked_until": None},
                    {"locked_until": {"$lt": now_iso}}
                ]
            },
            {
                "$set": {
                    "status": "running",
                    "worker_id": worker_id,
                    "started_at": now_iso,
                    "locked_until": locked_until,
                    "updated_at": now_iso
                },
                "$inc": {"attempts": 1}
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update the status of a job.

        Args:
            job_id: The job's unique identifier
            status: New status ('pending', 'running', 'completed', 'failed', 'cancelled')
            error: Optional error message

        Returns:
            Updated job document, or None if not found
        """
        job = await self.get_one({"job_id": job_id})
        if not job:
            try:
                job = await super().get_by_id(job_id)
            except ValueError:
                return None

        if not job:
            return None

        mongo_id = job["id"]
        now = datetime.utcnow().isoformat()

        update_data: Dict[str, Any] = {
            "status": status,
            "updated_at": now
        }

        if error:
            update_data["error"] = error

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {"$set": update_data},
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def complete_job(
        self,
        job_id: str,
        result: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Mark a job as completed.

        Args:
            job_id: The job's unique identifier
            result: Optional result data from the job

        Returns:
            Updated job document, or None if not found
        """
        job = await self.get_one({"job_id": job_id})
        if not job:
            try:
                job = await super().get_by_id(job_id)
            except ValueError:
                return None

        if not job:
            return None

        mongo_id = job["id"]
        now = datetime.utcnow().isoformat()

        update_data: Dict[str, Any] = {
            "status": "completed",
            "completed_at": now,
            "locked_until": None,
            "updated_at": now
        }

        if result is not None:
            update_data["result"] = result

        db_result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {"$set": update_data},
            return_document=True
        )

        return self._convert_id(db_result) if db_result else None

    async def fail_job(
        self,
        job_id: str,
        error: str,
        retry: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Mark a job as failed.

        If retry is True and attempts < max_retries, the job will be
        re-queued as pending.

        Args:
            job_id: The job's unique identifier
            error: Error message describing the failure
            retry: Whether to retry the job if retries remain

        Returns:
            Updated job document, or None if not found
        """
        job = await self.get_one({"job_id": job_id})
        if not job:
            try:
                job = await super().get_by_id(job_id)
            except ValueError:
                return None

        if not job:
            return None

        mongo_id = job["id"]
        now = datetime.utcnow().isoformat()

        attempts = job.get("attempts", 0)
        max_retries = job.get("max_retries", 3)

        if retry and attempts < max_retries:
            # Retry the job with exponential backoff
            backoff_seconds = min(300, 30 * (2 ** attempts))
            scheduled_at = (datetime.utcnow() + timedelta(seconds=backoff_seconds)).isoformat()

            update_data = {
                "status": "pending",
                "error": error,
                "scheduled_at": scheduled_at,
                "worker_id": None,
                "locked_until": None,
                "updated_at": now
            }
        else:
            # Final failure
            update_data = {
                "status": "failed",
                "error": error,
                "completed_at": now,
                "locked_until": None,
                "updated_at": now
            }

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {"$set": update_data},
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a job by its ID.

        Args:
            job_id: The job's unique identifier (job_id field)

        Returns:
            Job document with id field, or None if not found
        """
        # First try by job_id field
        job = await self.get_one({"job_id": job_id})
        if job:
            return job

        # Fall back to MongoDB _id
        try:
            return await super().get_by_id(job_id)
        except ValueError:
            return None

    async def get_jobs_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve jobs by status.

        Args:
            status: Job status to filter by
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of job documents sorted by created_at descending
        """
        return await self.get_all(
            filter={"status": status},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def get_worker_jobs(
        self,
        worker_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve jobs assigned to a specific worker.

        Args:
            worker_id: ID of the worker
            status: Optional status filter
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of job documents
        """
        filter_query: Dict[str, Any] = {"worker_id": worker_id}

        if status:
            filter_query["status"] = status

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def release_stale_jobs(
        self,
        stale_threshold_seconds: int = 600
    ) -> int:
        """
        Release jobs that have been locked for too long.

        Args:
            stale_threshold_seconds: Time in seconds before a locked job is considered stale

        Returns:
            Number of jobs released
        """
        threshold = (datetime.utcnow() - timedelta(seconds=stale_threshold_seconds)).isoformat()
        now = datetime.utcnow().isoformat()

        result = await self.collection.update_many(
            {
                "status": "running",
                "locked_until": {"$lt": threshold}
            },
            {
                "$set": {
                    "status": "pending",
                    "worker_id": None,
                    "locked_until": None,
                    "updated_at": now
                }
            }
        )

        return result.modified_count

    async def cancel_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Cancel a pending or running job.

        Args:
            job_id: The job's unique identifier

        Returns:
            Updated job document, or None if not found
        """
        job = await self.get_one({"job_id": job_id, "status": {"$in": ["pending", "running"]}})
        if not job:
            return None

        mongo_id = job["id"]
        now = datetime.utcnow().isoformat()

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$set": {
                    "status": "cancelled",
                    "completed_at": now,
                    "locked_until": None,
                    "updated_at": now
                }
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def cleanup_old_jobs(
        self,
        days_to_keep: int = 30
    ) -> int:
        """
        Delete old completed/failed jobs.

        Args:
            days_to_keep: Number of days to keep jobs

        Returns:
            Number of jobs deleted
        """
        threshold = (datetime.utcnow() - timedelta(days=days_to_keep)).isoformat()

        result = await self.collection.delete_many({
            "status": {"$in": ["completed", "failed", "cancelled"]},
            "completed_at": {"$lt": threshold}
        })

        return result.deleted_count
