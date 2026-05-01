"""CRUD over the `kb_folder_sources` collection.

One row per mapped folder. The orchestrator (`personal_docs_service`) walks
each mapping on demand or on a schedule to ingest new/changed files.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository

_INTERVALS = {"1h": 3600, "6h": 6 * 3600, "24h": 24 * 3600}


class FolderSourceRepository(BaseRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "kb_folder_sources")

    async def create_source(
        self,
        *,
        kb_id: str,
        path: str,
        label: str,
        include_globs: List[str],
        exclude_globs: List[str],
        schedule: str,
        max_file_bytes: int,
        max_files: int,
        max_depth: int,
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        doc = {
            "_id": str(uuid.uuid4()),
            "kb_id": kb_id,
            "path": path,
            "label": label,
            "include_globs": include_globs,
            "exclude_globs": exclude_globs,
            "schedule": schedule,
            "max_file_bytes": max_file_bytes,
            "max_files": max_files,
            "max_depth": max_depth,
            "status": "active",
            "last_sync_at": None,
            "last_sync_job_id": None,
            "file_count": 0,
            "byte_count": 0,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(doc)
        return doc

    async def list_for_kb(self, kb_id: str) -> List[Dict[str, Any]]:
        return await self.get_all(
            filter={"kb_id": kb_id}, limit=200, sort=[("created_at", -1)]
        )

    async def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"_id": source_id})

    async def update_source(self, source_id: str, update: Dict[str, Any]) -> None:
        update = {**update, "updated_at": datetime.utcnow().isoformat()}
        await self.collection.update_one({"_id": source_id}, {"$set": update})

    async def delete_source(self, source_id: str) -> None:
        await self.collection.delete_one({"_id": source_id})

    async def delete_for_kb(self, kb_id: str) -> int:
        return await self.delete_many({"kb_id": kb_id})

    async def list_due_for_sync(self) -> List[Dict[str, Any]]:
        """Return active mappings whose schedule != manual and are due.

        Returns raw documents (preserves `_id`) — internal callers pass the
        result straight into the orchestrator which keys off `_id`.
        """
        now = datetime.utcnow()
        all_sources = await self.collection.find(
            {"status": "active"}
        ).to_list(length=500)
        due: List[Dict[str, Any]] = []
        for s in all_sources:
            sched = s.get("schedule", "manual")
            if sched not in _INTERVALS:
                continue
            last = s.get("last_sync_at")
            if last is None:
                due.append(s)
                continue
            try:
                last_dt = datetime.fromisoformat(last)
            except (TypeError, ValueError):
                due.append(s)
                continue
            if now - last_dt >= timedelta(seconds=_INTERVALS[sched]):
                due.append(s)
        return due
