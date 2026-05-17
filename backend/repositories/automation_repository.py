"""
Automation Repository — CRUD on the ``automations`` collection.

Solo single-user variant: drops user_id-based filtering. The aggregator
collection still stores a ``user_id`` field of "desktop" for forward-compat
with the enterprise schema.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository

DESKTOP_USER_ID = "desktop"


class AutomationRepository(BaseRepository):
    """Repository for the ``automations`` collection (single-user)."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "automations")

    async def create(
        self,
        name: str,
        description: str,
        prompt_template: str,
        trigger_type: str = "manual",
        trigger_config: Optional[Dict[str, Any]] = None,
        status: str = "draft",
        execution_mode: str = "smart",
        personas_detected: Optional[List[str]] = None,
        output_actions: Optional[List[Dict[str, Any]]] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = {
            "automation_id": str(uuid.uuid4()),
            "user_id": DESKTOP_USER_ID,
            "name": name,
            "description": description,
            "prompt_template": prompt_template,
            "trigger_type": trigger_type,
            "trigger_config": trigger_config,
            "status": status,
            "execution_mode": execution_mode,
            "personas_detected": personas_detected or [],
            "run_count": 0,
            "last_run": None,
            "output_actions": output_actions or [],
            "model_id": model_id,
        }
        return await super().create(data)

    async def get_by_id(self, automation_id: str) -> Optional[Dict[str, Any]]:
        row = await self.get_one({"automation_id": automation_id})
        if row:
            return row
        try:
            return await super().get_by_id(automation_id)
        except ValueError:
            return None

    async def list_all(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        filter_q: Dict[str, Any] = {}
        if status:
            filter_q["status"] = status
        return await self.get_all(
            filter=filter_q,
            skip=offset,
            limit=limit,
            sort=[("created_at", -1)],
        )

    async def update(
        self, automation_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        row = await self.get_one({"automation_id": automation_id})
        if row:
            return await super().update(row["id"], data)
        try:
            return await super().update(automation_id, data)
        except ValueError:
            return None

    async def delete(self, automation_id: str) -> bool:
        row = await self.get_one({"automation_id": automation_id})
        if row:
            return await super().delete(row["id"])
        try:
            return await super().delete(automation_id)
        except ValueError:
            return False

    async def increment_run_count(
        self, automation_id: str, last_run: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        row = await self.get_by_id(automation_id)
        if not row:
            return None
        new_count = (row.get("run_count") or 0) + 1
        return await super().update(
            row["id"],
            {
                "run_count": new_count,
                "last_run": last_run or datetime.utcnow().isoformat(),
            },
        )

    async def count_by_status(self) -> Dict[str, int]:
        active = await self.count({"status": "active"})
        inactive = await self.count({"status": "inactive"})
        draft = await self.count({"status": "draft"})
        return {
            "active": active,
            "inactive": inactive,
            "draft": draft,
            "total": active + inactive + draft,
        }
