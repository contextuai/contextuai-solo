"""
User Profile Repository for Profile Management

Repository class for managing user profiles in MongoDB.
Handles display name, bio, avatar, social links, skills, interests, etc.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime

from .base_repository import BaseRepository


class UserProfileRepository(BaseRepository):
    """
    Repository for user profile management.

    Manages the 'user_profiles' collection in MongoDB, providing methods for
    creating, retrieving, updating, and deleting user profile records.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for user profiles
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the UserProfileRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "user_profiles")

    async def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a user profile by user ID.

        Args:
            user_id: The user's unique identifier

        Returns:
            User profile document with id field, or None if not found
        """
        return await self.get_one({"user_id": user_id})

    async def create_profile(
        self,
        user_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new user profile.

        Args:
            user_id: User's unique identifier
            data: Profile data including:
                - display_name: Display name
                - bio: User biography
                - avatar_url: Avatar image URL
                - phone: Phone number
                - timezone: User's timezone
                - location: User's location
                - social_links: Dict of social media links
                - job_title: Job title
                - company: Company name
                - skills: List of skills
                - interests: List of interests

        Returns:
            Created profile document with id field

        Raises:
            ValueError: If profile already exists for user_id
        """
        # Check if profile already exists
        existing = await self.get_by_user_id(user_id)
        if existing:
            raise ValueError(f"Profile already exists for user '{user_id}'")

        profile_data = {
            "user_id": user_id,
            "display_name": data.get("display_name"),
            "bio": data.get("bio"),
            "avatar_url": data.get("avatar_url"),
            "phone": data.get("phone"),
            "timezone": data.get("timezone"),
            "location": data.get("location"),
            "social_links": data.get("social_links"),
            "job_title": data.get("job_title"),
            "company": data.get("company"),
            "skills": data.get("skills", []),
            "interests": data.get("interests", []),
        }

        # Remove None values to keep document clean
        profile_data = {k: v for k, v in profile_data.items() if v is not None}
        profile_data["user_id"] = user_id  # Ensure user_id is always present

        return await super().create(profile_data)

    async def update_profile(
        self,
        user_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing user profile.

        Args:
            user_id: The user's unique identifier
            data: Fields to update (partial update supported)

        Returns:
            Updated profile document with id field, or None if not found
        """
        profile = await self.get_by_user_id(user_id)
        if not profile:
            return None

        return await super().update(profile["id"], data)

    async def upsert_profile(
        self,
        user_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a user profile or create it if it doesn't exist.

        Args:
            user_id: The user's unique identifier
            data: Profile data to upsert

        Returns:
            Updated or created profile document with id field
        """
        data["user_id"] = user_id
        return await self.upsert({"user_id": user_id}, data)

    async def delete_profile(self, user_id: str) -> bool:
        """
        Delete a user profile.

        Args:
            user_id: The user's unique identifier

        Returns:
            True if profile was deleted, False if not found
        """
        profile = await self.get_by_user_id(user_id)
        if not profile:
            return False

        return await super().delete(profile["id"])

    async def get_all_profiles(
        self,
        skip: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all user profiles with pagination.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of profile documents
        """
        return await self.get_all(
            skip=skip,
            limit=limit,
            sort=[("updated_at", -1)]
        )

    def calculate_completion(self, profile_data: Dict[str, Any]) -> int:
        """
        Calculate profile completion percentage.

        Args:
            profile_data: Profile document

        Returns:
            Completion percentage (0-100)
        """
        fields_to_check = [
            'display_name', 'bio', 'avatar_url', 'phone', 'timezone',
            'location', 'job_title', 'company', 'skills', 'interests'
        ]

        completed_fields = 0
        total_fields = len(fields_to_check)

        for field in fields_to_check:
            value = profile_data.get(field)
            if value is not None and value != "" and value != []:
                completed_fields += 1

        # Social links count as one field
        if profile_data.get('social_links'):
            social_links = profile_data['social_links']
            if any(social_links.values()):
                completed_fields += 1
            total_fields += 1

        return int((completed_fields / total_fields) * 100) if total_fields > 0 else 0
