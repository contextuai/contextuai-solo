"""
Workspace Agent Repository for AI Team Workspace Feature

Repository class for managing workspace agents in MongoDB.
Provides methods for retrieving and managing AI team agents.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class WorkspaceAgentRepository(BaseRepository):
    """
    Repository for workspace agents.

    Manages the 'workspace_agents' collection in MongoDB, providing methods for
    retrieving, creating, and updating AI team agents.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for workspace agents
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the WorkspaceAgentRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "workspace_agents")

    async def get_all_active(self) -> List[Dict[str, Any]]:
        """
        Retrieve all active agents.

        Returns:
            List of active agent documents sorted by created_at descending
        """
        return await self.get_all(
            filter={"is_active": True},
            sort=[("created_at", -1)]
        )

    async def get_by_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an agent by its ID.

        Args:
            agent_id: The agent's unique identifier (agent_id field)

        Returns:
            Agent document with id field, or None if not found
        """
        # First try by agent_id field
        agent = await self.get_one({"agent_id": agent_id})
        if agent:
            return agent

        # Fall back to MongoDB _id
        try:
            return await super().get_by_id(agent_id)
        except ValueError:
            return None

    async def get_by_category(
        self,
        category: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve agents by category.

        Args:
            category: The agent category ('architect', 'developer', 'tester', 'reviewer', etc.)
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of agent documents matching the category
        """
        return await self.get_all(
            filter={"category": category, "is_active": True},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def get_by_ids(self, agent_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Retrieve multiple agents by their IDs.

        Args:
            agent_ids: List of agent IDs to retrieve

        Returns:
            List of agent documents
        """
        # Try by agent_id field first
        agents = await self.get_all(
            filter={"agent_id": {"$in": agent_ids}},
            limit=len(agent_ids)
        )

        # If we found all agents, return them
        if len(agents) == len(agent_ids):
            return agents

        # Try to find remaining by MongoDB _id
        found_agent_ids = {a.get("agent_id") for a in agents}
        remaining_ids = [aid for aid in agent_ids if aid not in found_agent_ids]

        if remaining_ids:
            try:
                additional = await self.find_by_ids(remaining_ids)
                agents.extend(additional)
            except ValueError:
                pass

        return agents

    async def create(
        self,
        name: str,
        description: str,
        category: str,
        capabilities: List[str],
        system_prompt: str,
        model_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new workspace agent.

        Args:
            name: Name of the agent
            description: Description of the agent's role and capabilities
            category: Agent category ('architect', 'developer', 'tester', 'reviewer', etc.)
            capabilities: List of agent capabilities
            system_prompt: The agent's system prompt
            model_id: Optional AI model ID for the agent
            config: Optional additional configuration

        Returns:
            Created agent document with id field
        """
        agent_data = {
            "agent_id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "category": category,
            "capabilities": capabilities,
            "system_prompt": system_prompt,
            "model_id": model_id,
            "config": config or {},
            "is_active": True,
            "usage_count": 0,
            "last_used": None
        }

        return await super().create(agent_data)

    async def update(
        self,
        agent_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing agent.

        Args:
            agent_id: The agent's unique identifier
            data: Fields to update (partial update supported)

        Returns:
            Updated agent document with id field, or None if not found
        """
        # Find the agent first
        agent = await self.get_one({"agent_id": agent_id})
        if agent:
            return await super().update(agent["id"], data)

        # Fall back to MongoDB _id
        try:
            return await super().update(agent_id, data)
        except ValueError:
            return None

    async def increment_usage_count(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Increment the usage count and update last_used timestamp.

        Args:
            agent_id: The agent's unique identifier

        Returns:
            Updated agent document, or None if not found
        """
        agent = await self.get_one({"agent_id": agent_id})
        if not agent:
            try:
                agent = await super().get_by_id(agent_id)
            except ValueError:
                return None

        if not agent:
            return None

        mongo_id = agent["id"]
        now = datetime.utcnow().isoformat()

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$inc": {"usage_count": 1},
                "$set": {
                    "last_used": now,
                    "updated_at": now
                }
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def get_by_capability(
        self,
        capability: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve agents that have a specific capability.

        Args:
            capability: The capability to search for
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of agent documents with the capability
        """
        return await self.get_all(
            filter={"capabilities": capability, "is_active": True},
            skip=skip,
            limit=limit,
            sort=[("usage_count", -1)]
        )

    async def get_popular_agents(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most used agents.

        Args:
            limit: Maximum number of agents to return

        Returns:
            List of agent documents sorted by usage count
        """
        return await self.get_all(
            filter={"is_active": True},
            limit=limit,
            sort=[("usage_count", -1)]
        )

    async def deactivate(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Deactivate an agent.

        Args:
            agent_id: The agent's unique identifier

        Returns:
            Updated agent document, or None if not found
        """
        return await self.update(agent_id, {"is_active": False})

    async def activate(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Activate an agent.

        Args:
            agent_id: The agent's unique identifier

        Returns:
            Updated agent document, or None if not found
        """
        return await self.update(agent_id, {"is_active": True})

    async def get_custom_agents(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve custom (non-system) agents created by a specific user.

        Args:
            user_id: The user's identifier

        Returns:
            List of custom agent documents created by the user
        """
        return await self.get_all(
            filter={
                "is_system": {"$ne": True},
                "created_by": user_id,
                "is_active": True
            },
            sort=[("created_at", -1)]
        )

    async def get_all_agents_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all agents available to a user: system agents + user's custom agents.

        Args:
            user_id: The user's identifier

        Returns:
            List of all available agent documents (system + user-created)
        """
        return await self.get_all(
            filter={
                "is_active": True,
                "$or": [
                    {"is_system": True},
                    {"created_by": user_id}
                ]
            },
            sort=[("is_system", -1), ("created_at", -1)]
        )
