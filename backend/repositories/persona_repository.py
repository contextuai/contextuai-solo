"""
Persona Repository for Persona Instances

Repository class for managing persona instances in MongoDB.
Provides methods for CRUD operations with filtering by user, persona type, and enabled status.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository


class PersonaRepository(BaseRepository):
    """
    Repository for persona instances.

    Manages the 'personas' collection in MongoDB, providing methods for
    retrieving, creating, updating, and deleting persona instances.

    Personas are user-configured instances of persona types (connectors)
    with specific credentials and settings.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for personas
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the PersonaRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "personas")

    async def get_all(
        self,
        filter: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None,
        projection: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all persona instances with optional filtering.

        Args:
            filter: MongoDB query filter
            skip: Number of documents to skip (offset)
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting.
                  Default: sort by name ascending.
            projection: Fields to include/exclude in results

        Returns:
            List of persona documents with id fields
        """
        if sort is None:
            sort = [("name", 1)]

        return await super().get_all(
            filter=filter,
            skip=skip,
            limit=limit,
            sort=sort,
            projection=projection
        )

    async def get_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        include_credentials: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all personas belonging to a specific user.

        Args:
            user_id: The user's ID
            status: Optional filter by status ('active' or 'inactive')
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            include_credentials: If False, mask credentials in response

        Returns:
            List of persona documents for the user
        """
        filter_query: Dict[str, Any] = {"user_id": user_id}

        if status:
            filter_query["status"] = status

        # Exclude credentials field if not requested
        projection = None
        if not include_credentials:
            projection = {"credentials": 0}

        personas = await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("name", 1)],
            projection=projection
        )

        # If credentials were not excluded but we don't want to include them, mask them
        if not include_credentials and projection is None:
            for persona in personas:
                if "credentials" in persona:
                    persona["credentials"] = {"_encrypted": True}

        return personas

    async def get_by_type(
        self,
        persona_type_id: str,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all personas of a specific persona type.

        Args:
            persona_type_id: The persona type ID to filter by
            user_id: Optional filter by user ID
            status: Optional filter by status ('active' or 'inactive')
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of persona documents matching the persona type
        """
        filter_query: Dict[str, Any] = {"persona_type_id": persona_type_id}

        if user_id:
            filter_query["user_id"] = user_id

        if status:
            filter_query["status"] = status

        personas = await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )

        # Mask credentials in response
        for persona in personas:
            if "credentials" in persona:
                persona["credentials"] = {"_encrypted": True}

        return personas

    async def get_by_user_and_type(
        self,
        user_id: str,
        persona_type_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve personas for a specific user and persona type combination.

        Args:
            user_id: The user's ID
            persona_type_id: The persona type ID
            status: Optional filter by status

        Returns:
            List of persona documents matching both user and type
        """
        filter_query: Dict[str, Any] = {
            "user_id": user_id,
            "persona_type_id": persona_type_id
        }

        if status:
            filter_query["status"] = status

        personas = await self.get_all(
            filter=filter_query,
            sort=[("name", 1)]
        )

        # Mask credentials in response
        for persona in personas:
            if "credentials" in persona:
                persona["credentials"] = {"_encrypted": True}

        return personas

    async def get_by_id(
        self,
        persona_id: str,
        include_credentials: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a persona instance by its ID.

        Args:
            persona_id: String representation of the persona's ObjectId
            include_credentials: If False, mask credentials in response

        Returns:
            Persona document with id field, or None if not found

        Raises:
            ValueError: If persona_id is not a valid ObjectId string
        """
        persona = await super().get_by_id(persona_id)

        if persona and not include_credentials:
            if "credentials" in persona:
                persona["credentials"] = {"_encrypted": True}

        return persona

    async def get_by_id_with_credentials(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a persona instance by its ID with full credentials.

        WARNING: Use with caution - only use when credentials are needed
        for actual connection operations.

        Args:
            persona_id: String representation of the persona's ObjectId

        Returns:
            Persona document with id field and full credentials, or None if not found

        Raises:
            ValueError: If persona_id is not a valid ObjectId string
        """
        return await super().get_by_id(persona_id)

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new persona instance.

        Args:
            data: Persona data including:
                - name: Display name for the persona
                - description: Description of the persona
                - persona_type_id: ID of the persona type (connector type)
                - user_id: ID of the user who owns this persona
                - credentials: Connection credentials (will be stored securely)
                - category: Optional category
                - icon: Optional icon identifier
                - status: Status ('active' or 'inactive'), defaults to 'active'

        Returns:
            Created persona document with id field (credentials masked)
        """
        # Set default status if not provided
        if "status" not in data:
            data["status"] = "active"

        persona = await super().create(data)

        # Mask credentials in response
        if "credentials" in persona:
            persona["credentials"] = {"_encrypted": True}

        return persona

    async def update(
        self,
        persona_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a persona instance.

        Args:
            persona_id: String representation of the persona's ObjectId
            data: Fields to update (partial update supported).
                  Note: user_id and created_at cannot be changed.

        Returns:
            Updated persona document with id field (credentials masked),
            or None if not found

        Raises:
            ValueError: If persona_id is not a valid ObjectId string
        """
        # Remove fields that should not be updated
        data.pop("user_id", None)
        data.pop("created_at", None)

        persona = await super().update(persona_id, data)

        if persona and "credentials" in persona:
            persona["credentials"] = {"_encrypted": True}

        return persona

    async def delete(self, persona_id: str) -> bool:
        """
        Delete a persona instance.

        Args:
            persona_id: String representation of the persona's ObjectId

        Returns:
            True if persona was deleted, False if not found

        Raises:
            ValueError: If persona_id is not a valid ObjectId string
        """
        return await super().delete(persona_id)

    async def set_status(
        self,
        persona_id: str,
        status: str
    ) -> Optional[Dict[str, Any]]:
        """
        Set the status of a persona instance.

        Args:
            persona_id: String representation of the persona's ObjectId
            status: New status ('active' or 'inactive')

        Returns:
            Updated persona document, or None if not found

        Raises:
            ValueError: If persona_id is not a valid ObjectId string
            ValueError: If status is not 'active' or 'inactive'
        """
        if status not in ("active", "inactive"):
            raise ValueError("Status must be 'active' or 'inactive'")

        return await self.update(persona_id, {"status": status})

    async def get_active_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all active personas for a user.

        Args:
            user_id: The user's ID
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of active persona documents for the user
        """
        return await self.get_by_user(
            user_id=user_id,
            status="active",
            skip=skip,
            limit=limit
        )

    async def count_by_user(self, user_id: str) -> int:
        """
        Count personas owned by a user.

        Args:
            user_id: The user's ID

        Returns:
            Number of personas owned by the user
        """
        return await self.count({"user_id": user_id})

    async def count_by_type(self, persona_type_id: str) -> int:
        """
        Count personas of a specific type.

        Args:
            persona_type_id: The persona type ID

        Returns:
            Number of personas of the specified type
        """
        return await self.count({"persona_type_id": persona_type_id})

    async def get_by_category(
        self,
        category: str,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve personas by category.

        Args:
            category: The category to filter by
            user_id: Optional filter by user ID
            status: Optional filter by status
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of persona documents matching the category
        """
        filter_query: Dict[str, Any] = {"category": category}

        if user_id:
            filter_query["user_id"] = user_id

        if status:
            filter_query["status"] = status

        personas = await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("name", 1)]
        )

        # Mask credentials in response
        for persona in personas:
            if "credentials" in persona:
                persona["credentials"] = {"_encrypted": True}

        return personas

    async def update_credentials(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update only the credentials of a persona.

        Args:
            persona_id: String representation of the persona's ObjectId
            credentials: New credentials to store

        Returns:
            Updated persona document (credentials masked), or None if not found

        Raises:
            ValueError: If persona_id is not a valid ObjectId string
        """
        return await self.update(persona_id, {"credentials": credentials})

    async def exists_for_user(self, user_id: str, name: str) -> bool:
        """
        Check if a persona with the given name exists for a user.

        Useful for preventing duplicate persona names per user.

        Args:
            user_id: The user's ID
            name: The persona name to check

        Returns:
            True if a persona with that name exists for the user
        """
        return await self.exists({
            "user_id": user_id,
            "name": name
        })
