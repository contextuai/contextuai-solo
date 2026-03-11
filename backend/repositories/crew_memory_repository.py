"""
Crew Memory Repository — MongoDB data access for crew memory entries.

Stores persistent context that carries across crew runs: facts, decisions,
preferences, and agent-specific knowledge.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class CrewMemoryRepository(BaseRepository):
    """Repository for crew memory entries."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "crew_memories")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def add_memory(
        self,
        crew_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Add a new memory entry for a crew."""
        now = datetime.utcnow().isoformat()
        doc = {
            "memory_id": str(uuid.uuid4()),
            "crew_id": crew_id,
            "category": data.get("category", "general"),
            "key": data.get("key"),
            "content": data.get("content"),
            "source_run_id": data.get("source_run_id"),
            "source_agent_id": data.get("source_agent_id"),
            "source_agent_name": data.get("source_agent_name"),
            "tags": data.get("tags", []),
            "importance": data.get("importance", "normal"),
            "ttl_hours": data.get("ttl_hours"),
            "expires_at": data.get("expires_at"),
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["id"] = str(doc.pop("_id"))
        return doc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_memory_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a single memory entry."""
        doc = await self.collection.find_one({"memory_id": memory_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def get_crew_memories(
        self,
        crew_id: str,
        category: Optional[str] = None,
        agent_id: Optional[str] = None,
        importance: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get memories for a crew with optional filters."""
        query: Dict[str, Any] = {"crew_id": crew_id}
        if category:
            query["category"] = category
        if agent_id:
            query["source_agent_id"] = agent_id
        if importance:
            query["importance"] = importance

        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)

        return docs, total

    async def search_memories(
        self,
        crew_id: str,
        search_text: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search memory entries by content text (simple regex)."""
        import re
        query = {
            "crew_id": crew_id,
            "$or": [
                {"content": re.compile(re.escape(search_text), re.IGNORECASE)},
                {"key": re.compile(re.escape(search_text), re.IGNORECASE)},
                {"tags": re.compile(re.escape(search_text), re.IGNORECASE)},
            ],
        }
        cursor = self.collection.find(query).sort("created_at", -1).limit(limit)
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)
        return docs

    async def get_context_for_run(
        self,
        crew_id: str,
        max_entries: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get the most relevant memories to inject as context for a new run.

        Priorities: high importance first, then most recent.
        Excludes expired entries.
        """
        now = datetime.utcnow().isoformat()

        # Exclude expired memories
        query = {
            "crew_id": crew_id,
            "$or": [
                {"expires_at": None},
                {"expires_at": {"$gt": now}},
            ],
        }

        cursor = (
            self.collection.find(query)
            .sort([("importance", -1), ("created_at", -1)])
            .limit(max_entries)
        )
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)
        return docs

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_memory(
        self, memory_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a memory entry."""
        data["updated_at"] = datetime.utcnow().isoformat()
        result = await self.collection.find_one_and_update(
            {"memory_id": memory_id},
            {"$set": data},
            return_document=True,
        )
        if result:
            result["id"] = str(result.pop("_id"))
        return result

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_memory(self, memory_id: str) -> bool:
        """Hard-delete a single memory entry."""
        result = await self.collection.delete_one({"memory_id": memory_id})
        return result.deleted_count > 0

    async def clear_crew_memories(self, crew_id: str) -> int:
        """Delete all memories for a crew. Returns count deleted."""
        result = await self.collection.delete_many({"crew_id": crew_id})
        return result.deleted_count

    async def cleanup_expired(self) -> int:
        """Remove expired memory entries across all crews."""
        now = datetime.utcnow().isoformat()
        result = await self.collection.delete_many({
            "expires_at": {"$lte": now, "$ne": None},
        })
        return result.deleted_count
