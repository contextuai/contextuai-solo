"""CRUD + status transitions over the `kb_index_jobs` collection.

One row per sync run. Drives the progress UI and lets us mark jobs that
were interrupted by a backend crash so they can be re-attempted.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository

_ACTIVE_STATUSES = ["queued", "walking", "awaiting_confirmation", "running"]


class IndexJobRepository(BaseRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "kb_index_jobs")

    async def create_job(
        self, *, kb_id: str, source_id: str, kind: str
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        doc = {
            "_id": str(uuid.uuid4()),
            "kb_id": kb_id,
            "source_id": source_id,
            "kind": kind,
            "status": "queued",
            "files_total": 0,
            "files_done": 0,
            "files_added": 0,
            "files_updated": 0,
            "files_removed": 0,
            "files_skipped": 0,
            "bytes_total": 0,
            "bytes_done": 0,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "cancel_requested": False,
            "created_at": now,
        }
        await self.collection.insert_one(doc)
        return doc

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"_id": job_id})

    async def patch(self, job_id: str, update: Dict[str, Any]) -> None:
        await self.collection.update_one({"_id": job_id}, {"$set": update})

    async def request_cancel(self, job_id: str) -> None:
        await self.patch(job_id, {"cancel_requested": True})

    async def running_for_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one(
            {"source_id": source_id, "status": {"$in": _ACTIVE_STATUSES}}
        )

    async def list_for_source(
        self, source_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        return await self.get_all(
            filter={"source_id": source_id},
            limit=limit,
            sort=[("created_at", -1)],
        )

    async def reset_orphans(self) -> int:
        """Mark `walking`/`running` jobs as interrupted (called on startup)."""
        return await self.update_many(
            {"status": {"$in": ["walking", "running"]}},
            {
                "status": "error",
                "error": "interrupted",
                "finished_at": datetime.utcnow().isoformat(),
            },
        )
