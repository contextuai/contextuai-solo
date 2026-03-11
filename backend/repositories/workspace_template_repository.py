"""
Workspace Template Repository for AI Team Workspace Feature

Repository class for managing workspace templates in MongoDB.
Provides methods for retrieving and managing project templates.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class WorkspaceTemplateRepository(BaseRepository):
    """
    Repository for workspace templates.

    Manages the 'workspace_templates' collection in MongoDB, providing methods for
    retrieving, creating, updating, and deleting project templates.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for workspace templates
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the WorkspaceTemplateRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "workspace_templates")

    async def get_system_templates(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all system templates.

        System templates are pre-defined templates available to all users.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of system template documents sorted by created_at descending
        """
        return await self.get_all(
            filter={"is_system": True, "is_active": True},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def get_user_templates(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve templates created by a specific user.

        Args:
            user_id: ID of the user
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of user template documents sorted by created_at descending
        """
        return await self.get_all(
            filter={"user_id": user_id, "is_active": True},
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )

    async def get_by_id(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a template by its ID.

        Args:
            template_id: The template's unique identifier (template_id field)

        Returns:
            Template document with id field, or None if not found
        """
        # First try by template_id field
        template = await self.get_one({"template_id": template_id, "is_active": True})
        if template:
            return template

        # Fall back to MongoDB _id
        try:
            result = await super().get_by_id(template_id)
            if result and result.get("is_active", True):
                return result
            return None
        except ValueError:
            return None

    async def create(
        self,
        name: str,
        description: str,
        category: str,
        tech_stack: List[str],
        complexity: str,
        team_agent_ids: List[str],
        config: Dict[str, Any],
        user_id: Optional[str] = None,
        is_system: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new workspace template.

        Args:
            name: Name of the template
            description: Description of the template
            category: Template category ('web', 'api', 'mobile', 'data', etc.)
            tech_stack: List of technologies in the template
            complexity: Complexity level ('simple', 'moderate', 'complex')
            team_agent_ids: Default agent IDs for projects using this template
            config: Template configuration including default settings
            user_id: Optional user ID for user-created templates
            is_system: Whether this is a system template

        Returns:
            Created template document with id field
        """
        template_data = {
            "template_id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "category": category,
            "tech_stack": tech_stack,
            "complexity": complexity,
            "team_agent_ids": team_agent_ids,
            "config": config,
            "user_id": user_id,
            "is_system": is_system,
            "is_active": True,
            "usage_count": 0,
            "last_used": None
        }

        return await super().create(template_data)

    async def update(
        self,
        template_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing template.

        Args:
            template_id: The template's unique identifier
            data: Fields to update (partial update supported)

        Returns:
            Updated template document with id field, or None if not found
        """
        # Find the template first
        template = await self.get_one({"template_id": template_id, "is_active": True})
        if template:
            return await super().update(template["id"], data)

        # Fall back to MongoDB _id
        try:
            return await super().update(template_id, data)
        except ValueError:
            return None

    async def delete(self, template_id: str) -> bool:
        """
        Soft delete a template by setting is_active to False.

        Args:
            template_id: The template's unique identifier

        Returns:
            True if template was deleted, False if not found
        """
        template = await self.get_one({"template_id": template_id, "is_active": True})
        if template:
            result = await super().update(template["id"], {"is_active": False})
            return result is not None

        # Fall back to MongoDB _id
        try:
            result = await super().update(template_id, {"is_active": False})
            return result is not None
        except ValueError:
            return False

    async def increment_usage_count(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        Increment the usage count and update last_used timestamp.

        Args:
            template_id: The template's unique identifier

        Returns:
            Updated template document, or None if not found
        """
        template = await self.get_one({"template_id": template_id, "is_active": True})
        if not template:
            try:
                template = await super().get_by_id(template_id)
            except ValueError:
                return None

        if not template:
            return None

        mongo_id = template["id"]
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

    async def get_by_category(
        self,
        category: str,
        include_system: bool = True,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve templates by category.

        Args:
            category: The template category
            include_system: Whether to include system templates
            user_id: Optional user ID to include user templates
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of template documents matching the category
        """
        filter_query: Dict[str, Any] = {"category": category, "is_active": True}

        if include_system and user_id:
            filter_query["$or"] = [
                {"is_system": True},
                {"user_id": user_id}
            ]
        elif include_system:
            filter_query["is_system"] = True
        elif user_id:
            filter_query["user_id"] = user_id

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("usage_count", -1)]
        )

    async def get_popular_templates(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most used templates.

        Args:
            limit: Maximum number of templates to return

        Returns:
            List of template documents sorted by usage count
        """
        return await self.get_all(
            filter={"is_system": True, "is_active": True},
            limit=limit,
            sort=[("usage_count", -1)]
        )

    async def get_all_available(
        self,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all available templates (system + user's own).

        Args:
            user_id: Optional user ID to include user templates
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of available template documents
        """
        filter_query: Dict[str, Any] = {"is_active": True}

        if user_id:
            filter_query["$or"] = [
                {"is_system": True},
                {"user_id": user_id}
            ]
        else:
            filter_query["is_system"] = True

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        )
