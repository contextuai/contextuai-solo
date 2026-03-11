"""
User Settings Repository for Settings Management

Repository class for managing user settings in MongoDB.
Handles theme, notifications, privacy, chat, and language settings.
"""

from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime

from .base_repository import BaseRepository


class UserSettingsRepository(BaseRepository):
    """
    Repository for user settings management.

    Manages the 'user_settings' collection in MongoDB, providing methods for
    creating, retrieving, updating, and deleting user settings records.

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance for user settings
    """

    # Default settings for new users
    DEFAULT_THEME = {
        "mode": "light",
        "primary_color": "#007bff",
        "font_size": "medium",
        "compact_mode": False
    }

    DEFAULT_NOTIFICATIONS = {
        "email_notifications": True,
        "push_notifications": True,
        "chat_notifications": True,
        "system_notifications": True,
        "marketing_emails": False,
        "notification_sound": True,
        "quiet_hours_enabled": False,
        "quiet_hours_start": None,
        "quiet_hours_end": None
    }

    DEFAULT_PRIVACY = {
        "profile_visibility": "private",
        "show_online_status": True,
        "allow_direct_messages": True,
        "data_collection": True,
        "analytics_tracking": True,
        "session_recording": False
    }

    DEFAULT_CHAT = {
        "default_model": None,
        "message_history_limit": 100,
        "auto_save_sessions": True,
        "show_timestamps": True,
        "message_grouping": True,
        "typing_indicators": True,
        "read_receipts": True,
        "auto_scroll": True
    }

    DEFAULT_LANGUAGE = {
        "language": "en",
        "date_format": "MM/DD/YYYY",
        "time_format": "12h",
        "timezone": "UTC"
    }

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the UserSettingsRepository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, "user_settings")

    def get_default_settings(self) -> Dict[str, Any]:
        """
        Get default settings for new users.

        Returns:
            Dictionary with default settings for all categories
        """
        return {
            "theme": self.DEFAULT_THEME.copy(),
            "notifications": self.DEFAULT_NOTIFICATIONS.copy(),
            "privacy": self.DEFAULT_PRIVACY.copy(),
            "chat": self.DEFAULT_CHAT.copy(),
            "language": self.DEFAULT_LANGUAGE.copy()
        }

    async def get_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve user settings by user ID.

        Args:
            user_id: The user's unique identifier

        Returns:
            User settings document with id field, or None if not found
        """
        return await self.get_one({"user_id": user_id})

    async def get_or_create(self, user_id: str) -> Dict[str, Any]:
        """
        Get user settings or create defaults if they don't exist.

        Args:
            user_id: The user's unique identifier

        Returns:
            User settings document (existing or newly created)
        """
        settings = await self.get_by_user_id(user_id)
        if settings:
            return settings

        # Create default settings
        return await self.create_settings(user_id, {})

    async def create_settings(
        self,
        user_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create new user settings.

        Args:
            user_id: User's unique identifier
            data: Settings data (will be merged with defaults)

        Returns:
            Created settings document with id field

        Raises:
            ValueError: If settings already exist for user_id
        """
        # Check if settings already exist
        existing = await self.get_by_user_id(user_id)
        if existing:
            raise ValueError(f"Settings already exist for user '{user_id}'")

        # Start with defaults
        settings_data = self.get_default_settings()
        settings_data["user_id"] = user_id

        # Merge provided settings
        for category in ["theme", "notifications", "privacy", "chat", "language"]:
            if category in data and data[category]:
                if isinstance(data[category], dict):
                    settings_data[category].update(data[category])

        return await super().create(settings_data)

    async def update_settings(
        self,
        user_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update existing user settings.

        Args:
            user_id: The user's unique identifier
            data: Settings categories to update (partial update supported)

        Returns:
            Updated settings document with id field, or None if not found
        """
        settings = await self.get_by_user_id(user_id)
        if not settings:
            return None

        # Merge updates with existing settings
        update_data = {}
        for category in ["theme", "notifications", "privacy", "chat", "language"]:
            if category in data and data[category]:
                current = settings.get(category, {})
                if isinstance(data[category], dict):
                    current.update(data[category])
                else:
                    current = data[category]
                update_data[category] = current

        if not update_data:
            return settings

        return await super().update(settings["id"], update_data)

    async def delete_settings(self, user_id: str) -> bool:
        """
        Delete user settings.

        Args:
            user_id: The user's unique identifier

        Returns:
            True if settings were deleted, False if not found
        """
        settings = await self.get_by_user_id(user_id)
        if not settings:
            return False

        return await super().delete(settings["id"])

    async def reset_settings(self, user_id: str) -> Dict[str, Any]:
        """
        Reset user settings to defaults.

        Args:
            user_id: The user's unique identifier

        Returns:
            Reset settings document with id field
        """
        # Delete existing settings
        await self.delete_settings(user_id)

        # Create new default settings
        return await self.create_settings(user_id, {})

    async def update_category(
        self,
        user_id: str,
        category: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a specific settings category.

        Args:
            user_id: The user's unique identifier
            category: Settings category (theme, notifications, privacy, chat, language)
            data: Category-specific settings to update

        Returns:
            Updated settings document, or None if not found
        """
        if category not in ["theme", "notifications", "privacy", "chat", "language"]:
            raise ValueError(f"Invalid settings category: {category}")

        settings = await self.get_or_create(user_id)
        current_category = settings.get(category, {})
        current_category.update(data)

        return await super().update(settings["id"], {category: current_category})

    async def get_category(
        self,
        user_id: str,
        category: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific settings category.

        Args:
            user_id: The user's unique identifier
            category: Settings category (theme, notifications, privacy, chat, language)

        Returns:
            Category settings dict, or None if not found
        """
        if category not in ["theme", "notifications", "privacy", "chat", "language"]:
            raise ValueError(f"Invalid settings category: {category}")

        settings = await self.get_or_create(user_id)
        return settings.get(category)
