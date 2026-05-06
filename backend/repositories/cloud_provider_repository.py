"""
Cloud Provider Repository — CRUD on the ``cloud_providers`` collection.

Stores user-supplied credentials for cloud LLM providers (Anthropic, OpenAI,
Google, AWS Bedrock). One row per provider type — `get_by_type` lets the
service layer upsert rather than create duplicates.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository


class CloudProviderRepository(BaseRepository):
    """Repository for the ``cloud_providers`` collection."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "cloud_providers")

    async def create(
        self,
        provider_type: str,
        display_name: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        data = {
            "provider_id": str(uuid.uuid4()),
            "provider_type": provider_type,
            "display_name": display_name,
            "connected": False,
            "last_tested_at": None,
            "last_test_status": None,
            "last_test_error": None,
            "config": config or {},
        }
        return await super().create(data)

    async def list_all(self) -> List[Dict[str, Any]]:
        return await self.get_all(
            filter={},
            limit=100,
            sort=[("created_at", -1)],
        )

    async def get_by_id(self, provider_id: str) -> Optional[Dict[str, Any]]:
        row = await self.get_one({"provider_id": provider_id})
        if row:
            return row
        try:
            return await super().get_by_id(provider_id)
        except ValueError:
            return None

    async def get_by_type(self, provider_type: str) -> Optional[Dict[str, Any]]:
        return await self.get_one({"provider_type": provider_type})

    async def update(
        self,
        provider_id: str,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        row = await self.get_one({"provider_id": provider_id})
        if row:
            return await super().update(row["id"], data)
        try:
            return await super().update(provider_id, data)
        except ValueError:
            return None

    async def delete(self, provider_id: str) -> bool:
        row = await self.get_one({"provider_id": provider_id})
        if row:
            return await super().delete(row["id"])
        try:
            return await super().delete(provider_id)
        except ValueError:
            return False

    async def set_test_result(
        self,
        provider_id: str,
        ok: bool,
        error: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Persist the outcome of a connection test.

        ``connected`` is set to True on success, False on failure.
        """
        return await self.update(
            provider_id,
            {
                "last_tested_at": datetime.utcnow().isoformat(),
                "last_test_status": "ok" if ok else "failed",
                "last_test_error": None if ok else (error or "unknown error"),
                "connected": bool(ok),
            },
        )
