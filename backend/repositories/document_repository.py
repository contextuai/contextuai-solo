"""Document metadata persistence (one row per uploaded file in a KB)."""
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class DocumentRepository(BaseRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "kb_documents")

    async def list_for_kb(self, kb_id: str) -> List[Dict[str, Any]]:
        return await self.get_all(
            filter={"kb_id": kb_id}, limit=500, sort=[("created_at", -1)]
        )

    async def delete_for_kb(self, kb_id: str) -> int:
        return await self.delete_many({"kb_id": kb_id})

    async def set_status(
        self,
        doc_id: str,
        status: str,
        error: Optional[str] = None,
        page_count: Optional[int] = None,
        chunk_count: Optional[int] = None,
    ) -> None:
        update: Dict[str, Any] = {"status": status}
        if error is not None:
            update["error"] = error
        if page_count is not None:
            update["page_count"] = page_count
        if chunk_count is not None:
            update["chunk_count"] = chunk_count
        await self.collection.update_one({"_id": doc_id}, {"$set": update})
