"""
Chat Messages Router - MongoDB Implementation

Provides REST API endpoints for managing chat messages using MongoDB.
Migrated from DynamoDB to use MessageRepository and SessionRepository.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timedelta

from database import get_database
from repositories import MessageRepository, SessionRepository

router = APIRouter(prefix="/api/v1/chat-messages", tags=["chat-messages"])


# =============================================================================
# Dependency Functions
# =============================================================================

async def get_message_repository() -> MessageRepository:
    """Get MessageRepository instance with database connection."""
    db = await get_database()
    return MessageRepository(db)


async def get_session_repository() -> SessionRepository:
    """Get SessionRepository instance with database connection."""
    db = await get_database()
    return SessionRepository(db)


# =============================================================================
# Pydantic Models for Validation
# =============================================================================

class MessageAttachment(BaseModel):
    filename: str
    file_type: str = Field(..., alias="fileType")
    file_size: int = Field(..., alias="fileSize")
    file_url: str = Field(..., alias="fileUrl")
    thumbnail_url: Optional[str] = Field(None, alias="thumbnailUrl")

    class Config:
        populate_by_name = True  # Accept both snake_case and camelCase
        by_alias = True  # Return camelCase by default


class MessageReaction(BaseModel):
    emoji: str
    count: int = 1
    users: List[str] = []


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    message_type: str = Field("user", pattern="^(user|assistant|system)$", alias="messageType")
    parent_message_id: Optional[str] = Field(None, alias="parentMessageId")
    attachments: Optional[List[MessageAttachment]] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        populate_by_name = True  # Accept both snake_case and camelCase
        by_alias = True  # Return camelCase by default


class MessageUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1, max_length=10000)
    metadata: Optional[Dict[str, Any]] = None


class MessageResponse(BaseModel):
    message_id: str = Field(..., alias="messageId")
    session_id: str = Field(..., alias="sessionId")
    content: str
    message_type: str = Field(..., alias="messageType")
    parent_message_id: Optional[str] = Field(None, alias="parentMessageId")
    attachments: Optional[List[MessageAttachment]] = None
    reactions: Optional[List[MessageReaction]] = None
    metadata: Optional[Dict[str, Any]] = None
    is_edited: bool = Field(False, alias="isEdited")
    is_deleted: bool = Field(False, alias="isDeleted")
    timestamp: str
    created_at: str = Field(..., alias="createdAt")
    updated_at: str = Field(..., alias="updatedAt")
    expires_at: str = Field("", alias="expiresAt")

    class Config:
        populate_by_name = True  # Accept both snake_case and camelCase
        by_alias = True  # Return camelCase by default


class MessagesListResponse(BaseModel):
    success: bool
    messages: List[MessageResponse]
    total_count: int = Field(..., alias="totalCount")
    has_more: bool = Field(..., alias="hasMore")
    last_evaluated_key: Optional[str] = Field(None, alias="lastEvaluatedKey")
    last_updated: str = Field(..., alias="lastUpdated")
    error: Optional[str] = None

    class Config:
        populate_by_name = True  # Accept both snake_case and camelCase
        by_alias = True  # Return camelCase by default


# =============================================================================
# Helper Functions
# =============================================================================

def calculate_expiry_date(days: int = 90) -> str:
    """Calculate expiry date for message TTL"""
    expiry_date = datetime.utcnow() + timedelta(days=days)
    return str(int(expiry_date.timestamp()))


def create_message_dict(session_id: str, message_data: MessageCreate, message_id: str = None) -> Dict[str, Any]:
    """Create message dictionary for MongoDB"""
    if not message_id:
        message_id = str(uuid.uuid4())

    now = datetime.utcnow().isoformat() + "Z"
    timestamp = now

    message_dict = {
        "session_id": session_id,
        "message_id": message_id,
        "content": message_data.content,
        "message_type": message_data.message_type,
        "timestamp": timestamp,
        "created_at": now,
        "updated_at": now,
        "expires_at": calculate_expiry_date(),
        "is_edited": False,
        "is_deleted": False
    }

    # Add optional fields
    if message_data.parent_message_id:
        message_dict["parent_message_id"] = message_data.parent_message_id
    if message_data.attachments:
        message_dict["attachments"] = [att.dict() for att in message_data.attachments]
    if message_data.metadata:
        message_dict["metadata"] = message_data.metadata

    return message_dict


def format_message_response(message_item: Dict[str, Any]) -> MessageResponse:
    """Format MongoDB document to MessageResponse"""
    # Handle both 'id' (from MongoDB) and 'message_id' (legacy format)
    message_id = message_item.get("message_id") or message_item.get("id", "")

    # Parse attachments
    attachments = None
    if message_item.get("attachments"):
        attachments = [MessageAttachment(**att) for att in message_item["attachments"]]

    # Parse reactions
    reactions = None
    if message_item.get("reactions"):
        reactions = [MessageReaction(**react) for react in message_item["reactions"]]

    return MessageResponse(
        message_id=message_id,
        session_id=message_item.get("session_id", ""),
        content=message_item.get("content", ""),
        message_type=message_item.get("message_type", "user"),
        parent_message_id=message_item.get("parent_message_id"),
        attachments=attachments,
        reactions=reactions,
        metadata=message_item.get("metadata"),
        is_edited=message_item.get("is_edited", False),
        is_deleted=message_item.get("is_deleted", False),
        timestamp=message_item.get("timestamp", ""),
        created_at=message_item.get("created_at", ""),
        updated_at=message_item.get("updated_at", ""),
        expires_at=message_item.get("expires_at", "")
    )


async def update_session_message_count(
    session_repo: SessionRepository,
    session_id: str,
    increment: int = 1
):
    """Update session message count and last message timestamp"""
    try:
        await session_repo.increment_stats(session_id, message_increment=increment)
    except Exception:
        # Don't fail message creation if session update fails
        pass


async def find_session(session_repo: SessionRepository, session_id: str) -> Optional[Dict[str, Any]]:
    """
    Find a session by session_id field (UUID) or MongoDB ObjectId.

    Args:
        session_repo: SessionRepository instance
        session_id: Session ID (UUID string or MongoDB ObjectId string)

    Returns:
        Session document if found, None otherwise
    """
    # First try to find by session_id field (UUID)
    session = await session_repo.get_one({"session_id": session_id})
    if session:
        return session

    # Fall back to MongoDB ObjectId lookup
    try:
        session = await session_repo.get_by_id(session_id)
        return session
    except ValueError:
        # Invalid ObjectId format
        return None


async def find_message(message_repo: MessageRepository, message_id: str) -> Optional[Dict[str, Any]]:
    """
    Find a message by message_id field (UUID) or MongoDB ObjectId.

    Args:
        message_repo: MessageRepository instance
        message_id: Message ID (UUID string or MongoDB ObjectId string)

    Returns:
        Message document if found, None otherwise
    """
    # First try to find by message_id field (UUID)
    message = await message_repo.get_one({"message_id": message_id})
    if message:
        return message

    # Fall back to MongoDB ObjectId lookup
    try:
        message = await message_repo.get_by_id(message_id)
        return message
    except ValueError:
        # Invalid ObjectId format
        return None


# =============================================================================
# Frontend-friendly Endpoints
# =============================================================================

@router.post("/")
async def create_message_simple(
    request: Dict[str, Any],
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """
    Create a new message - Frontend-friendly endpoint
    Accepts both camelCase (frontend) and snake_case (backend) field names
    """
    try:
        print(f"=== CREATE MESSAGE REQUEST ===")
        print(f"Request Body: {request}")

        # Extract fields - support both camelCase and snake_case
        message_id = request.get('message_id') or request.get('messageId')
        session_id = request.get('session_id') or request.get('sessionId')
        content = request.get('content')
        message_type = request.get('message_type') or request.get('messageType') or request.get('role')
        timestamp = request.get('timestamp')
        metadata = request.get('metadata', {})

        # Validate required fields
        if not message_id:
            raise HTTPException(status_code=400, detail="message_id is required")
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        if not message_type:
            raise HTTPException(status_code=400, detail="message_type is required")

        print(f"Extracted fields: message_id={message_id}, session_id={session_id}, message_type={message_type}")

        # Verify session exists
        session = await session_repo.get_by_id(session_id)
        if not session:
            print(f"ERROR: Session {session_id} not found")
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        # Create message dict
        now = datetime.utcnow().isoformat() + "Z"
        message_dict = {
            "session_id": session_id,
            "message_id": message_id,
            "content": content,
            "message_type": message_type,
            "timestamp": timestamp if timestamp else now,
            "created_at": now,
            "updated_at": now,
            "expires_at": calculate_expiry_date(),
            "is_edited": False,
            "is_deleted": False
        }

        # Add metadata if provided
        if metadata:
            message_dict["metadata"] = metadata

        print(f"Saving message to MongoDB: {message_dict}")

        # Save to MongoDB using repository
        created_message = await message_repo.create(message_dict)

        # Update session message count
        await update_session_message_count(session_repo, session_id)

        print(f"[OK] Message saved successfully")

        return {
            "success": True,
            "message": format_message_response(created_message)
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: Failed to create message: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create message: {str(e)}")


@router.get("/")
async def get_messages_by_session(
    sessionId: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """
    Get messages by session ID - Frontend-friendly endpoint
    Accepts both ?sessionId= (camelCase) and ?session_id= (snake_case)
    """
    try:
        # Support both camelCase and snake_case
        sid = session_id or sessionId

        if not sid:
            raise HTTPException(status_code=400, detail="sessionId or session_id is required")

        print(f"=== GET MESSAGES REQUEST ===")
        print(f"Session ID: {sid}")

        # Verify session exists
        session = await session_repo.get_by_id(sid)
        if not session:
            print(f"ERROR: Session {sid} not found")
            raise HTTPException(status_code=404, detail=f"Session {sid} not found")

        # Query messages for this session using repository
        messages = await message_repo.get_session_messages(sid, limit=1000)

        # Filter out deleted messages
        messages = [msg for msg in messages if not msg.get('is_deleted', False)]

        print(f"Found {len(messages)} messages")

        # Format messages
        formatted_messages = [format_message_response(msg) for msg in messages]

        return {
            "success": True,
            "messages": formatted_messages,
            "total_count": len(formatted_messages),
            "has_more": False,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: Failed to get messages: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "messages": [],
            "total_count": 0,
            "has_more": False,
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "error": str(e)
        }


# =============================================================================
# Enhanced Functions for Chat Orchestration
# =============================================================================

async def store_chat_pair(
    session_id: str,
    user_id: str,
    user_message: str,
    assistant_message: str,
    metadata: Dict[str, Any] = None
) -> Tuple[str, str]:
    """Store both user and assistant messages as a pair"""
    try:
        db = await get_database()
        message_repo = MessageRepository(db)
        session_repo = SessionRepository(db)

        user_message_id = str(uuid.uuid4())
        assistant_message_id = str(uuid.uuid4())

        # Store user message
        user_msg_dict = create_message_dict(
            session_id=session_id,
            message_data=MessageCreate(
                content=user_message,
                message_type="user",
                metadata=metadata.get("user_metadata", {}) if metadata else {}
            ),
            message_id=user_message_id
        )

        # Store assistant message with reference to user message
        assistant_msg_dict = create_message_dict(
            session_id=session_id,
            message_data=MessageCreate(
                content=assistant_message,
                message_type="assistant",
                parent_message_id=user_message_id,
                metadata=metadata.get("assistant_metadata", {}) if metadata else {}
            ),
            message_id=assistant_message_id
        )

        # Store both messages using repository
        await message_repo.create(user_msg_dict)
        await message_repo.create(assistant_msg_dict)

        # Update session message count
        await update_session_message_count(session_repo, session_id, increment=2)

        return user_message_id, assistant_message_id

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store chat pair: {str(e)}")


async def get_session_context(
    session_id: str,
    limit: int = 10,
    include_system: bool = True
) -> List[Dict[str, Any]]:
    """Get recent messages from session for AI context"""
    try:
        db = await get_database()
        message_repo = MessageRepository(db)

        # Use the repository's context messages method
        messages = await message_repo.get_context_messages(
            session_id=session_id,
            limit=limit,
            include_system=include_system
        )

        # Filter deleted messages and format for AI context
        context_messages = []
        for msg in messages:
            if msg.get('is_deleted', False):
                continue

            message_type = msg.get('message_type', '')

            context_messages.append({
                'message_id': msg.get('id', '') or msg.get('message_id', ''),
                'message_type': message_type,
                'content': msg.get('content', ''),
                'timestamp': msg.get('timestamp', ''),
                'parent_message_id': msg.get('parent_message_id', None)
            })

        return context_messages

    except Exception as e:
        print(f"WARNING: Failed to get session context for {session_id}: {e}")
        return []


# =============================================================================
# Standard REST Endpoints
# =============================================================================

@router.post("/{session_id}/messages", response_model=MessageResponse)
async def create_message(
    session_id: str,
    message: MessageCreate,
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Create a new message in a session"""
    try:
        # Verify session exists (supports both UUID and ObjectId)
        session = await find_session(session_repo, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        message_id = str(uuid.uuid4())
        message_dict = create_message_dict(session_id, message, message_id)

        created_message = await message_repo.create(message_dict)

        # Update session message count
        await update_session_message_count(session_repo, session_id)

        return format_message_response(created_message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/messages", response_model=MessagesListResponse)
async def list_session_messages(
    session_id: str,
    limit: Optional[int] = Query(50, ge=1, le=200),
    last_evaluated_key: Optional[str] = None,
    sort_order: Optional[str] = Query("desc", regex="^(asc|desc)$"),
    message_type: Optional[str] = Query(None, regex="^(user|assistant|system)$"),
    search: Optional[str] = None,
    include_deleted: Optional[bool] = False,
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """List messages in a session with filtering and pagination"""
    try:
        # Verify session exists (supports both UUID and ObjectId)
        session = await find_session(session_repo, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Calculate offset from last_evaluated_key if provided
        offset = 0
        if last_evaluated_key:
            # In MongoDB, we use offset-based pagination
            # The last_evaluated_key is treated as an offset hint
            try:
                offset = int(last_evaluated_key)
            except ValueError:
                offset = 0

        # Get messages based on message_type filter
        if message_type:
            messages = await message_repo.get_messages_by_type(
                session_id=session_id,
                message_type=message_type,
                limit=limit
            )
        else:
            messages = await message_repo.get_session_messages(
                session_id=session_id,
                limit=limit,
                offset=offset
            )

        # Apply additional filters
        filtered_messages = []
        for msg in messages:
            # Filter deleted messages unless explicitly included
            if not include_deleted and msg.get('is_deleted', False):
                continue

            # Filter by search term if provided
            if search and search.lower() not in msg.get('content', '').lower():
                continue

            filtered_messages.append(msg)

        # Sort messages
        if sort_order == "desc":
            filtered_messages = list(reversed(filtered_messages))

        # Format messages
        formatted_messages = [format_message_response(msg) for msg in filtered_messages]

        # Determine if there are more results
        has_more = len(messages) >= limit
        next_key = str(offset + limit) if has_more else None

        return MessagesListResponse(
            success=True,
            messages=formatted_messages,
            total_count=len(formatted_messages),
            has_more=has_more,
            last_evaluated_key=next_key,
            last_updated=datetime.utcnow().isoformat() + "Z"
        )
    except HTTPException:
        raise
    except Exception as e:
        return MessagesListResponse(
            success=False,
            messages=[],
            total_count=0,
            has_more=False,
            last_updated=datetime.utcnow().isoformat() + "Z",
            error=str(e)
        )


# NOTE: Search and export routes MUST come before /{message_id} to avoid
# "search" and "export" being matched as message_id parameters

@router.get("/{session_id}/messages/search")
async def search_messages(
    session_id: str,
    query: str = Query(..., min_length=1),
    limit: Optional[int] = Query(20, ge=1, le=100),
    message_type: Optional[str] = Query(None, regex="^(user|assistant|system)$"),
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Search messages in a session"""
    try:
        # Verify session exists (supports both UUID and ObjectId)
        session = await find_session(session_repo, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get messages from session
        if message_type:
            messages = await message_repo.get_messages_by_type(
                session_id=session_id,
                message_type=message_type,
                limit=1000  # Get more to filter by search
            )
        else:
            messages = await message_repo.get_session_messages(
                session_id=session_id,
                limit=1000
            )

        # Filter by search query and deleted status
        matching_messages = []
        for msg in messages:
            if msg.get('is_deleted', False):
                continue
            if query.lower() in msg.get('content', '').lower():
                matching_messages.append(msg)
                if len(matching_messages) >= limit:
                    break

        # Format messages
        formatted_messages = [format_message_response(msg) for msg in matching_messages]

        return {
            "query": query,
            "session_id": session_id,
            "results": formatted_messages,
            "count": len(formatted_messages)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/messages/export")
async def export_messages(
    session_id: str,
    format: str = Query("json", regex="^(json|txt|csv)$"),
    include_metadata: bool = Query(True),
    include_deleted: bool = Query(False),
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Export session messages in various formats"""
    try:
        # Verify session exists (supports both UUID and ObjectId)
        session = await find_session(session_repo, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get all messages using repository's export method
        messages = await message_repo.export_session_messages(
            session_id=session_id,
            include_metadata=include_metadata
        )

        # Filter deleted messages if not included
        if not include_deleted:
            messages = [msg for msg in messages if not msg.get('is_deleted', False)]

        # Format messages for response
        formatted_messages = [format_message_response(msg) for msg in messages]

        if format == "json":
            return {
                "session_id": session_id,
                "export_format": "json",
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "message_count": len(formatted_messages),
                "messages": [msg.dict() for msg in formatted_messages]
            }

        elif format == "txt":
            # Simple text format
            text_content = f"Chat Session Export - {session_id}\n"
            text_content += f"Exported at: {datetime.utcnow().isoformat() + 'Z'}\n"
            text_content += f"Total messages: {len(formatted_messages)}\n\n"

            for msg in formatted_messages:
                text_content += f"[{msg.timestamp}] {msg.message_type.upper()}: {msg.content}\n"
                if msg.attachments and include_metadata:
                    text_content += f"  Attachments: {len(msg.attachments)} files\n"
                text_content += "\n"

            return {"content": text_content, "format": "txt"}

        elif format == "csv":
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Header
            headers = ["timestamp", "message_type", "content"]
            if include_metadata:
                headers.extend(["attachments_count", "reactions_count", "is_edited"])
            writer.writerow(headers)

            # Data rows
            for msg in formatted_messages:
                row = [msg.timestamp, msg.message_type, msg.content]
                if include_metadata:
                    row.extend([
                        len(msg.attachments) if msg.attachments else 0,
                        len(msg.reactions) if msg.reactions else 0,
                        msg.is_edited
                    ])
                writer.writerow(row)

            return {"content": output.getvalue(), "format": "csv"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/messages/{message_id}", response_model=MessageResponse)
async def get_message(
    session_id: str,
    message_id: str,
    message_repo: MessageRepository = Depends(get_message_repository)
):
    """Get a specific message"""
    try:
        # Find message (supports both UUID and ObjectId)
        message = await find_message(message_repo, message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Verify message belongs to the session
        if message.get('session_id') != session_id:
            raise HTTPException(status_code=404, detail="Message not found in this session")

        return format_message_response(message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{session_id}/messages/{message_id}", response_model=MessageResponse)
async def update_message(
    session_id: str,
    message_id: str,
    message_update: MessageUpdate,
    message_repo: MessageRepository = Depends(get_message_repository)
):
    """Update an existing message"""
    try:
        # Get current message (supports both UUID and ObjectId)
        current_message = await find_message(message_repo, message_id)
        if not current_message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Verify message belongs to the session
        if current_message.get('session_id') != session_id:
            raise HTTPException(status_code=404, detail="Message not found in this session")

        # Build update data
        update_data = message_update.dict(exclude_unset=True)
        update_data['updated_at'] = datetime.utcnow().isoformat() + "Z"
        update_data['is_edited'] = True

        # Update message using repository (use MongoDB id for update)
        mongo_id = current_message.get('id') or message_id
        updated_message = await message_repo.update(mongo_id, update_data)

        if not updated_message:
            raise HTTPException(status_code=500, detail="Failed to update message")

        return format_message_response(updated_message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}/messages/{message_id}")
async def delete_message(
    session_id: str,
    message_id: str,
    hard_delete: bool = Query(False),
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Delete a message (soft delete by default)"""
    try:
        # Check if message exists (supports both UUID and ObjectId)
        message = await find_message(message_repo, message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Verify message belongs to the session
        if message.get('session_id') != session_id:
            raise HTTPException(status_code=404, detail="Message not found in this session")

        # Use MongoDB id for update/delete operations
        mongo_id = message.get('id') or message_id

        if hard_delete:
            # Hard delete - remove from database
            deleted = await message_repo.delete(mongo_id)
            if not deleted:
                raise HTTPException(status_code=500, detail="Failed to delete message")

            # Update session message count
            await update_session_message_count(session_repo, session_id, -1)

            return {"message": "Message permanently deleted"}
        else:
            # Soft delete - mark as deleted
            updated = await message_repo.update(mongo_id, {
                "is_deleted": True,
                "updated_at": datetime.utcnow().isoformat() + "Z"
            })
            if not updated:
                raise HTTPException(status_code=500, detail="Failed to delete message")

            return {"message": "Message deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/messages/{message_id}/reactions")
async def add_reaction(
    session_id: str,
    message_id: str,
    emoji: str,
    user_id: str,
    message_repo: MessageRepository = Depends(get_message_repository)
):
    """Add a reaction to a message"""
    try:
        # Get current message (supports both UUID and ObjectId)
        message = await find_message(message_repo, message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Verify message belongs to the session
        if message.get('session_id') != session_id:
            raise HTTPException(status_code=404, detail="Message not found in this session")

        reactions = message.get('reactions', [])

        # Find existing reaction with same emoji
        reaction_found = False
        for reaction in reactions:
            if reaction['emoji'] == emoji:
                if user_id not in reaction['users']:
                    reaction['users'].append(user_id)
                    reaction['count'] = len(reaction['users'])
                    reaction_found = True
                break

        if not reaction_found:
            # Add new reaction
            reactions.append({
                'emoji': emoji,
                'count': 1,
                'users': [user_id]
            })

        # Update message with reactions (use MongoDB id)
        mongo_id = message.get('id') or message_id
        await message_repo.update(mongo_id, {
            "reactions": reactions,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        })

        return {"message": "Reaction added successfully", "reactions": reactions}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}/messages/{message_id}/reactions")
async def remove_reaction(
    session_id: str,
    message_id: str,
    emoji: str,
    user_id: str,
    message_repo: MessageRepository = Depends(get_message_repository)
):
    """Remove a reaction from a message"""
    try:
        # Get current message (supports both UUID and ObjectId)
        message = await find_message(message_repo, message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Verify message belongs to the session
        if message.get('session_id') != session_id:
            raise HTTPException(status_code=404, detail="Message not found in this session")

        reactions = message.get('reactions', [])

        # Find and remove user from reaction
        for i, reaction in enumerate(reactions):
            if reaction['emoji'] == emoji and user_id in reaction['users']:
                reaction['users'].remove(user_id)
                reaction['count'] = len(reaction['users'])

                # Remove reaction if no users left
                if reaction['count'] == 0:
                    reactions.pop(i)
                break

        # Update message with reactions (use MongoDB id)
        mongo_id = message.get('id') or message_id
        await message_repo.update(mongo_id, {
            "reactions": reactions,
            "updated_at": datetime.utcnow().isoformat() + "Z"
        })

        return {"message": "Reaction removed successfully", "reactions": reactions}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Bulk Operations
# =============================================================================

@router.post("/{session_id}/messages/bulk-delete")
async def bulk_delete_messages(
    session_id: str,
    message_ids: List[str],
    hard_delete: bool = False,
    message_repo: MessageRepository = Depends(get_message_repository),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Delete multiple messages"""
    try:
        results = []
        for message_id in message_ids:
            try:
                # Get message to verify it belongs to session (supports both UUID and ObjectId)
                message = await find_message(message_repo, message_id)
                if not message:
                    results.append({"message_id": message_id, "status": "error", "error": "Message not found"})
                    continue

                if message.get('session_id') != session_id:
                    results.append({"message_id": message_id, "status": "error", "error": "Message not in session"})
                    continue

                # Use MongoDB id for update/delete operations
                mongo_id = message.get('id') or message_id

                if hard_delete:
                    await message_repo.delete(mongo_id)
                    await update_session_message_count(session_repo, session_id, -1)
                else:
                    await message_repo.update(mongo_id, {
                        "is_deleted": True,
                        "updated_at": datetime.utcnow().isoformat() + "Z"
                    })

                results.append({"message_id": message_id, "status": "deleted"})
            except Exception as e:
                results.append({"message_id": message_id, "status": "error", "error": str(e)})

        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
