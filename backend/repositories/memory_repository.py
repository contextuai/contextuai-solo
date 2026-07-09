"""Fact persistence — text + optional 384-dim embedding, inline JSON envelope.

Mirrors ``repositories/chunk_repository.py``: a thin ``BaseRepository``
subclass over a hard-coded collection name. The table auto-creates on first
write — no migration needed.
"""
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class MemoryRepository(BaseRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "memory_facts")

    async def list_by_scope(
        self, scopes: List[str], statuses: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Raw documents (preserves `_id` + `embedding`) for the given scopes."""
        query: Dict[str, Any] = {"scope": {"$in": scopes}}
        if statuses:
            query["status"] = {"$in": statuses}
        cursor = self.collection.find(query)
        return await cursor.to_list(length=None)

    async def list_all(self) -> List[Dict[str, Any]]:
        """Every fact, raw (preserves `_id` + `embedding`)."""
        cursor = self.collection.find({})
        return await cursor.to_list(length=None)
