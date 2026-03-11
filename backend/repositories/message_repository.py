"""
Message Repository for Chat Messages

Provides CRUD operations and business logic for chat messages.
Uses MongoDB as the backend storage with async operations.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_repository import BaseRepository


class MessageRepository(BaseRepository):
    """
    Repository for managing chat messages in MongoDB.

    Collection: 'messages'

    Message Schema:
        - id: ObjectId (auto-generated)
        - session_id: str (required, references sessions collection)
        - message_type: str ('user', 'assistant', 'system')
        - content: str (required)
        - metadata: Dict[str, Any] (optional, for tokens, model info, etc.)
        - timestamp: str (ISO datetime, message creation time)
        - created_at: str (ISO datetime)
        - updated_at: str (ISO datetime)
    """

    COLLECTION_NAME = "messages"

    # Valid message types
    TYPE_USER = "user"
    TYPE_ASSISTANT = "assistant"
    TYPE_SYSTEM = "system"
    VALID_TYPES = [TYPE_USER, TYPE_ASSISTANT, TYPE_SYSTEM]

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the message repository.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        super().__init__(db, self.COLLECTION_NAME)

    async def create_message(
        self,
        session_id: str,
        message_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new chat message.

        Args:
            session_id: The ID of the session this message belongs to
            message_type: Type of message ('user', 'assistant', 'system')
            content: The message content/text
            metadata: Optional metadata (tokens, model info, etc.)

        Returns:
            Created message document with id field

        Raises:
            ValueError: If message_type is not valid
        """
        if message_type not in self.VALID_TYPES:
            raise ValueError(
                f"Invalid message_type: {message_type}. Must be one of {self.VALID_TYPES}"
            )

        message_data = {
            "session_id": session_id,
            "message_type": message_type,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        return await self.create(message_data)

    async def get_session_messages(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all messages for a specific session.

        Args:
            session_id: The session's ID
            limit: Maximum number of messages to return (default: 50)
            offset: Number of messages to skip for pagination (default: 0)

        Returns:
            List of message documents sorted by timestamp ascending (oldest first)
        """
        filter_query = {"session_id": session_id}

        # Sort by timestamp ascending - oldest messages first for chat history
        return await self.get_all(
            filter=filter_query,
            skip=offset,
            limit=limit,
            sort=[("timestamp", 1)]  # 1 = ascending
        )

    async def get_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a message by its ID.

        Args:
            message_id: The message's ObjectId as string

        Returns:
            Message document with id field, or None if not found

        Raises:
            ValueError: If message_id is not a valid ObjectId
        """
        return await super().get_by_id(message_id)

    async def search_messages(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search messages across all user's sessions.

        This performs a text search on message content, joining with sessions
        to filter by user.

        Args:
            user_id: The user's ID to search within
            query: Search query string
            limit: Maximum number of results to return (default: 20)

        Returns:
            List of matching message documents with session info
        """
        # Use aggregation to join with sessions and filter by user
        pipeline = [
            # First, lookup the session to get user_id
            {
                "$lookup": {
                    "from": "sessions",
                    "localField": "session_id",
                    "foreignField": "_id",
                    "as": "session"
                }
            },
            # Unwind the session array (it will be single element)
            {"$unwind": "$session"},
            # Filter by user_id and status
            {
                "$match": {
                    "session.user_id": user_id,
                    "session.status": {"$ne": "deleted"},
                    "content": {"$regex": query, "$options": "i"}
                }
            },
            # Sort by timestamp descending (most recent first)
            {"$sort": {"timestamp": -1}},
            # Limit results
            {"$limit": limit},
            # Project the fields we need
            {
                "$project": {
                    "_id": 1,
                    "session_id": 1,
                    "message_type": 1,
                    "content": 1,
                    "metadata": 1,
                    "timestamp": 1,
                    "created_at": 1,
                    "session_title": "$session.title"
                }
            }
        ]

        return await self.aggregate(pipeline)

    async def delete_message(self, message_id: str) -> bool:
        """
        Delete a message by its ID.

        Args:
            message_id: The message's ObjectId as string

        Returns:
            True if message was deleted, False if not found

        Raises:
            ValueError: If message_id is not a valid ObjectId
        """
        return await self.delete(message_id)

    async def delete_session_messages(self, session_id: str) -> int:
        """
        Delete all messages for a specific session.

        Args:
            session_id: The session's ID

        Returns:
            Number of messages deleted
        """
        return await self.delete_many({"session_id": session_id})

    async def get_messages_by_type(
        self,
        session_id: str,
        message_type: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get messages of a specific type from a session.

        Args:
            session_id: The session's ID
            message_type: Type of messages to retrieve ('user', 'assistant', 'system')
            limit: Maximum number of messages to return

        Returns:
            List of message documents sorted by timestamp ascending

        Raises:
            ValueError: If message_type is not valid
        """
        if message_type not in self.VALID_TYPES:
            raise ValueError(
                f"Invalid message_type: {message_type}. Must be one of {self.VALID_TYPES}"
            )

        filter_query = {
            "session_id": session_id,
            "message_type": message_type
        }

        return await self.get_all(
            filter=filter_query,
            limit=limit,
            sort=[("timestamp", 1)]
        )

    async def count_session_messages(self, session_id: str) -> int:
        """
        Count total messages in a session.

        Args:
            session_id: The session's ID

        Returns:
            Number of messages in the session
        """
        return await self.count({"session_id": session_id})

    async def get_latest_messages(
        self,
        session_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get the most recent messages from a session.

        Args:
            session_id: The session's ID
            limit: Number of recent messages to retrieve

        Returns:
            List of message documents sorted by timestamp descending (newest first)
        """
        filter_query = {"session_id": session_id}

        return await self.get_all(
            filter=filter_query,
            limit=limit,
            sort=[("timestamp", -1)]  # -1 = descending (newest first)
        )

    async def get_context_messages(
        self,
        session_id: str,
        limit: int = 10,
        include_system: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get recent messages formatted for AI context.

        Retrieves the most recent messages and returns them in chronological order
        (oldest to newest) suitable for providing context to an AI model.

        Args:
            session_id: The session's ID
            limit: Maximum number of messages to include in context
            include_system: Whether to include system messages

        Returns:
            List of message documents in chronological order (oldest first)
        """
        filter_query: Dict[str, Any] = {"session_id": session_id}

        if not include_system:
            filter_query["message_type"] = {"$ne": self.TYPE_SYSTEM}

        # Get latest messages (sorted descending)
        messages = await self.get_all(
            filter=filter_query,
            limit=limit,
            sort=[("timestamp", -1)]
        )

        # Reverse to get chronological order (oldest first)
        return list(reversed(messages))

    async def update_message_metadata(
        self,
        message_id: str,
        metadata: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update the metadata of a message.

        Args:
            message_id: The message's ObjectId as string
            metadata: Metadata to merge with existing metadata

        Returns:
            Updated message document, or None if not found
        """
        # Get current message to merge metadata
        current = await self.get_by_id(message_id)
        if not current:
            return None

        # Merge metadata
        current_metadata = current.get("metadata", {})
        current_metadata.update(metadata)

        return await self.update(message_id, {"metadata": current_metadata})

    async def bulk_create_messages(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Create multiple messages at once.

        Args:
            messages: List of message data dictionaries, each containing:
                - session_id: str
                - message_type: str
                - content: str
                - metadata: Optional[Dict[str, Any]]

        Returns:
            List of created message documents with id fields

        Raises:
            ValueError: If any message has an invalid message_type
        """
        # Validate all message types
        for msg in messages:
            if msg.get("message_type") not in self.VALID_TYPES:
                raise ValueError(
                    f"Invalid message_type: {msg.get('message_type')}. "
                    f"Must be one of {self.VALID_TYPES}"
                )

        # Add timestamps to each message
        prepared_messages = []
        for msg in messages:
            prepared_msg = {
                "session_id": msg["session_id"],
                "message_type": msg["message_type"],
                "content": msg["content"],
                "metadata": msg.get("metadata", {}),
                "timestamp": msg.get("timestamp", datetime.utcnow().isoformat())
            }
            prepared_messages.append(prepared_msg)

        return await self.create_many(prepared_messages)

    async def get_message_stats(self, session_id: str) -> Dict[str, Any]:
        """
        Get statistics about messages in a session.

        Args:
            session_id: The session's ID

        Returns:
            Dictionary containing:
                - total_count: Total number of messages
                - user_count: Number of user messages
                - assistant_count: Number of assistant messages
                - system_count: Number of system messages
                - first_message_at: Timestamp of first message
                - last_message_at: Timestamp of last message
        """
        pipeline = [
            {"$match": {"session_id": session_id}},
            {
                "$group": {
                    "_id": "$session_id",
                    "total_count": {"$sum": 1},
                    "user_count": {
                        "$sum": {"$cond": [{"$eq": ["$message_type", "user"]}, 1, 0]}
                    },
                    "assistant_count": {
                        "$sum": {"$cond": [{"$eq": ["$message_type", "assistant"]}, 1, 0]}
                    },
                    "system_count": {
                        "$sum": {"$cond": [{"$eq": ["$message_type", "system"]}, 1, 0]}
                    },
                    "first_message_at": {"$min": "$timestamp"},
                    "last_message_at": {"$max": "$timestamp"}
                }
            }
        ]

        results = await self.aggregate(pipeline, convert_ids=False)

        if results:
            result = results[0]
            result.pop("_id", None)
            return result

        # Return default stats if no messages
        return {
            "total_count": 0,
            "user_count": 0,
            "assistant_count": 0,
            "system_count": 0,
            "first_message_at": None,
            "last_message_at": None
        }

    async def export_session_messages(
        self,
        session_id: str,
        include_metadata: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Export all messages from a session for backup or export.

        Args:
            session_id: The session's ID
            include_metadata: Whether to include message metadata

        Returns:
            List of all messages in the session
        """
        projection = None
        if not include_metadata:
            projection = {
                "session_id": 1,
                "message_type": 1,
                "content": 1,
                "timestamp": 1
            }

        return await self.get_all(
            filter={"session_id": session_id},
            limit=10000,  # High limit for export
            sort=[("timestamp", 1)],
            projection=projection
        )
