"""Knowledge Base metadata persistence."""
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class KnowledgeBaseRepository(BaseRepository):
    """One row per knowledge base. Counts are denormalised for fast list views."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "knowledge_bases")

    async def list_all(self) -> List[Dict[str, Any]]:
        return await self.get_all(limit=200, sort=[("created_at", -1)])

    async def update_counts(self, kb_id: str, doc_count: int, chunk_count: int) -> None:
        await self.collection.update_one(
            {"_id": kb_id},
            {"$set": {"doc_count": doc_count, "chunk_count": chunk_count}},
        )
