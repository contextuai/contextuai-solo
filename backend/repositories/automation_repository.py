"""
Automation Repository for Workflow Automations

Repository class for managing workflow automations in MongoDB.
Provides methods for CRUD operations with filtering by user and status.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class AutomationRepository(BaseRepository):
    """
    Repository for workflow automations.

    Manages the 'automations' collection in MongoDB, providing methods for
    creating, retrieving, updating, and deleting workflow automations.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for automations
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the AutomationRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "automations")

    async def create(
        self,
        user_id: str,
        name: str,
        description: str,
        prompt_template: str,
        trigger_type: str = "manual",
        trigger_config: Optional[Dict[str, Any]] = None,
        status: str = "draft",
        execution_mode: str = "smart",
        personas_detected: Optional[List[str]] = None,
        output_actions: Optional[List[Dict[str, Any]]] = None,
        model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new automation workflow.

        Args:
            user_id: ID of the user creating the automation
            name: Name of the automation
            description: Description of the automation
            prompt_template: Natural language prompt with @persona mentions
            trigger_type: How the automation is triggered ('manual', 'scheduled', 'event')
            trigger_config: Configuration for scheduled/event triggers
            status: Initial status ('draft', 'active', 'inactive')
            execution_mode: Execution mode ('sequential', 'parallel', 'smart')
            personas_detected: List of detected persona names from prompt
            output_actions: List of output action configurations
            model_id: Optional Claude model ID for execution

        Returns:
            Created automation document with id field
        """
        automation_data = {
            "automation_id": str(uuid.uuid4()),
            "user_id": user_id,
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
            "model_id": model_id
        }

        return await super().create(automation_data)

    async def get_by_id(self, automation_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an automation by its ID.

        Args:
            automation_id: The automation's unique identifier (automation_id field)

        Returns:
            Automation document with id field, or None if not found
        """
        # First try by automation_id field
        automation = await self.get_one({"automation_id": automation_id})
        if automation:
            return automation

        # Fall back to MongoDB _id
        try:
            return await super().get_by_id(automation_id)
        except ValueError:
            return None

    async def get_user_automations(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve automations for a specific user.

        Args:
            user_id: ID of the user
            status: Optional status filter ('active', 'inactive', 'draft')
            limit: Maximum number of automations to return
            offset: Number of automations to skip (for pagination)

        Returns:
            List of automation documents sorted by created_at descending
        """
        filter_query: Dict[str, Any] = {"user_id": user_id}

        if status:
            filter_query["status"] = status

        return await self.get_all(
            filter=filter_query,
            skip=offset,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def update(
        self,
        automation_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing automation.

        Args:
            automation_id: The automation's unique identifier
            data: Fields to update (partial update supported)

        Returns:
            Updated automation document with id field, or None if not found
        """
        # Find the automation first
        automation = await self.get_one({"automation_id": automation_id})
        if automation:
            return await super().update(automation["id"], data)

        # Fall back to MongoDB _id
        try:
            return await super().update(automation_id, data)
        except ValueError:
            return None

    async def delete(self, automation_id: str) -> bool:
        """
        Delete an automation.

        Args:
            automation_id: The automation's unique identifier

        Returns:
            True if automation was deleted, False if not found
        """
        # Find the automation first
        automation = await self.get_one({"automation_id": automation_id})
        if automation:
            return await super().delete(automation["id"])

        # Fall back to MongoDB _id
        try:
            return await super().delete(automation_id)
        except ValueError:
            return False

    async def increment_run_count(self, automation_id: str) -> Optional[Dict[str, Any]]:
        """
        Increment the run count and update last_run timestamp.

        Args:
            automation_id: The automation's unique identifier

        Returns:
            Updated automation document, or None if not found
        """
        automation = await self.get_one({"automation_id": automation_id})
        if not automation:
            try:
                automation = await super().get_by_id(automation_id)
            except ValueError:
                return None

        if not automation:
            return None

        mongo_id = automation["id"]
        now = datetime.utcnow().isoformat()

        result = await self.collection.find_one_and_update(
            {"_id": self._to_object_id(mongo_id)},
            {
                "$inc": {"run_count": 1},
                "$set": {
                    "last_run": now,
                    "updated_at": now
                }
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def get_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve automations by status.

        Args:
            status: The automation status ('active', 'inactive', 'draft')
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of automation documents matching the status
        """
        return await self.get_all(
            filter={"status": status},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def get_by_trigger_type(
        self,
        trigger_type: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve automations by trigger type.

        Args:
            trigger_type: The trigger type ('manual', 'scheduled', 'event')
            status: Optional status filter
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of automation documents matching the trigger type
        """
        filter_query: Dict[str, Any] = {"trigger_type": trigger_type}

        if status:
            filter_query["status"] = status

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def get_scheduled_automations(
        self,
        status: str = "active"
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all scheduled automations that are active.

        Args:
            status: Filter by status (default 'active')

        Returns:
            List of scheduled automation documents
        """
        return await self.get_all(
            filter={
                "trigger_type": "scheduled",
                "status": status
            },
            sort=[("created_at", -1)]
        )

    async def search_by_name(
        self,
        user_id: str,
        search_term: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search automations by name for a specific user.

        Args:
            user_id: ID of the user
            search_term: Search term for name matching
            limit: Maximum number of results

        Returns:
            List of matching automation documents
        """
        return await self.get_all(
            filter={
                "user_id": user_id,
                "name": {"$regex": search_term, "$options": "i"}
            },
            limit=limit,
            sort=[("name", 1)]
        )

    async def get_automations_using_persona(
        self,
        persona_name: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve automations that use a specific persona.

        Args:
            persona_name: Name of the persona
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of automation documents using the persona
        """
        return await self.get_all(
            filter={"personas_detected": persona_name},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def count_by_user(self, user_id: str) -> int:
        """
        Count automations for a specific user.

        Args:
            user_id: ID of the user

        Returns:
            Number of automations for the user
        """
        return await self.count({"user_id": user_id})

    async def count_by_status(self) -> Dict[str, int]:
        """
        Count automations by status.

        Returns:
            Dictionary with status counts and total
        """
        active = await self.count({"status": "active"})
        inactive = await self.count({"status": "inactive"})
        draft = await self.count({"status": "draft"})

        return {
            "active": active,
            "inactive": inactive,
            "draft": draft,
            "total": active + inactive + draft
        }
