"""Pydantic v2 models for the Twitter/X connection."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TwitterAccount(BaseModel):
    """Stored Twitter/X account credentials + poll configuration.

    Either OAuth 1.0a user-context creds (api_key/api_secret/access_token/
    access_token_secret) or a bearer_token may be supplied. OAuth 1.0a is
    required for posting replies and DMs; bearer_token is sufficient for
    read-only polling.
    """

    model_config = {"protected_namespaces": ()}

    id: Optional[str] = Field(default=None, alias="_id")

    # OAuth 1.0a user-context
    api_key: Optional[str] = Field(default=None)
    api_secret: Optional[str] = Field(default=None)
    access_token: Optional[str] = Field(default=None)
    access_token_secret: Optional[str] = Field(default=None)

    # App-only bearer token (for read endpoints)
    bearer_token: Optional[str] = Field(default=None)

    # Numeric Twitter user id for mention polling
    user_id: str = Field(..., min_length=1)

    keywords: List[str] = Field(default_factory=list)
    poll_mentions: bool = Field(default=True)
    poll_dms: bool = Field(default=True)

    enabled: bool = Field(default=True)
    last_seen_ids: dict = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TwitterAccountCreate(BaseModel):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    access_token: Optional[str] = None
    access_token_secret: Optional[str] = None
    bearer_token: Optional[str] = None
    user_id: str = Field(..., min_length=1)
    keywords: List[str] = Field(default_factory=list)
    poll_mentions: bool = True
    poll_dms: bool = True


class TwitterAccountUpdate(BaseModel):
    keywords: Optional[List[str]] = None
    poll_mentions: Optional[bool] = None
    poll_dms: Optional[bool] = None
    enabled: Optional[bool] = None


class TwitterPostReply(BaseModel):
    """Outbound tweet reply or DM."""

    target_type: str = Field(..., pattern="^(tweet|dm)$")
    target_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1, max_length=10000)
    recipient: Optional[str] = None
