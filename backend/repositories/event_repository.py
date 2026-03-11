"""
Event Repository — MongoDB data access for event subscriptions and delivery logs.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class EventSubscriptionRepository(BaseRepository):
    """Repository for event subscriptions."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "event_subscriptions")

    async def create_subscription(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new event subscription."""
        now = datetime.utcnow().isoformat()
        doc = {
            "subscription_id": str(uuid.uuid4()),
            "status": "active",
            "delivery_count": 0,
            "failure_count": 0,
            "last_delivered_at": None,
            "deleted_at": None,
            "created_at": now,
            "updated_at": now,
            **data,
        }
        await self.collection.insert_one(doc)
        doc["id"] = str(doc.pop("_id"))
        return doc

    async def get_by_subscription_id(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get subscription by subscription_id."""
        doc = await self.collection.find_one({
            "subscription_id": subscription_id,
            "deleted_at": None,
        })
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def get_user_subscriptions(
        self,
        user_id: str,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get all subscriptions for a user."""
        query: Dict[str, Any] = {"user_id": user_id, "deleted_at": None}
        if status:
            query["status"] = status
        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)
        return docs, total

    async def get_active_subscriptions_for_event(
        self, event_type: str
    ) -> List[Dict[str, Any]]:
        """Get all active subscriptions matching an event type (or wildcard)."""
        query = {
            "status": "active",
            "deleted_at": None,
            "$or": [
                {"event_types": event_type},
                {"event_types": "*"},
            ],
        }
        cursor = self.collection.find(query)
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)
        return docs

    async def update_subscription(
        self, subscription_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a subscription."""
        data["updated_at"] = datetime.utcnow().isoformat()
        result = await self.collection.find_one_and_update(
            {"subscription_id": subscription_id, "deleted_at": None},
            {"$set": data},
            return_document=True,
        )
        if result:
            result["id"] = str(result.pop("_id"))
        return result

    async def record_delivery(self, subscription_id: str, success: bool) -> None:
        """Increment delivery/failure count."""
        update = {
            "$inc": {"delivery_count": 1} if success else {"failure_count": 1},
            "$set": {"last_delivered_at": datetime.utcnow().isoformat()},
        }
        await self.collection.update_one(
            {"subscription_id": subscription_id},
            update,
        )

    async def soft_delete(self, subscription_id: str) -> bool:
        """Soft-delete a subscription."""
        result = await self.collection.update_one(
            {"subscription_id": subscription_id, "deleted_at": None},
            {"$set": {
                "deleted_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }},
        )
        return result.modified_count > 0


class EventDeliveryRepository(BaseRepository):
    """Repository for event delivery logs."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "event_deliveries")

    async def log_delivery(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Log an event delivery attempt."""
        now = datetime.utcnow().isoformat()
        doc = {
            "delivery_id": str(uuid.uuid4()),
            "created_at": now,
            **data,
        }
        await self.collection.insert_one(doc)
        doc["id"] = str(doc.pop("_id"))
        return doc

    async def get_delivery_logs(
        self,
        subscription_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get delivery logs for a subscription."""
        cursor = (
            self.collection.find({"subscription_id": subscription_id})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)
        return docs
