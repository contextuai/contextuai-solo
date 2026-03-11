"""
Workspace Project Type Repository for Project Type Definitions

Repository class for managing workspace project type definitions in MongoDB.
Provides methods for CRUD operations with filtering by category and enabled status.

Workspace project types define the available project types (e.g., Build, Workshop),
workshop types (e.g., Strategy, Brainstorm), and output formats (e.g., Report, Slides)
that users can select when creating workspace projects.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository


class WorkspaceProjectTypeRepository(BaseRepository):
    """
    Repository for workspace project type definitions.

    Manages the 'workspace_project_types' collection in MongoDB, providing methods for
    retrieving, creating, updating, and deleting workspace project type definitions.

    Workspace project types are organized into categories:
    - 'project_type': Top-level project types (Build, Workshop)
    - 'workshop_type': Workshop session types (Strategy, Brainstorm, Analysis, etc.)
    - 'output_format': Output format options (Report, Slides, Canvas, Brief)

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for workspace_project_types
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the WorkspaceProjectTypeRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "workspace_project_types")

    async def get_all(
        self,
        filter: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None,
        projection: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all workspace project type definitions with optional filtering.

        Args:
            filter: MongoDB query filter
            skip: Number of documents to skip (offset)
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting.
                  Default: sort by sort_order, then label ascending.
            projection: Fields to include/exclude in results

        Returns:
            List of workspace project type documents with id fields
        """
        if sort is None:
            sort = [("sort_order", 1), ("label", 1)]

        return await super().get_all(
            filter=filter,
            skip=skip,
            limit=limit,
            sort=sort,
            projection=projection
        )

    async def get_by_category(
        self,
        category: str,
        enabled: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve workspace project types by category.

        Args:
            category: The category to filter by ('project_type', 'workshop_type', 'output_format')
            enabled: Optional filter by enabled status
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of workspace project type documents matching the category
        """
        filter_query: Dict[str, Any] = {"category": category}

        if enabled is not None:
            filter_query["enabled"] = enabled

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("sort_order", 1), ("label", 1)]
        )

    async def get_by_id(self, project_type_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a workspace project type definition by its MongoDB ObjectId.

        Args:
            project_type_id: String representation of the project type's ObjectId

        Returns:
            Workspace project type document with id field, or None if not found

        Raises:
            ValueError: If project_type_id is not a valid ObjectId string
        """
        return await super().get_by_id(project_type_id)

    async def get_by_string_id(self, type_key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a workspace project type by its string key field.

        Some workspace project types use a readable string key (e.g., 'build', 'workshop',
        'strategy') instead of MongoDB ObjectId.

        Args:
            type_key: The string key of the workspace project type

        Returns:
            Workspace project type document, or None if not found
        """
        return await self.get_one({"key": type_key})

    async def get_enabled(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all enabled workspace project types.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of enabled workspace project type documents
        """
        return await self.get_all(
            filter={"enabled": True},
            skip=skip,
            limit=limit,
            sort=[("sort_order", 1), ("label", 1)]
        )

    async def get_active(
        self,
        filter: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve active workspace project types (not soft-deleted and status is active).

        Args:
            filter: Additional filter criteria
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting

        Returns:
            List of active workspace project type documents
        """
        active_filter: Dict[str, Any] = {
            "status": "active",
            "deleted_at": {"$exists": False}
        }

        if filter:
            active_filter.update(filter)

        return await self.get_all(
            filter=active_filter,
            skip=skip,
            limit=limit,
            sort=sort
        )

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new workspace project type definition.

        Args:
            data: Workspace project type data including:
                - key: Unique string identifier (e.g., 'build', 'workshop', 'strategy')
                - label: Display name
                - description: Description of the project type
                - icon: Lucide icon name
                - color: Hex color code (e.g., '#3B82F6')
                - category: Category ('project_type', 'workshop_type', 'output_format')
                - sort_order: Display order
                - enabled: Whether the type is available
                - config: Optional additional configuration

        Returns:
            Created workspace project type document with id field
        """
        if "status" not in data:
            data["status"] = "active"

        if "enabled" not in data:
            data["enabled"] = True

        return await super().create(data)

    async def update(
        self,
        project_type_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a workspace project type definition.

        Args:
            project_type_id: String representation of the project type's ObjectId
            data: Fields to update (partial update supported)

        Returns:
            Updated workspace project type document with id field, or None if not found

        Raises:
            ValueError: If project_type_id is not a valid ObjectId string
        """
        return await super().update(project_type_id, data)

    async def delete(self, project_type_id: str) -> bool:
        """
        Delete a workspace project type definition.

        Args:
            project_type_id: String representation of the project type's ObjectId

        Returns:
            True if workspace project type was deleted, False if not found

        Raises:
            ValueError: If project_type_id is not a valid ObjectId string
        """
        return await super().delete(project_type_id)

    async def set_enabled(
        self,
        project_type_id: str,
        enabled: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Enable or disable a workspace project type.

        Args:
            project_type_id: String representation of the project type's ObjectId
            enabled: Whether the workspace project type should be enabled

        Returns:
            Updated workspace project type document, or None if not found

        Raises:
            ValueError: If project_type_id is not a valid ObjectId string
        """
        return await self.update(project_type_id, {"enabled": enabled})

    async def set_status(
        self,
        project_type_id: str,
        status: str
    ) -> Optional[Dict[str, Any]]:
        """
        Set the lifecycle status of a workspace project type.

        Args:
            project_type_id: String representation of the project type's ObjectId
            status: New status ('active' or 'inactive')

        Returns:
            Updated workspace project type document, or None if not found

        Raises:
            ValueError: If project_type_id is not a valid ObjectId string
            ValueError: If status is not 'active' or 'inactive'
        """
        if status not in ("active", "inactive"):
            raise ValueError("Status must be 'active' or 'inactive'")

        return await self.update(project_type_id, {"status": status})

    async def get_categories(self) -> List[str]:
        """
        Get all distinct categories.

        Returns:
            List of unique category names
        """
        return await self.distinct("category")

    async def count_by_category(self) -> List[Dict[str, Any]]:
        """
        Count workspace project types grouped by category.

        Returns:
            List of dictionaries with category and count
        """
        pipeline = [
            {"$match": {"deleted_at": {"$exists": False}}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$project": {"category": "$_id", "count": 1, "_id": 0}},
            {"$sort": {"category": 1}}
        ]

        return await self.aggregate(pipeline, convert_ids=False)

    async def exists_by_key(self, key: str) -> bool:
        """
        Check if a workspace project type with the given key exists.

        Args:
            key: The string key to check

        Returns:
            True if a workspace project type with that key exists
        """
        return await self.exists({"key": key})
