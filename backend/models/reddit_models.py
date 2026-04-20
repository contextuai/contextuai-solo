"""Pydantic v2 models for the Reddit connection."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RedditAccount(BaseModel):
    """Stored Reddit account credentials + poll configuration."""

    model_config = {"protected_namespaces": ()}

    id: Optional[str] = Field(default=None, alias="_id")
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    user_agent: str = Field(default="ContextuAI-Solo/1.0")

    subreddits: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    poll_inbox: bool = Field(default=True)

    enabled: bool = Field(default=True)
    last_seen_ids: dict = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RedditAccountCreate(BaseModel):
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    user_agent: Optional[str] = None
    subreddits: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    poll_inbox: bool = True


class RedditAccountUpdate(BaseModel):
    subreddits: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    poll_inbox: Optional[bool] = None
    enabled: Optional[bool] = None


class RedditPostReply(BaseModel):
    """Outbound comment or DM."""

    target_type: str = Field(..., pattern="^(comment|submission|dm)$")
    target_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1, max_length=10000)
    recipient: Optional[str] = None
