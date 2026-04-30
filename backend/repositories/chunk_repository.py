"""Chunk persistence — text + 384-dim embedding vector stored as JSON array."""
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class ChunkRepository(BaseRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "kb_chunks")

    async def list_for_kb(self, kb_id: str) -> List[Dict[str, Any]]:
        cursor = self.collection.find({"kb_id": kb_id})
        return await cursor.to_list(length=None)

    async def delete_for_kb(self, kb_id: str) -> int:
        return await self.delete_many({"kb_id": kb_id})

    async def delete_for_document(self, doc_id: str) -> int:
        return await self.delete_many({"doc_id": doc_id})

    async def count_for_kb(self, kb_id: str) -> int:
        return await self.count({"kb_id": kb_id})
