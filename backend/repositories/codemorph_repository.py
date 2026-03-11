"""
CodeMorph Repository
MongoDB repository for CodeMorph migration jobs.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from .base_repository import BaseRepository


class CodeMorphRepository(BaseRepository):
    """
    Repository for CodeMorph job data in MongoDB.

    Collection: codemorph_jobs
    """

    def __init__(self, db):
        """Initialize with MongoDB database reference"""
        super().__init__(db, "codemorph_jobs")

    async def create_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new migration job.

        Args:
            job_data: Job data dictionary

        Returns:
            Created job with _id
        """
        return await self.create(job_data)

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job by job_id.

        Args:
            job_id: Job identifier

        Returns:
            Job document or None
        """
        return await self.get_one({"job_id": job_id})

    async def get_jobs_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get jobs for a specific user with optional filtering.

        Args:
            user_id: User identifier
            status: Optional status filter
            limit: Maximum results
            offset: Skip count for pagination

        Returns:
            List of job documents
        """
        filter_query = {"user_id": user_id}
        if status:
            filter_query["status"] = status

        return await self.get_all(
            filter=filter_query,
            limit=limit,
            skip=offset,
            sort=[("created_at", -1)]  # Newest first
        )

    async def count_user_jobs(
        self,
        user_id: str,
        status: Optional[str] = None
    ) -> int:
        """
        Count jobs for a user with optional status filter.

        Args:
            user_id: User identifier
            status: Optional status filter

        Returns:
            Job count
        """
        filter_query = {"user_id": user_id}
        if status:
            filter_query["status"] = status

        return await self.count(filter_query)

    async def update_job(
        self,
        job_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update job fields.

        Args:
            job_id: Job identifier
            updates: Fields to update

        Returns:
            Updated job document or None
        """
        # Add updated_at timestamp
        updates["updated_at"] = datetime.utcnow().isoformat() + "Z"

        # Use collection directly for filter-based update
        result = await self.collection.find_one_and_update(
            {"job_id": job_id},
            {"$set": updates},
            return_document=True
        )
        return self._convert_id(result) if result else None

    async def update_job_status(
        self,
        job_id: str,
        status: str,
        progress_percentage: Optional[int] = None,
        current_phase: Optional[str] = None,
        current_step: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update job status and progress.

        Args:
            job_id: Job identifier
            status: New status
            progress_percentage: Optional progress update
            current_phase: Optional phase update
            current_step: Optional step description
            error_message: Optional error message

        Returns:
            Updated job or None
        """
        updates = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }

        if progress_percentage is not None:
            updates["progress_percentage"] = progress_percentage
        if current_phase is not None:
            updates["current_phase"] = current_phase
        if current_step is not None:
            updates["current_step"] = current_step
        if error_message is not None:
            updates["error_message"] = error_message

        # Set completed_at for terminal states
        if status in ["completed", "failed", "cancelled"]:
            updates["completed_at"] = datetime.utcnow().isoformat() + "Z"

        return await self.update_job(job_id, updates)

    async def set_checkpoint(
        self,
        job_id: str,
        checkpoint_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Set checkpoint data for job approval.

        Args:
            job_id: Job identifier
            checkpoint_data: Checkpoint details

        Returns:
            Updated job or None
        """
        return await self.update_job(job_id, {
            "status": "paused",
            "checkpoint_data": checkpoint_data
        })

    async def clear_checkpoint(
        self,
        job_id: str,
        status: str = "processing"
    ) -> Optional[Dict[str, Any]]:
        """
        Clear checkpoint and resume job.

        Args:
            job_id: Job identifier
            status: Status to set after clearing (default: processing)

        Returns:
            Updated job or None
        """
        return await self.update_job(job_id, {
            "status": status,
            "checkpoint_data": None
        })

    async def set_result(
        self,
        job_id: str,
        result: Dict[str, Any],
        pr_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Set job result and PR URL.

        Args:
            job_id: Job identifier
            result: Job result data
            pr_url: Optional PR URL

        Returns:
            Updated job or None
        """
        updates = {
            "status": "completed",
            "progress_percentage": 100,
            "current_phase": "COMPLETE",
            "current_step": "Migration completed successfully",
            "result": result,
            "completed_at": datetime.utcnow().isoformat() + "Z"
        }

        if pr_url:
            updates["pr_url"] = pr_url

        return await self.update_job(job_id, updates)

    async def delete_job(self, job_id: str) -> bool:
        """
        Delete a job by job_id.

        Args:
            job_id: Job identifier

        Returns:
            True if deleted
        """
        result = await self.collection.delete_one({"job_id": job_id})
        return result.deleted_count > 0

    async def get_jobs_by_status(
        self,
        status: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get jobs with a specific status (for admin/worker use).

        Args:
            status: Job status to filter
            limit: Maximum results

        Returns:
            List of jobs
        """
        return await self.get_all(
            filter={"status": status},
            limit=limit,
            sort=[("created_at", 1)]  # Oldest first (FIFO for processing)
        )

    async def get_jobs_with_checkpoints(
        self,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get jobs waiting at checkpoints.

        Args:
            limit: Maximum results

        Returns:
            List of jobs with checkpoint_data
        """
        return await self.get_all(
            filter={
                "status": "paused",
                "checkpoint_data": {"$ne": None}
            },
            limit=limit,
            sort=[("updated_at", 1)]  # Oldest waiting first
        )
