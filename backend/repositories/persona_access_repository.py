"""
Persona Access Repository for Persona Access Management

Repository class for managing persona access records in MongoDB.
Provides methods for CRUD operations with filtering by user, persona, and access status.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class PersonaAccessRepository(BaseRepository):
    """
    Repository for persona access management.

    Manages the 'persona_access' collection in MongoDB, providing methods for
    creating, retrieving, updating, and deleting persona access records.

    Persona access records define which users have access to which personas,
    with access levels, expiration dates, and favorite status.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for persona_access
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the PersonaAccessRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "persona_access")

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new persona access record.

        Args:
            data: Access data including:
                - user_id: User's ID
                - persona_id: Persona's ID
                - granted_by: Admin user ID who granted access
                - access_level: Access level ('read', 'write', 'admin')
                - expires_at: Optional expiration datetime string
                - notes: Optional notes

        Returns:
            Created access record with id field
        """
        # Generate access_id if not provided
        if "access_id" not in data:
            data["access_id"] = str(uuid.uuid4())

        # Set default values
        now = datetime.utcnow().isoformat() + "Z"
        data.setdefault("granted_at", now)
        data.setdefault("is_favorite", False)
        data.setdefault("is_active", True)

        return await super().create(data)

    async def get_by_access_id(self, access_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an access record by its access_id.

        Args:
            access_id: The access record's unique identifier

        Returns:
            Access record with id field, or None if not found
        """
        return await self.get_one({"access_id": access_id})

    async def get_by_user(
        self,
        user_id: str,
        is_active: Optional[bool] = True,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all access records for a specific user.

        Args:
            user_id: The user's ID
            is_active: Filter by active status (default True)
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of access records for the user
        """
        filter_query: Dict[str, Any] = {"user_id": user_id}

        if is_active is not None:
            filter_query["is_active"] = is_active

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("granted_at", -1)]
        )

    async def get_by_persona(
        self,
        persona_id: str,
        is_active: Optional[bool] = True,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all access records for a specific persona.

        Args:
            persona_id: The persona's ID
            is_active: Filter by active status (default True)
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of access records for the persona
        """
        filter_query: Dict[str, Any] = {"persona_id": persona_id}

        if is_active is not None:
            filter_query["is_active"] = is_active

        return await self.get_all(
            filter=filter_query,
            skip=skip,
            limit=limit,
            sort=[("granted_at", -1)]
        )

    async def get_user_persona_access(
        self,
        user_id: str,
        persona_id: str,
        is_active: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific user's access to a specific persona.

        Args:
            user_id: The user's ID
            persona_id: The persona's ID
            is_active: Filter by active status

        Returns:
            Access record if found, None otherwise
        """
        filter_query: Dict[str, Any] = {
            "user_id": user_id,
            "persona_id": persona_id,
            "is_active": is_active
        }

        return await self.get_one(filter_query)

    async def update_by_access_id(
        self,
        access_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an access record by its access_id.

        Args:
            access_id: The access record's unique identifier
            data: Fields to update

        Returns:
            Updated access record, or None if not found
        """
        access = await self.get_by_access_id(access_id)
        if not access:
            return None

        return await super().update(access["id"], data)

    async def revoke_access(self, access_id: str) -> bool:
        """
        Revoke access by setting is_active to False.

        Args:
            access_id: The access record's unique identifier

        Returns:
            True if access was revoked, False if not found
        """
        access = await self.get_by_access_id(access_id)
        if not access:
            return False

        await super().update(access["id"], {"is_active": False})
        return True

    async def toggle_favorite(self, access_id: str) -> Optional[Dict[str, Any]]:
        """
        Toggle the favorite status of an access record.

        Args:
            access_id: The access record's unique identifier

        Returns:
            Updated access record with new favorite status, or None if not found
        """
        access = await self.get_by_access_id(access_id)
        if not access:
            return None

        new_favorite = not access.get("is_favorite", False)
        return await super().update(access["id"], {"is_favorite": new_favorite})

    async def count_by_user(self, user_id: str, is_active: bool = True) -> int:
        """
        Count access records for a user.

        Args:
            user_id: The user's ID
            is_active: Filter by active status

        Returns:
            Number of access records for the user
        """
        return await self.count({"user_id": user_id, "is_active": is_active})

    async def count_by_persona(self, persona_id: str, is_active: bool = True) -> int:
        """
        Count access records for a persona.

        Args:
            persona_id: The persona's ID
            is_active: Filter by active status

        Returns:
            Number of access records for the persona
        """
        return await self.count({"persona_id": persona_id, "is_active": is_active})

    async def count_favorites_by_user(self, user_id: str) -> int:
        """
        Count favorite personas for a user.

        Args:
            user_id: The user's ID

        Returns:
            Number of favorite personas for the user
        """
        return await self.count({
            "user_id": user_id,
            "is_active": True,
            "is_favorite": True
        })

    async def get_favorites_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get favorite access records for a user.

        Args:
            user_id: The user's ID
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of favorite access records for the user
        """
        return await self.get_all(
            filter={
                "user_id": user_id,
                "is_active": True,
                "is_favorite": True
            },
            skip=skip,
            limit=limit,
            sort=[("granted_at", -1)]
        )

    async def get_access_analytics_for_persona(
        self,
        persona_id: str
    ) -> Dict[str, Any]:
        """
        Get analytics for persona access.

        Args:
            persona_id: The persona's ID

        Returns:
            Analytics data including total users, active users, favorites, etc.
        """
        # Get all access records for this persona
        all_records = await self.get_all(
            filter={"persona_id": persona_id}
        )

        total_users = len(all_records)
        active_users = len([r for r in all_records if r.get("is_active", True)])
        favorite_count = len([r for r in all_records if r.get("is_favorite", False)])

        # Access levels distribution
        access_levels: Dict[str, int] = {}
        for record in all_records:
            if record.get("is_active", True):
                level = record.get("access_level", "read")
                access_levels[level] = access_levels.get(level, 0) + 1

        return {
            "total_users_granted": total_users,
            "active_users": active_users,
            "users_favorited": favorite_count,
            "access_levels_distribution": access_levels
        }

    async def get_access_analytics_for_user(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get analytics for user's persona access.

        Args:
            user_id: The user's ID

        Returns:
            Analytics data including total personas, favorites, access levels, etc.
        """
        # Get all active access records for this user
        records = await self.get_by_user(user_id, is_active=True)

        total_personas = len(records)
        favorites_count = len([r for r in records if r.get("is_favorite", False)])

        # Access levels distribution
        access_levels: Dict[str, int] = {}
        for record in records:
            level = record.get("access_level", "read")
            access_levels[level] = access_levels.get(level, 0) + 1

        return {
            "total_personas_assigned": total_personas,
            "favorite_personas": favorites_count,
            "access_levels_distribution": access_levels
        }
