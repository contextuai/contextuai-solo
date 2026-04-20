"""
ScheduledJob Repository — CRUD for cron-scheduled jobs.

Follows the BaseRepository pattern used by other repositories. Documents
are persisted in the ``scheduled_jobs`` collection. The ``_id`` column
holds the same UUID as the ``id`` response field; this keeps it simple
to correlate DB docs with APScheduler job IDs.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class ScheduledJobRepository(BaseRepository):
    """Repository for scheduled job documents."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "scheduled_jobs")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_job(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new scheduled job with tracking defaults."""
        job_id = data.get("id") or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        doc = {
            "_id": job_id,
            "name": data["name"],
            "job_type": data["job_type"],
            "cron": data["cron"],
            "timezone": data.get("timezone", "UTC"),
            "enabled": data.get("enabled", True),
            "channel_id": data.get("channel_id"),
            "content": data.get("content"),
            "title": data.get("title"),
            "metadata": data.get("metadata"),
            "crew_id": data.get("crew_id"),
            "crew_input": data.get("crew_input"),
            "last_run_at": None,
            "last_run_status": None,
            "last_run_error": None,
            "next_run_at": data.get("next_run_at"),
            "run_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(doc)
        doc["id"] = doc.pop("_id")
        return doc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single scheduled job by ID."""
        doc = await self.collection.find_one({"_id": job_id})
        if doc:
            doc["id"] = doc.pop("_id")
        return doc

    async def list_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List all scheduled jobs (most recent first)."""
        cursor = (
            self.collection.find({})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs: List[Dict[str, Any]] = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            docs.append(doc)
        return docs

    async def list_enabled(self) -> List[Dict[str, Any]]:
        """List all enabled scheduled jobs (used on startup to rehydrate)."""
        cursor = self.collection.find({"enabled": True})
        docs: List[Dict[str, Any]] = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            docs.append(doc)
        return docs

    async def count_all(self) -> int:
        return await self.collection.count_documents({})

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_job(
        self, job_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Partial update for a scheduled job."""
        clean = {k: v for k, v in updates.items() if v is not None}
        if not clean:
            return await self.get_job(job_id)
        clean["updated_at"] = datetime.utcnow().isoformat()
        await self.collection.update_one({"_id": job_id}, {"$set": clean})
        return await self.get_job(job_id)

    async def record_run(
        self,
        job_id: str,
        status: str,
        error: Optional[str] = None,
        next_run_at: Optional[str] = None,
    ) -> None:
        """Record the result of an execution and bump ``run_count``."""
        now = datetime.utcnow().isoformat()
        set_fields: Dict[str, Any] = {
            "last_run_at": now,
            "last_run_status": status,
            "last_run_error": error,
            "updated_at": now,
        }
        if next_run_at is not None:
            set_fields["next_run_at"] = next_run_at
        await self.collection.update_one(
            {"_id": job_id},
            {"$set": set_fields, "$inc": {"run_count": 1}},
        )

    async def set_next_run_at(
        self, job_id: str, next_run_at: Optional[str]
    ) -> None:
        await self.collection.update_one(
            {"_id": job_id},
            {"$set": {"next_run_at": next_run_at}},
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_job(self, job_id: str) -> bool:
        """Delete a scheduled job. Returns True if removed."""
        result = await self.collection.delete_one({"_id": job_id})
        return result.deleted_count > 0
