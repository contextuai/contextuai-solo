"""
User Repository for User Management

Repository class for managing users in MongoDB.
Provides methods for CRUD operations with email-based lookups.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid

from .base_repository import BaseRepository


class UserRepository(BaseRepository):
    """
    Repository for user management.

    Manages the 'users' collection in MongoDB, providing methods for
    creating, retrieving, updating, and deleting user records.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for users
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the UserRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "users")

    async def create(
        self,
        email: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new user.

        Args:
            email: User's email address (must be unique)
            data: Additional user data including:
                - first_name: User's first name
                - last_name: User's last name
                - role: User's role ('standardUser', 'powerUser', 'admin', etc.)
                - title: Job title
                - group: User's group
                - department: User's department
                - organization: Organization name
                - cognito_sub: AWS Cognito user ID (optional)

        Returns:
            Created user document with id field

        Raises:
            ValueError: If email already exists
        """
        # Check if email already exists
        existing = await self.get_by_email(email)
        if existing:
            raise ValueError(f"User with email '{email}' already exists")

        user_data = {
            "user_id": str(uuid.uuid4()),
            "email": email,
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "role": data.get("role", "standardUser"),
            "title": data.get("title", ""),
            "group": data.get("group", ""),
            "department": data.get("department", ""),
            "organization": data.get("organization", "default"),
            "status": data.get("status", "active"),
            "password_set": data.get("password_set", False),
            "cognito_sub": data.get("cognito_sub"),
            "in_cognito": data.get("in_cognito", False),
            "last_login": None,
            **{k: v for k, v in data.items() if k not in [
                "email", "first_name", "last_name", "role", "title",
                "group", "department", "organization", "status",
                "password_set", "cognito_sub", "in_cognito", "last_login"
            ]}
        }

        return await super().create(user_data)

    async def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a user by their ID.

        Args:
            user_id: The user's unique identifier (user_id field)

        Returns:
            User document with id field, or None if not found
        """
        # First try by user_id field
        user = await self.get_one({"user_id": user_id})
        if user:
            return user

        # Also try by cognito_sub (used as user_id in some cases)
        user = await self.get_one({"cognito_sub": user_id})
        if user:
            return user

        # Fall back to MongoDB _id
        try:
            return await super().get_by_id(user_id)
        except ValueError:
            return None

    async def get_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a user by their email address.

        Args:
            email: User's email address

        Returns:
            User document with id field, or None if not found
        """
        return await self.get_one({"email": email.lower()})

    async def update(
        self,
        user_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing user.

        Args:
            user_id: The user's unique identifier
            data: Fields to update (partial update supported)

        Returns:
            Updated user document with id field, or None if not found
        """
        # Find the user first
        user = await self.get_by_id(user_id)
        if not user:
            return None

        # Check if email is being changed and if it's already taken
        if "email" in data and data["email"].lower() != user.get("email", "").lower():
            existing = await self.get_by_email(data["email"])
            if existing:
                raise ValueError(f"Email '{data['email']}' is already in use")
            data["email"] = data["email"].lower()

        return await super().update(user["id"], data)

    async def delete(self, user_id: str) -> bool:
        """
        Delete a user (soft delete by setting status to 'inactive').

        Args:
            user_id: The user's unique identifier

        Returns:
            True if user was deleted, False if not found
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False

        # Soft delete - set status to inactive
        await super().update(user["id"], {"status": "inactive"})
        return True

    async def hard_delete(self, user_id: str) -> bool:
        """
        Permanently delete a user.

        Args:
            user_id: The user's unique identifier

        Returns:
            True if user was deleted, False if not found
        """
        user = await self.get_by_id(user_id)
        if not user:
            return False

        return await super().delete(user["id"])

    async def get_by_role(
        self,
        role: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve users by role.

        Args:
            role: The user role ('standardUser', 'powerUser', 'admin', etc.)
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of user documents matching the role
        """
        return await self.get_all(
            filter={"role": role, "status": "active"},
            skip=skip,
            limit=limit,
            sort=[("last_name", 1), ("first_name", 1)]
        )

    async def get_by_department(
        self,
        department: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve users by department.

        Args:
            department: The department name
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of user documents in the department
        """
        return await self.get_all(
            filter={"department": department, "status": "active"},
            skip=skip,
            limit=limit,
            sort=[("last_name", 1), ("first_name", 1)]
        )

    async def get_by_organization(
        self,
        organization: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve users by organization.

        Args:
            organization: The organization name
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of user documents in the organization
        """
        return await self.get_all(
            filter={"organization": organization, "status": "active"},
            skip=skip,
            limit=limit,
            sort=[("last_name", 1), ("first_name", 1)]
        )

    async def get_active_users(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all active users.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of active user documents
        """
        return await self.get_all(
            filter={"status": "active"},
            skip=skip,
            limit=limit,
            sort=[("last_name", 1), ("first_name", 1)]
        )

    async def search(
        self,
        search_term: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search users by name or email.

        Args:
            search_term: Search term to match against name or email
            limit: Maximum number of results

        Returns:
            List of matching user documents
        """
        return await self.get_all(
            filter={
                "status": "active",
                "$or": [
                    {"email": {"$regex": search_term, "$options": "i"}},
                    {"first_name": {"$regex": search_term, "$options": "i"}},
                    {"last_name": {"$regex": search_term, "$options": "i"}}
                ]
            },
            limit=limit,
            sort=[("last_name", 1), ("first_name", 1)]
        )

    async def update_last_login(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Update the user's last login timestamp.

        Args:
            user_id: The user's unique identifier

        Returns:
            Updated user document, or None if not found
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None

        return await super().update(user["id"], {
            "last_login": datetime.utcnow().isoformat()
        })

    async def set_password_flag(
        self,
        user_id: str,
        password_set: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Update the password_set flag for a user.

        Args:
            user_id: The user's unique identifier
            password_set: Whether password has been set

        Returns:
            Updated user document, or None if not found
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None

        return await super().update(user["id"], {"password_set": password_set})

    async def set_password_hash(
        self,
        user_id: str,
        password_hash: str
    ) -> Optional[Dict[str, Any]]:
        """
        Set the password hash for a user.

        Args:
            user_id: The user's unique identifier
            password_hash: Hashed password string

        Returns:
            Updated user document, or None if not found
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None

        return await super().update(user["id"], {
            "password_hash": password_hash,
            "password_set": True
        })

    async def count_by_role(self) -> Dict[str, int]:
        """
        Count users by role.

        Returns:
            Dictionary with role counts and total
        """
        roles = ["standardUser", "powerUser", "admin", "engineer", "superAdmin"]
        counts = {}

        for role in roles:
            counts[role] = await self.count({"role": role, "status": "active"})

        counts["total"] = sum(counts.values())
        return counts

    async def count_by_department(self) -> Dict[str, int]:
        """
        Count users by department.

        Returns:
            Dictionary with department counts
        """
        departments = await self.distinct("department", {"status": "active"})
        counts = {}

        for dept in departments:
            if dept:
                counts[dept] = await self.count({"department": dept, "status": "active"})

        return counts

    async def get_by_cognito_sub(self, cognito_sub: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a user by their Cognito user ID.

        Args:
            cognito_sub: AWS Cognito user ID

        Returns:
            User document with id field, or None if not found
        """
        return await self.get_one({"cognito_sub": cognito_sub})

    async def link_cognito(
        self,
        user_id: str,
        cognito_sub: str
    ) -> Optional[Dict[str, Any]]:
        """
        Link a Cognito user ID to an existing user.

        Args:
            user_id: The user's unique identifier
            cognito_sub: AWS Cognito user ID

        Returns:
            Updated user document, or None if not found
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None

        return await super().update(user["id"], {
            "cognito_sub": cognito_sub,
            "in_cognito": True
        })
