"""
Session Repository for Chat Sessions

Provides CRUD operations and business logic for chat sessions.
Uses MongoDB as the backend storage with async operations.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository


class SessionRepository(BaseRepository):
    """
    Repository for managing chat sessions in MongoDB.

    Collection: 'sessions'

    Session Schema:
        - id: ObjectId (auto-generated)
        - user_id: str (required)
        - title: str (optional)
        - persona_id: str (optional)
        - model_id: str (optional)
        - status: str ('active', 'archived', 'deleted')
        - message_count: int
        - token_count: int
        - last_message_at: str (ISO datetime)
        - created_at: str (ISO datetime)
        - updated_at: str (ISO datetime)
    """

    COLLECTION_NAME = "sessions"

    # Valid session statuses
    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"
    STATUS_DELETED = "deleted"
    VALID_STATUSES = [STATUS_ACTIVE, STATUS_ARCHIVED, STATUS_DELETED]

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the session repository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, self.COLLECTION_NAME)

    async def create_session(
        self,
        user_id: str,
        title: Optional[str] = None,
        persona_id: Optional[str] = None,
        model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new chat session.

        Args:
            user_id: The ID of the user creating the session
            title: Optional title for the session
            persona_id: Optional persona ID associated with the session
            model_id: Optional AI model ID to use for the session

        Returns:
            Created session document with id field
        """
        session_data = {
            "user_id": user_id,
            "title": title or "New Chat",
            "persona_id": persona_id,
            "model_id": model_id,
            "status": self.STATUS_ACTIVE,
            "message_count": 0,
            "token_count": 0,
            "last_message_at": None
        }

        return await self.create(session_data)

    async def get_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a session by its ID.

        Args:
            session_id: The session's ObjectId as string

        Returns:
            Session document with id field, or None if not found

        Raises:
            ValueError: If session_id is not a valid ObjectId
        """
        return await super().get_by_id(session_id)

    async def get_user_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get sessions for a specific user with pagination and filtering.

        Args:
            user_id: The user's ID
            limit: Maximum number of sessions to return (default: 20)
            offset: Number of sessions to skip for pagination (default: 0)
            status: Optional filter by status ('active', 'archived', 'deleted')
                    If None, returns only 'active' sessions

        Returns:
            List of session documents sorted by last_message_at descending

        Raises:
            ValueError: If status is provided but not a valid status
        """
        # Validate status if provided
        if status is not None and status not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid status: {status}. Must be one of {self.VALID_STATUSES}"
            )

        # Build filter
        filter_query: Dict[str, Any] = {"user_id": user_id}
        if status:
            filter_query["status"] = status
        else:
            # Default to active sessions
            filter_query["status"] = self.STATUS_ACTIVE

        # Sort by last_message_at descending, with created_at as fallback
        # Using a compound sort: sessions with messages first, then by date
        sort_order = [
            ("last_message_at", -1),
            ("created_at", -1)
        ]

        return await self.get_all(
            filter=filter_query,
            skip=offset,
            limit=limit,
            sort=sort_order
        )

    async def update_session(
        self,
        session_id: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update a session with the provided data.

        Args:
            session_id: The session's ObjectId as string
            data: Dictionary of fields to update

        Returns:
            Updated session document, or None if not found

        Raises:
            ValueError: If session_id is not a valid ObjectId
        """
        # Validate status if being updated
        if "status" in data and data["status"] not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid status: {data['status']}. Must be one of {self.VALID_STATUSES}"
            )

        return await self.update(session_id, data)

    async def update_stats(
        self,
        session_id: str,
        message_count: Optional[int] = None,
        token_count: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update session statistics (message count, token count).

        Args:
            session_id: The session's ObjectId as string
            message_count: New total message count (if provided)
            token_count: New total token count (if provided)

        Returns:
            Updated session document, or None if not found

        Note:
            Also updates last_message_at to current timestamp
        """
        update_data: Dict[str, Any] = {
            "last_message_at": datetime.utcnow().isoformat()
        }

        if message_count is not None:
            update_data["message_count"] = message_count

        if token_count is not None:
            update_data["token_count"] = token_count

        return await self.update(session_id, update_data)

    async def increment_stats(
        self,
        session_id: str,
        message_increment: int = 1,
        token_increment: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Increment session statistics atomically.

        Args:
            session_id: The session's ObjectId as string
            message_increment: Amount to add to message_count (default: 1)
            token_increment: Amount to add to token_count (default: 0)

        Returns:
            Updated session document, or None if not found
        """
        object_id = self._to_object_id(session_id)

        result = await self.collection.find_one_and_update(
            {"_id": object_id},
            {
                "$inc": {
                    "message_count": message_increment,
                    "token_count": token_increment
                },
                "$set": {
                    "last_message_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def archive_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Archive a session (soft archive by setting status to 'archived').

        Args:
            session_id: The session's ObjectId as string

        Returns:
            Updated session document, or None if not found
        """
        return await self.update(session_id, {"status": self.STATUS_ARCHIVED})

    async def restore_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Restore an archived or deleted session to active status.

        Args:
            session_id: The session's ObjectId as string

        Returns:
            Updated session document, or None if not found
        """
        return await self.update(session_id, {"status": self.STATUS_ACTIVE})

    async def delete_session(
        self,
        session_id: str,
        hard_delete: bool = False
    ) -> bool:
        """
        Delete a session.

        Args:
            session_id: The session's ObjectId as string
            hard_delete: If True, permanently removes the document.
                        If False (default), sets status to 'deleted'.

        Returns:
            True if session was deleted/updated, False if not found
        """
        if hard_delete:
            return await self.delete(session_id)
        else:
            result = await self.update(session_id, {"status": self.STATUS_DELETED})
            return result is not None

    async def get_sessions_by_persona(
        self,
        user_id: str,
        persona_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get sessions for a specific user and persona.

        Args:
            user_id: The user's ID
            persona_id: The persona's ID
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of session documents sorted by last_message_at descending
        """
        filter_query = {
            "user_id": user_id,
            "persona_id": persona_id,
            "status": self.STATUS_ACTIVE
        }

        return await self.get_all(
            filter=filter_query,
            skip=offset,
            limit=limit,
            sort=[("last_message_at", -1), ("created_at", -1)]
        )

    async def search_sessions(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search sessions by title for a specific user.

        Args:
            user_id: The user's ID
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of matching session documents
        """
        filter_query = {
            "user_id": user_id,
            "status": self.STATUS_ACTIVE,
            "title": {"$regex": query, "$options": "i"}  # Case-insensitive search
        }

        return await self.get_all(
            filter=filter_query,
            limit=limit,
            sort=[("last_message_at", -1)]
        )

    async def count_user_sessions(
        self,
        user_id: str,
        status: Optional[str] = None
    ) -> int:
        """
        Count sessions for a specific user.

        Args:
            user_id: The user's ID
            status: Optional filter by status

        Returns:
            Number of sessions matching the criteria
        """
        filter_query: Dict[str, Any] = {"user_id": user_id}
        if status:
            filter_query["status"] = status
        else:
            filter_query["status"] = self.STATUS_ACTIVE

        return await self.count(filter_query)

    async def bulk_archive(
        self,
        session_ids: List[str]
    ) -> int:
        """
        Archive multiple sessions at once.

        Args:
            session_ids: List of session ObjectIds as strings

        Returns:
            Number of sessions archived
        """
        object_ids = [self._to_object_id(sid) for sid in session_ids]

        result = await self.collection.update_many(
            {"_id": {"$in": object_ids}},
            {
                "$set": {
                    "status": self.STATUS_ARCHIVED,
                    "updated_at": datetime.utcnow().isoformat()
                }
            }
        )

        return result.modified_count

    async def bulk_delete(
        self,
        session_ids: List[str],
        hard_delete: bool = False
    ) -> int:
        """
        Delete multiple sessions at once.

        Args:
            session_ids: List of session ObjectIds as strings
            hard_delete: If True, permanently removes the documents

        Returns:
            Number of sessions deleted
        """
        object_ids = [self._to_object_id(sid) for sid in session_ids]

        if hard_delete:
            result = await self.collection.delete_many({"_id": {"$in": object_ids}})
            return result.deleted_count
        else:
            result = await self.collection.update_many(
                {"_id": {"$in": object_ids}},
                {
                    "$set": {
                        "status": self.STATUS_DELETED,
                        "updated_at": datetime.utcnow().isoformat()
                    }
                }
            )
            return result.modified_count
