from fastapi import APIRouter, HTTPException, Query, Request, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
import os
import uuid
import re
from datetime import datetime, timedelta

# Import MongoDB database and repositories
from database import get_database
from repositories import SessionRepository, MessageRepository

# Import analytics service for event capture
from services.analytics_service import capture_session_analytics

router = APIRouter(prefix="/api/v1/chat-sessions", tags=["chat-sessions"])

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")


# Dependency functions for repositories
async def get_session_repository() -> SessionRepository:
    """Dependency to get SessionRepository instance"""
    db = await get_database()
    return SessionRepository(db)


async def get_message_repository() -> MessageRepository:
    """Dependency to get MessageRepository instance"""
    db = await get_database()
    return MessageRepository(db)


# Pydantic models for validation
class SessionCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    persona_id: Optional[str] = None
    model_id: Optional[str] = None
    tags: Optional[List[str]] = Field(None, max_items=10)
    is_favorite: bool = False

class SessionUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    persona_id: Optional[str] = None
    model_id: Optional[str] = None
    tags: Optional[List[str]] = Field(None, max_items=10)
    is_favorite: Optional[bool] = None

class SessionResponse(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        populate_by_name=True,  # Accept both snake_case and camelCase
        from_attributes=True     # Replaces by_alias for Pydantic v2
    )

    session_id: str = Field(..., alias="sessionId")
    user_id: str = Field(..., alias="userId")
    title: Optional[str] = None
    description: Optional[str] = None
    persona_id: Optional[str] = Field(None, alias="personaId")
    model_id: Optional[str] = Field(None, alias="modelId")
    tags: Optional[List[str]] = None
    is_favorite: bool = Field(False, alias="isFavorite")
    message_count: int = Field(0, alias="messageCount")
    last_message_at: Optional[str] = Field(None, alias="lastMessageAt")
    created_at: str = Field(..., alias="createdAt")
    updated_at: str = Field(..., alias="updatedAt")
    expires_at: str = Field(..., alias="expiresAt")
    status: str = "active"

class SessionListResponse(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,  # Accept both snake_case and camelCase
        from_attributes=True     # Replaces by_alias for Pydantic v2
    )

    success: bool
    sessions: List[SessionResponse]
    total_count: int = Field(..., alias="totalCount")
    has_more: bool = Field(..., alias="hasMore")
    last_evaluated_key: Optional[str] = Field(None, alias="lastEvaluatedKey")
    last_updated: str = Field(..., alias="lastUpdated")
    error: Optional[str] = None

class SessionCreateResponse(BaseModel):
    success: bool
    session: SessionResponse

def calculate_expiry_date(days: int = 30) -> str:
    """Calculate expiry date for session TTL"""
    expiry_date = datetime.utcnow() + timedelta(days=days)
    return str(int(expiry_date.timestamp()))

def create_session_dict(user_id: str, session_data: SessionCreate, session_id: str = None) -> Dict[str, Any]:
    """Create session dictionary for MongoDB"""
    if not session_id:
        session_id = str(uuid.uuid4())

    now = datetime.utcnow().isoformat() + "Z"

    session_dict = {
        "session_id": session_id,
        "user_id": user_id,
        "status": "active",
        "message_count": 0,
        "is_favorite": session_data.is_favorite,
        "created_at": now,
        "updated_at": now,
        "expires_at": calculate_expiry_date()
    }

    # Add optional fields
    if session_data.title:
        session_dict["title"] = session_data.title
    if session_data.description:
        session_dict["description"] = session_data.description
    if session_data.persona_id:
        session_dict["persona_id"] = session_data.persona_id
    if session_data.model_id:
        session_dict["model_id"] = session_data.model_id
    if session_data.tags:
        session_dict["tags"] = session_data.tags

    return session_dict

def format_session_response(session_item: Dict[str, Any]) -> SessionResponse:
    """Format MongoDB document to SessionResponse"""
    # Handle both 'id' (from MongoDB) and 'session_id' (legacy format)
    session_id = session_item.get("session_id") or session_item.get("id", "")

    return SessionResponse(
        session_id=session_id,
        user_id=session_item["user_id"],
        title=session_item.get("title"),
        description=session_item.get("description"),
        persona_id=session_item.get("persona_id"),
        model_id=session_item.get("model_id"),
        tags=session_item.get("tags"),
        is_favorite=session_item.get("is_favorite", False),
        message_count=int(session_item.get("message_count", 0)),
        last_message_at=session_item.get("last_message_at"),
        created_at=session_item.get("created_at", ""),
        updated_at=session_item.get("updated_at", ""),
        expires_at=session_item.get("expires_at", ""),
        status=session_item.get("status", "active")
    )

@router.post("/", response_model=SessionCreateResponse)
async def create_session(
    request: Request,
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Create a new chat session"""
    try:
        # Log incoming request details
        print(f"=== CREATE SESSION REQUEST ===")
        print(f"URL: {request.url}")
        print(f"Method: {request.method}")
        print(f"Headers: {dict(request.headers)}")

        request_data = await request.json()
        print(f"Request Body: {request_data}")

        user_id = request_data.get("userId")  # Map userId -> user_id
        print(f"Extracted userId: {user_id}")

        if not user_id:
            # Also check query param
            user_id = request.query_params.get("user_id")
        if not user_id:
            user_id = "desktop-user"

        # Parse session fields from the request body
        session = SessionCreate(
            title=request_data.get("title"),
            persona_id=request_data.get("personaId") or request_data.get("persona_id"),
            model_id=request_data.get("modelId") or request_data.get("model_id"),
        )
        session_id = str(uuid.uuid4())
        print(f"Generated session_id: {session_id}")

        session_dict = create_session_dict(user_id, session, session_id)
        print(f"Session dict created: {session_dict}")

        # Save to MongoDB via repository
        created_session = await session_repo.create(session_dict)
        print(f"Session saved to MongoDB")

        # Capture session start analytics (non-blocking)
        await capture_session_analytics(
            user_id=user_id,
            session_id=session_id,
            is_start=True
        )
        print(f"Session analytics captured")

        response_data = SessionCreateResponse(
            success=True,
            session=format_session_response(created_session)
        )
        print(f"Response: {response_data}")
        print(f"=== SESSION CREATED SUCCESSFULLY ===")

        return response_data
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR: Session creation failed: {e}")
        print(f"Exception type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

# Enhanced functions for chat orchestration
async def get_or_create_session(
    user_id: str,
    session_id: Optional[str] = None,
    persona_id: Optional[str] = None,
    model_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get existing session or create new one for chat endpoint"""
    try:
        db = await get_database()
        session_repo = SessionRepository(db)

        if session_id:
            # Try to get existing session by session_id field
            session_data = await session_repo.get_one({"session_id": session_id})

            if session_data:
                # Update model_id if provided and different
                if model_id and session_data.get('model_id') != model_id:
                    now = datetime.utcnow().isoformat() + "Z"
                    # Use the MongoDB id for update
                    mongo_id = session_data.get('id') or session_id
                    await session_repo.update(mongo_id, {
                        'model_id': model_id,
                        'updated_at': now
                    })
                    session_data['model_id'] = model_id

                return format_session_response(session_data)
            else:
                # Session not found - create it with the provided session_id
                print(f"Session {session_id} not found, creating new one...")
                session_create = SessionCreate(
                    title="New Chat",
                    persona_id=persona_id,
                    model_id=model_id
                )
                session_dict = create_session_dict(user_id, session_create, session_id)
                created_session = await session_repo.create(session_dict)

                # Capture session start analytics (non-blocking)
                await capture_session_analytics(
                    user_id=user_id,
                    session_id=session_id,
                    is_start=True,
                    persona_id=persona_id,
                    model_id=model_id
                )

                return format_session_response(created_session)

        # Create new session
        new_session_id = str(uuid.uuid4())
        session_create = SessionCreate(
            title="New Chat",  # Will be updated with first message
            persona_id=persona_id,
            model_id=model_id
        )

        session_dict = create_session_dict(user_id, session_create, new_session_id)
        created_session = await session_repo.create(session_dict)

        # Capture session start analytics (non-blocking)
        await capture_session_analytics(
            user_id=user_id,
            session_id=new_session_id,
            is_start=True,
            persona_id=persona_id,
            model_id=model_id
        )

        return format_session_response(created_session)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session creation failed: {str(e)}")

async def update_session_stats(
    session_id: str,
    tokens_used: int = 0,
    response_time_ms: int = 0,
    increment_messages: int = 2  # User + Assistant message
) -> None:
    """Update session statistics after chat interaction"""
    try:
        db = await get_database()
        session_repo = SessionRepository(db)

        now = datetime.utcnow().isoformat() + "Z"

        # Get current session by session_id field
        current_session = await session_repo.get_one({"session_id": session_id})
        if not current_session:
            return  # Session doesn't exist, skip update

        current_message_count = int(current_session.get('message_count', 0))
        current_total_tokens = int(current_session.get('total_tokens_used', 0))
        current_avg_response_time = float(current_session.get('average_response_time_ms', 0))

        # Calculate new values
        new_message_count = current_message_count + increment_messages
        new_total_tokens = current_total_tokens + tokens_used

        # Calculate new average response time (only count assistant responses)
        assistant_response_count = (current_message_count // 2) + 1  # Assuming user/assistant pairs
        if assistant_response_count > 1:
            new_avg_response_time = (
                (current_avg_response_time * (assistant_response_count - 1) + response_time_ms)
                / assistant_response_count
            )
        else:
            new_avg_response_time = response_time_ms

        # Update session with new statistics using MongoDB id
        mongo_id = current_session.get('id') or session_id
        await session_repo.update(mongo_id, {
            'message_count': new_message_count,
            'total_tokens_used': new_total_tokens,
            'average_response_time_ms': int(new_avg_response_time),
            'last_message_at': now,
            'updated_at': now
        })

    except Exception as e:
        print(f"WARNING: Failed to update session stats for {session_id}: {e}")
        # Don't raise exception to avoid breaking chat flow

async def update_session_title_from_first_message(
    session_id: str,
    first_message: str,
    max_length: int = 20  # Changed default from 50 to 20 for shorter titles
) -> None:
    """Auto-generate session title from first user message with smart truncation"""
    try:
        db = await get_database()
        session_repo = SessionRepository(db)

        # Step 1: Remove @persona mentions (e.g., "@sales_db get data" -> "get data")
        title = re.sub(r'@\w+\s*', '', first_message)

        # Step 2: Remove code blocks and backticks
        title = re.sub(r'```[\s\S]*?```', '', title)  # Remove code blocks
        title = re.sub(r'`[^`]+`', '', title)  # Remove inline code

        # Step 3: Remove emojis and special unicode characters (keep basic punctuation)
        # Use a more targeted approach to remove only emojis while preserving regular text
        # Remove characters in emoji ranges
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE
        )
        title = emoji_pattern.sub('', title)
        # Also remove other special characters but keep basic punctuation and letters
        title = re.sub(r'[^\w\s\?\!\.\,\-\:\;\'\"]', '', title)

        # Step 4: Clean up whitespace
        title = " ".join(title.split()).strip()

        # Step 5: Handle empty or very short titles
        if not title or len(title.strip()) == 0:
            title = "New Chat"
        elif len(title) < 3:
            # For very short messages (1-2 chars), add "Chat:" prefix and capitalize
            title = f"Chat: {title.capitalize()}"
        else:
            # Step 6: Capitalize first letter for all other messages
            if title and len(title) > 0:
                title = title[0].upper() + title[1:]

        # Step 7: Smart truncation at word boundaries
        if len(title) > max_length:
            # Check if original ended with punctuation
            ends_with_punctuation = title[-1] in '?!.'
            original_ending = title[-1] if ends_with_punctuation else ''

            # Truncate at word boundary
            truncated = title[:max_length].rsplit(' ', 1)[0]

            # Try to preserve ending punctuation if it fits
            if ends_with_punctuation and len(truncated) + 4 <= max_length:  # "..." + ending
                title = truncated + "..." + original_ending
            else:
                title = truncated + "..."

        # Get session and update title using MongoDB id
        now = datetime.utcnow().isoformat() + "Z"
        session_data = await session_repo.get_one({"session_id": session_id})
        if session_data:
            mongo_id = session_data.get('id') or session_id
            await session_repo.update(mongo_id, {
                'title': title,
                'updated_at': now
            })

        print(f"Session title updated: '{title}' (from: '{first_message[:30]}...')")

    except Exception as e:
        print(f"WARNING: Failed to update session title for {session_id}: {e}")
        # Don't raise exception to avoid breaking chat flow

@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Get a specific chat session"""
    try:
        # Try to find by session_id field first
        session = await session_repo.get_one({"session_id": session_id})
        if not session:
            # Try to find by MongoDB id
            try:
                session = await session_repo.get_by_id(session_id)
            except ValueError:
                pass  # Invalid ObjectId, session not found

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return format_session_response(session)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/user/{user_id}", response_model=SessionListResponse)
async def list_user_sessions(
    user_id: str,
    limit: Optional[int] = Query(20, ge=1, le=100),
    last_evaluated_key: Optional[str] = None,
    favorites_only: Optional[bool] = False,
    status: Optional[str] = Query(None, regex="^(active|archived|deleted)$"),
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("created_at", regex="^(created_at|updated_at|last_message_at)$"),
    sort_order: Optional[str] = Query("desc", regex="^(asc|desc)$"),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """List user's chat sessions with filtering and pagination"""
    try:
        # Build filter query
        filter_query: Dict[str, Any] = {"user_id": user_id}

        # Add status filter (default to active)
        if status:
            filter_query["status"] = status
        else:
            filter_query["status"] = "active"

        # Add favorites filter
        if favorites_only:
            filter_query["is_favorite"] = True

        # Add search filter
        if search:
            filter_query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}}
            ]

        # Calculate offset from last_evaluated_key (for pagination compatibility)
        offset = 0
        if last_evaluated_key:
            # In MongoDB, we can use skip/limit instead of DynamoDB's LastEvaluatedKey
            # For simplicity, treat last_evaluated_key as an offset indicator
            try:
                offset = int(last_evaluated_key)
            except ValueError:
                offset = 0

        # Determine sort order
        sort_direction = -1 if sort_order == 'desc' else 1
        sort_field = sort_by if sort_by else 'created_at'

        # Query sessions using repository
        sessions = await session_repo.get_all(
            filter=filter_query,
            skip=offset,
            limit=limit + 1,  # Fetch one extra to check if there's more
            sort=[(sort_field, sort_direction)]
        )

        # Check if there are more results
        has_more = len(sessions) > limit
        if has_more:
            sessions = sessions[:limit]  # Remove the extra item

        # Format sessions
        formatted_sessions = [format_session_response(session) for session in sessions]

        # Calculate next offset for pagination
        next_key = str(offset + limit) if has_more else None

        return SessionListResponse(
            success=True,
            sessions=formatted_sessions,
            total_count=len(formatted_sessions),
            has_more=has_more,
            last_evaluated_key=next_key,
            last_updated=datetime.utcnow().isoformat() + "Z"
        )
    except Exception as e:
        return SessionListResponse(
            success=False,
            sessions=[],
            total_count=0,
            has_more=False,
            last_updated=datetime.utcnow().isoformat() + "Z",
            error=str(e)
        )

@router.put("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    session_update: SessionUpdate,
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Update an existing chat session"""
    try:
        # Get current session by session_id field
        current_session = await session_repo.get_one({"session_id": session_id})
        if not current_session:
            # Try by MongoDB id
            try:
                current_session = await session_repo.get_by_id(session_id)
            except ValueError:
                pass

        if not current_session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Update only provided fields
        update_data = session_update.dict(exclude_unset=True)
        update_data['updated_at'] = datetime.utcnow().isoformat() + "Z"

        # Extend expiry date
        update_data['expires_at'] = calculate_expiry_date()

        # Update session using MongoDB id
        mongo_id = current_session.get('id') or session_id
        updated_session = await session_repo.update(mongo_id, update_data)

        if not updated_session:
            raise HTTPException(status_code=404, detail="Session not found")

        return format_session_response(updated_session)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    hard_delete: bool = Query(False),
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Delete a chat session (soft delete by default)"""
    try:
        # Get session by session_id field
        session = await session_repo.get_one({"session_id": session_id})
        if not session:
            # Try by MongoDB id
            try:
                session = await session_repo.get_by_id(session_id)
            except ValueError:
                pass

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        mongo_id = session.get('id') or session_id

        if hard_delete:
            # Hard delete - remove from database
            deleted = await session_repo.delete(mongo_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="Session not found")
            return {"message": "Session permanently deleted"}
        else:
            # Soft delete - update status
            await session_repo.update(mongo_id, {
                'status': 'deleted',
                'updated_at': datetime.utcnow().isoformat() + "Z"
            })
            return {"message": "Session deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{session_id}/favorite")
async def toggle_session_favorite(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Toggle session favorite status"""
    try:
        # Get current session by session_id field
        session = await session_repo.get_one({"session_id": session_id})
        if not session:
            # Try by MongoDB id
            try:
                session = await session_repo.get_by_id(session_id)
            except ValueError:
                pass

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        current_favorite = session.get('is_favorite', False)
        new_favorite = not current_favorite

        # Update favorite status using MongoDB id
        mongo_id = session.get('id') or session_id
        await session_repo.update(mongo_id, {
            'is_favorite': new_favorite,
            'updated_at': datetime.utcnow().isoformat() + "Z"
        })

        return {
            "session_id": session_id,
            "is_favorite": new_favorite,
            "message": f"Session {'added to' if new_favorite else 'removed from'} favorites"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{session_id}/archive")
async def archive_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Archive a chat session"""
    try:
        # Get session by session_id field
        session = await session_repo.get_one({"session_id": session_id})
        if not session:
            # Try by MongoDB id
            try:
                session = await session_repo.get_by_id(session_id)
            except ValueError:
                pass

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Update status to archived using MongoDB id
        mongo_id = session.get('id') or session_id
        await session_repo.update(mongo_id, {
            'status': 'archived',
            'updated_at': datetime.utcnow().isoformat() + "Z"
        })

        return {"message": "Session archived successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{session_id}/restore")
async def restore_session(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Restore an archived or deleted session"""
    try:
        # Get session by session_id field
        session = await session_repo.get_one({"session_id": session_id})
        if not session:
            # Try by MongoDB id
            try:
                session = await session_repo.get_by_id(session_id)
            except ValueError:
                pass

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Update status to active using MongoDB id
        mongo_id = session.get('id') or session_id
        await session_repo.update(mongo_id, {
            'status': 'active',
            'updated_at': datetime.utcnow().isoformat() + "Z",
            'expires_at': calculate_expiry_date()
        })

        return {"message": "Session restored successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/stats")
async def get_session_stats(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Get session statistics"""
    try:
        # Get session by session_id field
        session = await session_repo.get_one({"session_id": session_id})
        if not session:
            # Try by MongoDB id
            try:
                session = await session_repo.get_by_id(session_id)
            except ValueError:
                pass

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Calculate session age
        created_at = datetime.fromisoformat(session['created_at'].replace('Z', '+00:00'))
        age_days = (datetime.utcnow().replace(tzinfo=created_at.tzinfo) - created_at).days

        return {
            "session_id": session_id,
            "message_count": int(session.get('message_count', 0)),
            "age_days": age_days,
            "is_favorite": session.get('is_favorite', False),
            "status": session.get('status', 'active'),
            "last_activity": session.get('last_message_at', session['updated_at']),
            "persona_id": session.get('persona_id'),
            "model_id": session.get('model_id')
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{session_id}/enhanced-stats")
async def get_enhanced_session_stats(
    session_id: str,
    session_repo: SessionRepository = Depends(get_session_repository),
    message_repo: MessageRepository = Depends(get_message_repository)
):
    """Get enhanced session analytics with message-level metrics"""
    try:
        from collections import Counter

        # Get basic session info by session_id field
        session = await session_repo.get_one({"session_id": session_id})
        if not session:
            # Try by MongoDB id
            try:
                session = await session_repo.get_by_id(session_id)
            except ValueError:
                pass

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Calculate basic stats
        created_at = datetime.fromisoformat(session['created_at'].replace('Z', '+00:00'))
        age_days = (datetime.utcnow().replace(tzinfo=created_at.tzinfo) - created_at).days

        # Query all messages for this session using MessageRepository
        messages = await message_repo.get_session_messages(session_id, limit=10000)

        # Initialize metrics
        user_messages = [m for m in messages if m.get('message_type') == 'user']
        assistant_messages = [m for m in messages if m.get('message_type') == 'assistant']

        # Calculate message length averages
        avg_user_length = int(sum(len(m.get('content', '')) for m in user_messages) / len(user_messages)) if user_messages else 0
        avg_ai_length = int(sum(len(m.get('content', '')) for m in assistant_messages) / len(assistant_messages)) if assistant_messages else 0

        # Conversation depth (message pairs)
        conversation_depth = min(len(user_messages), len(assistant_messages))

        # Extract topics using simple keyword analysis
        all_content = ' '.join(m.get('content', '') for m in messages)
        # Simple topic extraction - find common technical terms
        tech_keywords = ['python', 'javascript', 'react', 'database', 'api', 'error', 'function',
                        'deploy', 'aws', 'docker', 'git', 'code', 'bug', 'feature', 'test']
        topics_found = []
        for keyword in tech_keywords:
            if keyword.lower() in all_content.lower():
                topics_found.append(keyword.capitalize())
        topics_extracted = topics_found[:5] if topics_found else []

        # Classify question types
        how_to_count = sum(1 for m in user_messages if any(phrase in m.get('content', '').lower()
                                                            for phrase in ['how to', 'how do i', 'how can i']))
        troubleshooting_count = sum(1 for m in user_messages if any(word in m.get('content', '').lower()
                                                                     for word in ['error', 'bug', 'issue', 'problem', 'fix']))
        explanation_count = sum(1 for m in user_messages if any(word in m.get('content', '').lower()
                                                                 for word in ['what is', 'explain', 'why', 'what does']))
        comparison_count = sum(1 for m in user_messages if any(word in m.get('content', '').lower()
                                                                for word in ['vs', 'versus', 'compare', 'difference']))

        # Calculate peak activity hour
        message_hours = []
        for msg in messages:
            try:
                ts = datetime.fromisoformat(msg.get('timestamp', '').replace('Z', '+00:00'))
                message_hours.append(ts.hour)
            except:
                pass

        if message_hours:
            hour_counts = Counter(message_hours)
            peak_hour = hour_counts.most_common(1)[0][0]
            peak_activity_hour = f"{peak_hour:02d}:00"
        else:
            peak_activity_hour = "00:00"

        # Calculate session duration
        if messages:
            try:
                first_msg = min(messages, key=lambda m: m.get('timestamp', ''))
                last_msg = max(messages, key=lambda m: m.get('timestamp', ''))
                first_time = datetime.fromisoformat(first_msg.get('timestamp', '').replace('Z', '+00:00'))
                last_time = datetime.fromisoformat(last_msg.get('timestamp', '').replace('Z', '+00:00'))
                duration_seconds = (last_time - first_time).total_seconds()
                avg_session_duration = int(duration_seconds / 60)  # Convert to minutes
            except:
                avg_session_duration = 0
        else:
            avg_session_duration = 0

        # Calculate follow-up rate (ratio of user messages after first)
        follow_up_rate = round((len(user_messages) - 1) / len(user_messages), 2) if len(user_messages) > 0 else 0.0

        # AI effectiveness metrics
        clarification_requests = sum(1 for m in assistant_messages if any(phrase in m.get('content', '').lower()
                                                                           for phrase in ['could you clarify', 'can you provide more',
                                                                                        'what do you mean', 'could you explain']))

        # Count code examples (look for code blocks or common code indicators)
        code_examples_provided = sum(1 for m in assistant_messages if '```' in m.get('content', '') or
                                     'def ' in m.get('content', '') or 'function ' in m.get('content', ''))

        # Problem resolution score (simplified: ratio of assistant messages without clarification requests)
        if len(assistant_messages) > 0:
            problem_resolution_score = round((len(assistant_messages) - clarification_requests) / len(assistant_messages), 2)
        else:
            problem_resolution_score = 0.0

        return {
            # Basic session info
            "session_id": session_id,
            "message_count": int(session.get('message_count', 0)),
            "age_days": age_days,
            "is_favorite": session.get('is_favorite', False),
            "status": session.get('status', 'active'),
            "last_activity": session.get('last_message_at', session['updated_at']),
            "persona_id": session.get('persona_id'),
            "model_id": session.get('model_id'),

            # Conversation quality metrics
            "avg_user_message_length": avg_user_length,
            "avg_ai_response_length": avg_ai_length,
            "conversation_depth": conversation_depth,

            # Business intelligence
            "topics_extracted": topics_extracted,
            "question_types": {
                "how_to": how_to_count,
                "troubleshooting": troubleshooting_count,
                "explanation": explanation_count,
                "comparison": comparison_count
            },

            # Usage patterns
            "peak_activity_hour": peak_activity_hour,
            "avg_session_duration": avg_session_duration,
            "follow_up_rate": follow_up_rate,

            # AI effectiveness
            "clarification_requests": clarification_requests,
            "code_examples_provided": code_examples_provided,
            "problem_resolution_score": problem_resolution_score
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR: Enhanced stats failed: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# Bulk operations
@router.post("/bulk-archive")
async def bulk_archive_sessions(
    session_ids: List[str],
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Archive multiple sessions"""
    try:
        results = []
        for session_id in session_ids:
            try:
                # Get session by session_id field
                session = await session_repo.get_one({"session_id": session_id})
                if session:
                    mongo_id = session.get('id') or session_id
                    await session_repo.update(mongo_id, {
                        'status': 'archived',
                        'updated_at': datetime.utcnow().isoformat() + "Z"
                    })
                    results.append({"session_id": session_id, "status": "archived"})
                else:
                    results.append({"session_id": session_id, "status": "error", "error": "Session not found"})
            except Exception as e:
                results.append({"session_id": session_id, "status": "error", "error": str(e)})

        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-delete")
async def bulk_delete_sessions(
    session_ids: List[str],
    hard_delete: bool = False,
    session_repo: SessionRepository = Depends(get_session_repository)
):
    """Delete multiple sessions"""
    try:
        results = []
        for session_id in session_ids:
            try:
                # Get session by session_id field
                session = await session_repo.get_one({"session_id": session_id})
                if session:
                    mongo_id = session.get('id') or session_id
                    if hard_delete:
                        await session_repo.delete(mongo_id)
                    else:
                        await session_repo.update(mongo_id, {
                            'status': 'deleted',
                            'updated_at': datetime.utcnow().isoformat() + "Z"
                        })
                    results.append({"session_id": session_id, "status": "deleted"})
                else:
                    results.append({"session_id": session_id, "status": "error", "error": "Session not found"})
            except Exception as e:
                results.append({"session_id": session_id, "status": "error", "error": str(e)})

        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
