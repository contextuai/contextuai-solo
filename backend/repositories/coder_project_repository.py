"""Coder Project Repository — CRUD on the ``coder_projects`` collection.

Solo single-user variant. Mirrors the pattern used by
``CloudProviderRepository`` and ``AutomationRepository`` (UUID-keyed
``project_id`` plus the BaseRepository ``_id`` for direct lookups).
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository


class CoderProjectRepository(BaseRepository):
    """Repository for the ``coder_projects`` collection."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "coder_projects")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        name: str,
        folder_path: str,
        template_id: Optional[str] = None,
        runtime: str = "auto",
        chat_thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = {
            "project_id": str(uuid.uuid4()),
            "name": name,
            "folder_path": folder_path,
            "template_id": template_id,
            "runtime": runtime,
            "trusted": False,
            "network_policy": "block",
            "chat_thread_id": chat_thread_id,
            "last_run_at": None,
            "status": "created",
        }
        return await super().create(data)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        row = await self.get_one({"project_id": project_id})
        if row:
            return row
        try:
            return await super().get_by_id(project_id)
        except ValueError:
            return None

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.get_all(
            filter={},
            skip=offset,
            limit=limit,
            sort=[("created_at", -1)],
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(
        self,
        project_id: str,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        row = await self.get_one({"project_id": project_id})
        if row:
            return await super().update(row["id"], data)
        try:
            return await super().update(project_id, data)
        except ValueError:
            return None

    async def set_trusted(
        self, project_id: str, trusted: bool
    ) -> Optional[Dict[str, Any]]:
        update: Dict[str, Any] = {"trusted": trusted}
        # Promote status when first trusted; revert to "created" when revoked
        # only if the project isn't currently running/stopped.
        if trusted:
            update["status"] = "trusted"
        return await self.update(project_id, update)

    async def set_status(
        self, project_id: str, status: str
    ) -> Optional[Dict[str, Any]]:
        return await self.update(project_id, {"status": status})

    async def update_last_run(
        self, project_id: str, run_at: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        return await self.update(
            project_id,
            {"last_run_at": run_at or datetime.utcnow().isoformat()},
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, project_id: str) -> bool:
        row = await self.get_one({"project_id": project_id})
        if row:
            return await super().delete(row["id"])
        try:
            return await super().delete(project_id)
        except ValueError:
            return False
