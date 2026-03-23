"""
Blueprint Repository — MongoDB data access for blueprints.

Follows the BaseRepository pattern used by crews and workspace agents.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class BlueprintRepository(BaseRepository):
    """Repository for blueprint documents."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "blueprints")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_blueprint(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new blueprint."""
        now = datetime.utcnow().isoformat()
        doc = {
            "blueprint_id": str(uuid.uuid4()),
            "user_id": user_id,
            "source": "custom",
            "is_system": False,
            "usage_count": 0,
            "deleted_at": None,
            "created_at": now,
            "updated_at": now,
            **data,
        }
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_blueprint_id(self, blueprint_id: str) -> Optional[Dict[str, Any]]:
        """Get blueprint by blueprint_id, excluding soft-deleted."""
        doc = await self.collection.find_one({"blueprint_id": blueprint_id, "deleted_at": None})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def get_user_blueprints(
        self,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get blueprints with optional filters."""
        query: Dict[str, Any] = {"deleted_at": None}
        if user_id and source == "custom":
            query["user_id"] = user_id
        if category:
            query["category"] = category
        if source:
            query["source"] = source
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
                {"tags": {"$regex": search, "$options": "i"}},
            ]

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

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_blueprint(self, blueprint_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a blueprint by blueprint_id."""
        data["updated_at"] = datetime.utcnow().isoformat()
        result = await self.collection.find_one_and_update(
            {"blueprint_id": blueprint_id, "deleted_at": None},
            {"$set": data},
            return_document=True,
        )
        if result:
            result["id"] = str(result.pop("_id"))
        return result

    async def increment_usage(self, blueprint_id: str) -> None:
        """Increment usage count for a blueprint."""
        await self.collection.update_one(
            {"blueprint_id": blueprint_id},
            {
                "$inc": {"usage_count": 1},
                "$set": {"updated_at": datetime.utcnow().isoformat()},
            },
        )

    # ------------------------------------------------------------------
    # Soft Delete
    # ------------------------------------------------------------------

    async def soft_delete_blueprint(self, blueprint_id: str) -> bool:
        """Soft-delete a blueprint."""
        result = await self.collection.update_one(
            {"blueprint_id": blueprint_id, "deleted_at": None},
            {"$set": {
                "deleted_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }},
        )
        return result.modified_count > 0
