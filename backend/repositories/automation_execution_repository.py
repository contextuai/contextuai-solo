"""
Automation Execution Repository — CRUD on the ``automation_executions``
collection. Stores per-run history including step-by-step traces.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository

DESKTOP_USER_ID = "desktop"


class AutomationExecutionRepository(BaseRepository):
    """Repository for the ``automation_executions`` collection."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "automation_executions")

    async def create_execution(
        self,
        automation_id: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        data = {
            "execution_id": str(uuid.uuid4()),
            "automation_id": automation_id,
            "user_id": DESKTOP_USER_ID,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "duration_ms": None,
            "parameters": parameters or {},
            "steps": [],
            "result": None,
            "error": None,
            "total_steps": 0,
            "successful_steps": 0,
            "failed_steps": 0,
        }
        return await super().create(data)

    async def get_by_id(self, execution_id: str) -> Optional[Dict[str, Any]]:
        row = await self.get_one({"execution_id": execution_id})
        if row:
            return row
        try:
            return await super().get_by_id(execution_id)
        except ValueError:
            return None

    async def update_execution(
        self,
        execution_id: str,
        status: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
        output_results: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        row = await self.get_by_id(execution_id)
        if not row:
            return None

        update: Dict[str, Any] = {"status": status}

        if status in ("success", "failed", "partial"):
            now = datetime.utcnow()
            update["completed_at"] = now.isoformat()
            try:
                started = datetime.fromisoformat(row["started_at"].rstrip("Z"))
                update["duration_ms"] = int((now - started).total_seconds() * 1000)
            except Exception:
                pass

        if steps is not None:
            update["steps"] = steps
            update["total_steps"] = len(steps)
            update["successful_steps"] = sum(
                1 for s in steps if s.get("status") == "success"
            )
            update["failed_steps"] = sum(
                1 for s in steps if s.get("status") == "failed"
            )

        if result is not None:
            update["result"] = result
        if error is not None:
            update["error"] = error
        if output_results is not None:
            update["output_results"] = output_results

        return await super().update(row["id"], update)

    async def append_step(
        self, execution_id: str, step: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        row = await self.get_by_id(execution_id)
        if not row:
            return None
        steps = list(row.get("steps") or [])
        steps.append(step)
        return await super().update(
            row["id"],
            {
                "steps": steps,
                "total_steps": len(steps),
            },
        )

    async def list_for_automation(
        self, automation_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        return await self.get_all(
            filter={"automation_id": automation_id},
            limit=limit,
            sort=[("started_at", -1)],
        )

    async def list_recent(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        filter_q: Dict[str, Any] = {}
        if status:
            filter_q["status"] = status
        return await self.get_all(
            filter=filter_q,
            skip=offset,
            limit=limit,
            sort=[("started_at", -1)],
        )

    async def cleanup_old(self, days: int = 90) -> int:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return await self.delete_many({"started_at": {"$lt": cutoff}})
