"""
Audit Repository — MongoDB operations for the audit trail.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class AuditRepository(BaseRepository):
    """Repository for audit event storage and querying."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "audit_logs")

    async def log_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a single audit event."""
        event.setdefault("timestamp", datetime.utcnow().isoformat())
        return await self.create(event)

    async def query(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        ip_address: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple:
        """
        Query audit logs with filters.

        Returns:
            (events, total_count)
        """
        query: Dict[str, Any] = {}

        if user_id:
            query["user_id"] = user_id
        if action:
            # Support prefix matching (e.g. "auth." matches all auth events)
            if action.endswith(".*"):
                query["action"] = {"$regex": f"^{action[:-2]}"}
            else:
                query["action"] = action
        if severity:
            query["severity"] = severity
        if resource_type:
            query["resource_type"] = resource_type
        if resource_id:
            query["resource_id"] = resource_id
        if ip_address:
            query["ip_address"] = ip_address

        # Date range
        if from_date or to_date:
            date_filter: Dict[str, Any] = {}
            if from_date:
                date_filter["$gte"] = from_date.isoformat()
            if to_date:
                date_filter["$lte"] = to_date.isoformat()
            query["timestamp"] = date_filter

        total = await self.count(query)

        skip = (page - 1) * page_size
        cursor = (
            self.collection
            .find(query)
            .sort("timestamp", -1)
            .skip(skip)
            .limit(page_size)
        )

        events = []
        async for doc in cursor:
            events.append(self._convert_id(doc))

        return events, total
