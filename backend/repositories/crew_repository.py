"""
Crew Repository — MongoDB data access for crews and crew runs.

Follows the BaseRepository pattern used by workspace projects.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository

logger = logging.getLogger(__name__)


class CrewRepository(BaseRepository):
    """Repository for crew configurations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "crews")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_crew(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new crew configuration."""
        now = datetime.utcnow().isoformat()
        doc = {
            "crew_id": str(uuid.uuid4()),
            "user_id": user_id,
            "status": "active",
            "total_runs": 0,
            "total_cost_usd": 0.0,
            "last_run_at": None,
            "deleted_at": None,
            "created_at": now,
            "updated_at": now,
            **data,
        }
        # Assign agent_ids if missing
        for agent in doc.get("agents", []):
            if not agent.get("agent_id"):
                agent["agent_id"] = str(uuid.uuid4())

        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_crew_id(self, crew_id: str) -> Optional[Dict[str, Any]]:
        """Get crew by crew_id (UUID), excluding soft-deleted."""
        doc = await self.collection.find_one({"crew_id": crew_id, "deleted_at": None})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def get_user_crews(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get crews belonging to a user with optional status filter."""
        query: Dict[str, Any] = {"user_id": user_id, "deleted_at": None}
        if status:
            query["status"] = status

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

    async def get_by_name(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Find a crew by exact name (case-insensitive) for a user."""
        import re
        doc = await self.collection.find_one({
            "user_id": user_id,
            "name": re.compile(f"^{re.escape(name)}$", re.IGNORECASE),
            "deleted_at": None,
        })
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_crew(self, crew_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a crew by crew_id."""
        data["updated_at"] = datetime.utcnow().isoformat()
        result = await self.collection.find_one_and_update(
            {"crew_id": crew_id, "deleted_at": None},
            {"$set": data},
            return_document=True,
        )
        if result:
            result["id"] = str(result.pop("_id"))
        return result

    async def increment_run_stats(
        self, crew_id: str, cost_usd: float = 0.0
    ) -> None:
        """Increment total_runs and accumulate cost after a run completes."""
        await self.collection.update_one(
            {"crew_id": crew_id},
            {
                "$inc": {"total_runs": 1, "total_cost_usd": cost_usd},
                "$set": {
                    "last_run_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            },
        )

    # ------------------------------------------------------------------
    # Soft Delete
    # ------------------------------------------------------------------

    async def soft_delete_crew(self, crew_id: str) -> bool:
        """Soft-delete a crew."""
        result = await self.collection.update_one(
            {"crew_id": crew_id, "deleted_at": None},
            {"$set": {"deleted_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}},
        )
        return result.modified_count > 0


class CrewRunRepository(BaseRepository):
    """Repository for crew execution runs."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "crew_runs")

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_run(self, crew_id: str, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new crew run record."""
        now = datetime.utcnow().isoformat()
        doc = {
            "run_id": str(uuid.uuid4()),
            "crew_id": crew_id,
            "user_id": user_id,
            "status": "pending",
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "duration_ms": None,
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

    async def get_by_run_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get a run by run_id."""
        doc = await self.collection.find_one({"run_id": run_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def get_crew_runs(
        self,
        crew_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get runs for a specific crew."""
        query: Dict[str, Any] = {"crew_id": crew_id}
        if status:
            query["status"] = status

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

    async def update_run(self, run_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a run record."""
        data["updated_at"] = datetime.utcnow().isoformat()
        result = await self.collection.find_one_and_update(
            {"run_id": run_id},
            {"$set": data},
            return_document=True,
        )
        if result:
            result["id"] = str(result.pop("_id"))
        return result

    async def mark_running(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Mark a run as running."""
        return await self.update_run(run_id, {
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
        })

    async def mark_completed(
        self, run_id: str, result: str, total_tokens: int = 0, total_cost_usd: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """Mark a run as completed with result."""
        now = datetime.utcnow().isoformat()
        run = await self.get_by_run_id(run_id)
        duration_ms = None
        if run and run.get("started_at"):
            try:
                started = datetime.fromisoformat(run["started_at"])
                duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            except (ValueError, TypeError):
                pass

        return await self.update_run(run_id, {
            "status": "completed",
            "result": result,
            "completed_at": now,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "duration_ms": duration_ms,
        })

    async def mark_failed(self, run_id: str, error: str) -> Optional[Dict[str, Any]]:
        """Mark a run as failed."""
        now = datetime.utcnow().isoformat()
        run = await self.get_by_run_id(run_id)
        duration_ms = None
        if run and run.get("started_at"):
            try:
                started = datetime.fromisoformat(run["started_at"])
                duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            except (ValueError, TypeError):
                pass

        return await self.update_run(run_id, {
            "status": "failed",
            "error": error,
            "completed_at": now,
            "duration_ms": duration_ms,
        })

    async def update_agent_state(
        self, run_id: str, agent_id: str, state_update: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a specific agent's state within a run."""
        result = await self.collection.find_one_and_update(
            {"run_id": run_id, "agents.agent_id": agent_id},
            {"$set": {f"agents.$.{k}": v for k, v in state_update.items()}},
            return_document=True,
        )
        if result:
            result["id"] = str(result.pop("_id"))
        return result

    async def append_agent_state(
        self, run_id: str, agent_state: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Append a new agent state to a run (used by autonomous mode)."""
        result = await self.collection.find_one_and_update(
            {"run_id": run_id},
            {"$push": {"agents": agent_state}},
            return_document=True,
        )
        if result:
            result["id"] = str(result.pop("_id"))
        return result
