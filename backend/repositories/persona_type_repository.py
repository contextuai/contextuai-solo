"""
Persona Type Repository for Persona Type Definitions

Repository class for managing persona type definitions in MongoDB.
Provides methods for CRUD operations with filtering by category and enabled status.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository


class PersonaTypeRepository(BaseRepository):
    """
    Repository for persona type definitions.

    Manages the 'persona_types' collection in MongoDB, providing methods for
    retrieving, creating, updating, and deleting persona type definitions.

    Persona types define the available connector types (e.g., PostgreSQL, MySQL,
    Slack) that users can instantiate as personas.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for persona_types
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the PersonaTypeRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "persona_types")

    async def get_all(
        self,
        filter: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None,
        projection: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all persona type definitions with optional filtering.

        Args:
            filter: MongoDB query filter
            skip: Number of documents to skip (offset)
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting.
                  Default: sort by category, then name ascending.
            projection: Fields to include/exclude in results

        Returns:
            List of persona type documents with id fields
        """
        if sort is None:
            sort = [("category", 1), ("name", 1)]

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
        status: Optional[str] = None,
        enabled: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve persona types by category.

        Args:
            category: The category to filter by (e.g., 'Data & Analytics', 'Communication')
            status: Optional filter by lifecycle status ('active' or 'inactive')
            enabled: Optional filter by implementation status
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of persona type documents matching the category
        """
        filter_query: Dict[str, Any] = {"category": category}

        if status:
            filter_query["status"] = status

        if enabled is not None:
            filter_query["enabled"] = enabled

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )

    async def get_by_id(self, persona_type_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a persona type definition by its ID.

        Args:
            persona_type_id: String representation of the persona type's ObjectId

        Returns:
            Persona type document with id field, or None if not found

        Raises:
            ValueError: If persona_type_id is not a valid ObjectId string
        """
        return await super().get_by_id(persona_type_id)

    async def get_by_string_id(self, type_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a persona type by its string ID field (not ObjectId).

        Some persona types use a readable string ID (e.g., 'postgresql_database')
        instead of MongoDB ObjectId.

        Args:
            type_id: The string ID of the persona type

        Returns:
            Persona type document, or None if not found
        """
        return await self.get_one({"id": type_id})

    async def get_enabled(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all enabled (implemented) persona types.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of enabled persona type documents
        """
        return await self.get_all(
            filter={"enabled": True},
            skip=skip,
            limit=limit
        )

    async def get_active(
        self,
        filter: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve active persona types (not soft-deleted and status is active).

        Args:
            filter: Additional filter criteria
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting

        Returns:
            List of active persona type documents
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
        Create a new persona type definition.

        Args:
            data: Persona type data including:
                - id: Unique string identifier (e.g., 'postgresql_database')
                - name: Display name
                - description: Description of the persona type
                - icon: Icon identifier
                - color: Hex color code (e.g., '#336791')
                - category: Category (e.g., 'Data & Analytics')
                - status: Lifecycle status ('active' or 'inactive')
                - enabled: Whether the connector is implemented
                - credentialFields: List of credential field definitions

        Returns:
            Created persona type document with id field
        """
        # Set default values if not provided
        if "status" not in data:
            data["status"] = "active"

        if "enabled" not in data:
            data["enabled"] = False

        return await super().create(data)

    async def update(
        self,
        persona_type_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a persona type definition.

        Args:
            persona_type_id: String representation of the persona type's ObjectId
            data: Fields to update (partial update supported)

        Returns:
            Updated persona type document with id field, or None if not found

        Raises:
            ValueError: If persona_type_id is not a valid ObjectId string
        """
        return await super().update(persona_type_id, data)

    async def delete(self, persona_type_id: str) -> bool:
        """
        Delete a persona type definition.

        Args:
            persona_type_id: String representation of the persona type's ObjectId

        Returns:
            True if persona type was deleted, False if not found

        Raises:
            ValueError: If persona_type_id is not a valid ObjectId string
        """
        return await super().delete(persona_type_id)

    async def set_enabled(
        self,
        persona_type_id: str,
        enabled: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Enable or disable a persona type (mark as implemented or not).

        Args:
            persona_type_id: String representation of the persona type's ObjectId
            enabled: Whether the persona type connector is implemented

        Returns:
            Updated persona type document, or None if not found

        Raises:
            ValueError: If persona_type_id is not a valid ObjectId string
        """
        return await self.update(persona_type_id, {"enabled": enabled})

    async def set_status(
        self,
        persona_type_id: str,
        status: str
    ) -> Optional[Dict[str, Any]]:
        """
        Set the lifecycle status of a persona type.

        Args:
            persona_type_id: String representation of the persona type's ObjectId
            status: New status ('active' or 'inactive')

        Returns:
            Updated persona type document, or None if not found

        Raises:
            ValueError: If persona_type_id is not a valid ObjectId string
            ValueError: If status is not 'active' or 'inactive'
        """
        if status not in ("active", "inactive"):
            raise ValueError("Status must be 'active' or 'inactive'")

        return await self.update(persona_type_id, {"status": status})

    async def get_categories(self) -> List[str]:
        """
        Get all distinct categories.

        Returns:
            List of unique category names
        """
        return await self.distinct("category")

    async def count_by_category(self) -> List[Dict[str, Any]]:
        """
        Count persona types grouped by category.

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

    async def count_by_enabled_status(self) -> Dict[str, int]:
        """
        Count persona types by enabled status.

        Returns:
            Dictionary with 'enabled', 'disabled', and 'total' counts
        """
        enabled_count = await self.count({"enabled": True})
        disabled_count = await self.count({
            "$or": [
                {"enabled": False},
                {"enabled": {"$exists": False}}
            ]
        })

        return {
            "enabled": enabled_count,
            "disabled": disabled_count,
            "total": enabled_count + disabled_count
        }

    async def get_by_category_and_status(
        self,
        category: str,
        status: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve persona types by category and status.

        Args:
            category: The category to filter by
            status: The lifecycle status to filter by
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of persona type documents matching category and status
        """
        return await self.get_all(
            filter={
                "category": category,
                "status": status
            },
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )

    async def exists_by_string_id(self, type_id: str) -> bool:
        """
        Check if a persona type with the given string ID exists.

        Args:
            type_id: The string ID to check

        Returns:
            True if a persona type with that string ID exists
        """
        return await self.exists({"id": type_id})

    async def update_credential_fields(
        self,
        persona_type_id: str,
        credential_fields: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Update the credential field definitions for a persona type.

        Args:
            persona_type_id: String representation of the persona type's ObjectId
            credential_fields: List of credential field definitions, each containing:
                - name: Field name
                - label: Display label
                - type: Field type (text, password, number, etc.)
                - required: Whether the field is required
                - placeholder: Optional placeholder text
                - options: Optional list of options (for select type)

        Returns:
            Updated persona type document, or None if not found

        Raises:
            ValueError: If persona_type_id is not a valid ObjectId string
        """
        return await self.update(
            persona_type_id,
            {"credentialFields": credential_fields}
        )
