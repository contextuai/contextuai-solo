"""
Approval Repository — CRUD for the human-in-the-loop approval queue.

Pending approvals are created when a trigger has ``approval_required=True``.
Each approval contains the draft AI response waiting for human review.
"""

import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class ApprovalRepository:
    """Async CRUD for the ``approval_queue`` collection."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db["approval_queue"]

    async def create(self, approval: Dict[str, Any]) -> Dict[str, Any]:
        approval_id = approval.get("approval_id") or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        doc = {
            "_id": approval_id,
            "approval_id": approval_id,
            "trigger_id": approval.get("trigger_id"),
            "channel_type": approval["channel_type"],
            "channel_id": approval["channel_id"],
            "sender_name": approval.get("sender_name", "Unknown"),
            "sender_id": approval.get("sender_id", ""),
            "inbound_text": approval["inbound_text"],
            "draft_response": approval["draft_response"],
            "final_response": None,
            "session_id": approval.get("session_id"),
            "status": "pending",  # pending | approved | rejected | edited
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get_by_id(self, approval_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.collection.find_one({"approval_id": approval_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def list_pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = (
            self.collection.find({"status": "pending"})
            .sort("created_at", -1)
            .limit(limit)
        )
        docs = []
        async for doc in cursor:
            doc.pop("_id", None)
            docs.append(doc)
        return docs

    async def list_all(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status
        cursor = self.collection.find(query).sort("created_at", -1).limit(limit)
        docs = []
        async for doc in cursor:
            doc.pop("_id", None)
            docs.append(doc)
        return docs

    async def approve(
        self,
        approval_id: str,
        reviewed_by: str = "desktop-user",
        edited_response: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        updates: Dict[str, Any] = {
            "status": "edited" if edited_response else "approved",
            "reviewed_by": reviewed_by,
            "reviewed_at": now,
            "updated_at": now,
        }
        if edited_response:
            updates["final_response"] = edited_response
        else:
            # Use draft as final
            doc = await self.get_by_id(approval_id)
            if doc:
                updates["final_response"] = doc["draft_response"]

        await self.collection.update_one(
            {"approval_id": approval_id},
            {"$set": updates},
        )
        return await self.get_by_id(approval_id)

    async def reject(
        self,
        approval_id: str,
        reviewed_by: str = "desktop-user",
    ) -> Optional[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        await self.collection.update_one(
            {"approval_id": approval_id},
            {
                "$set": {
                    "status": "rejected",
                    "reviewed_by": reviewed_by,
                    "reviewed_at": now,
                    "updated_at": now,
                }
            },
        )
        return await self.get_by_id(approval_id)

    async def count_pending(self) -> int:
        return await self.collection.count_documents({"status": "pending"})
