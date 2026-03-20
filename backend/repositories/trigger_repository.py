"""
Trigger Repository — CRUD for channel-crew trigger configurations.

Each trigger links a channel (Telegram, Discord, etc.) to a Crew or
direct-AI response.  Triggers support cooldowns, approval requirements,
and enable/disable toggling.
"""

import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class TriggerRepository:
    """Async CRUD for the ``channel_triggers`` collection."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["channel_triggers"]

    async def create(self, trigger: Dict[str, Any]) -> Dict[str, Any]:
        trigger_id = trigger.get("trigger_id") or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        doc = {
            "_id": trigger_id,
            "trigger_id": trigger_id,
            "channel_type": trigger["channel_type"],
            "channel_id": trigger.get("channel_id", "*"),  # * = all chats
            "crew_id": trigger.get("crew_id"),  # None = direct AI
            "agent_id": trigger.get("agent_id"),  # optional single agent
            "enabled": trigger.get("enabled", True),
            "approval_required": trigger.get("approval_required", False),
            "cooldown_seconds": trigger.get("cooldown_seconds", 0),
            "last_fired_at": None,
            "fire_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get_by_id(self, trigger_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.collection.find_one({"trigger_id": trigger_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def list_all(
        self,
        channel_type: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if channel_type:
            query["channel_type"] = channel_type
        if enabled_only:
            query["enabled"] = True
        cursor = self.collection.find(query).sort("created_at", -1)
        docs = []
        async for doc in cursor:
            doc.pop("_id", None)
            docs.append(doc)
        return docs

    async def find_for_channel(
        self,
        channel_type: str,
        channel_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Find the best matching enabled trigger for a channel.

        Priority: exact channel_id match > wildcard (*).
        """
        # Exact match first
        doc = await self.collection.find_one({
            "channel_type": channel_type,
            "channel_id": channel_id,
            "enabled": True,
        })
        if doc:
            doc.pop("_id", None)
            return doc

        # Wildcard
        doc = await self.collection.find_one({
            "channel_type": channel_type,
            "channel_id": "*",
            "enabled": True,
        })
        if doc:
            doc.pop("_id", None)
            return doc

        return None

    async def update(self, trigger_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        updates["updated_at"] = datetime.utcnow().isoformat()
        await self.collection.update_one(
            {"trigger_id": trigger_id},
            {"$set": updates},
        )
        return await self.get_by_id(trigger_id)

    async def record_fire(self, trigger_id: str) -> None:
        """Record that a trigger was fired (for cooldown tracking)."""
        await self.collection.update_one(
            {"trigger_id": trigger_id},
            {
                "$set": {
                    "last_fired_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                },
                "$inc": {"fire_count": 1},
            },
        )

    async def delete(self, trigger_id: str) -> bool:
        result = await self.collection.delete_one({"trigger_id": trigger_id})
        return result.deleted_count > 0
