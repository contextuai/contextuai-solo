"""Coder Agent Role Repository — CRUD on the ``coder_agent_roles`` collection.

Mirrors the pattern of ``CoderProjectRepository``. Each row stores one
specialist role (Coder, Reviewer, Security, etc.) linked to a project via
``project_id``. Rows are sorted by ``order`` when listing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository


class CoderAgentRoleRepository(BaseRepository):
    """Repository for the ``coder_agent_roles`` collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db, "coder_agent_roles")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(self, role: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new role row. Caller must supply all required fields."""
        data = {
            "role_id": role.get("role_id") or str(uuid.uuid4()),
            "project_id": role["project_id"],
            "role_kind": role["role_kind"],
            "display_name": role["display_name"],
            "system_prompt": role["system_prompt"],
            "model_id": role["model_id"],
            "temperature": role.get("temperature", 0.7),
            "max_tokens": role.get("max_tokens", 4096),
            "enabled": role.get("enabled", True),
            "order": role["order"],
        }
        return await super().create(data)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        """Return all roles for *project_id*, sorted by ``order`` ascending."""
        rows = await self.get_all(
            filter={"project_id": project_id},
            limit=1000,
            sort=[("order", 1)],
        )
        return rows

    async def get_by_role_id(self, role_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single role by its ``role_id`` UUID."""
        return await self.get_one({"role_id": role_id})

    async def max_order_for_project(self, project_id: str) -> int:
        """Return the current maximum ``order`` value for the project, or -1."""
        rows = await self.list_for_project(project_id)
        if not rows:
            return -1
        return max(r.get("order", 0) for r in rows)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(self, role_id: str, partial: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Partial-update a role by its ``role_id``."""
        row = await self.get_by_role_id(role_id)
        if not row:
            return None
        return await super().update(row["id"], partial)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, role_id: str) -> bool:
        """Delete a role by its ``role_id``. Returns True if deleted."""
        row = await self.get_by_role_id(role_id)
        if not row:
            return False
        return await super().delete(row["id"])

    async def delete_for_project(self, project_id: str) -> int:
        """Delete all roles for a project. Returns number of rows removed."""
        return await self.delete_many({"project_id": project_id})
