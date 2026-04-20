"""
Connection Models — unified shape across every credential store.

Phase 3 PR 2 introduces a single `/api/v1/connections` aggregator that reads
from oauth_connections (LinkedIn/IG/FB), reddit_accounts, twitter_accounts,
channel_registrations (Telegram/Discord), and distribution_channels
(blog/email/slack_webhook). This module defines the request/response models
for that surface.

Existing per-platform credential endpoints (OAuth callback, Reddit CRUD,
Twitter CRUD, channels/register) are unchanged — the aggregator is a
read-plus-capability-toggle layer on top.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# =============================================================================
# Platform catalog
# =============================================================================

class Platform(str, Enum):
    """All supported connection platforms. Includes PR 2's new outbound-only types."""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    REDDIT = "reddit"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    BLOG = "blog"
    EMAIL = "email"
    SLACK_WEBHOOK = "slack_webhook"


# Platform capabilities — what direction(s) each platform supports.
PLATFORM_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    Platform.TELEGRAM.value:      {"inbound_supported": True,  "outbound_supported": True},
    Platform.DISCORD.value:       {"inbound_supported": True,  "outbound_supported": True},
    Platform.REDDIT.value:        {"inbound_supported": True,  "outbound_supported": True},
    Platform.TWITTER.value:       {"inbound_supported": True,  "outbound_supported": True},
    Platform.LINKEDIN.value:      {"inbound_supported": False, "outbound_supported": True},
    Platform.INSTAGRAM.value:     {"inbound_supported": False, "outbound_supported": True},
    Platform.FACEBOOK.value:      {"inbound_supported": False, "outbound_supported": True},
    Platform.BLOG.value:          {"inbound_supported": False, "outbound_supported": True},
    Platform.EMAIL.value:         {"inbound_supported": False, "outbound_supported": True},
    Platform.SLACK_WEBHOOK.value: {"inbound_supported": False, "outbound_supported": True},
}

OUTBOUND_ONLY_PLATFORMS = {
    Platform.BLOG.value,
    Platform.EMAIL.value,
    Platform.SLACK_WEBHOOK.value,
}


# =============================================================================
# Aggregator response
# =============================================================================

class ConnectionSummary(BaseModel):
    """Unified view of one connection across all stores.

    `id` is the store-native identifier (OAuth provider id, reddit_accounts
    _id, channel_registrations _id, distribution_channels channel_id, etc.).
    The aggregator stamps a `store` hint so writes can route back to the
    originating collection.
    """
    id: str
    platform: str
    store: Literal[
        "oauth_connections",
        "reddit_accounts",
        "twitter_accounts",
        "channel_registrations",
        "distribution_channels",
    ]
    display_name: Optional[str] = None
    connected: bool = True
    inbound_enabled: bool = True
    outbound_enabled: bool = True
    inbound_supported: bool = False
    outbound_supported: bool = False
    config_summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Non-sensitive subset safe to show in UI (e.g. profile_name, subreddits count, from_email).",
    )
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConnectionListResponse(BaseModel):
    success: bool = True
    connections: List[ConnectionSummary]
    total_count: int


# =============================================================================
# Capability PATCH
# =============================================================================

class CapabilityUpdate(BaseModel):
    """Toggle inbound/outbound on an existing connection. Omitted fields untouched."""
    inbound_enabled: Optional[bool] = None
    outbound_enabled: Optional[bool] = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.inbound_enabled is None and self.outbound_enabled is None:
            raise ValueError("Specify inbound_enabled and/or outbound_enabled")
        return self


# =============================================================================
# Outbound-only connections (blog / email / slack_webhook)
# =============================================================================

class OutboundConnectionCreate(BaseModel):
    """Create a blog / email / slack_webhook connection.

    Type-specific fields live in `config`; the validator enforces required
    keys per platform.
    """
    platform: Literal["blog", "email", "slack_webhook"]
    name: str = Field(..., min_length=1, max_length=200)
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_config_for_platform(self):
        cfg = self.config or {}
        if self.platform == "blog":
            if not cfg.get("api_url"):
                raise ValueError("blog config requires api_url")
            if not cfg.get("cms_type"):
                raise ValueError("blog config requires cms_type (ghost | wordpress | custom)")
        elif self.platform == "email":
            for key in ("provider", "api_key", "from_email"):
                if not cfg.get(key):
                    raise ValueError(f"email config requires {key}")
        elif self.platform == "slack_webhook":
            if not cfg.get("webhook_url"):
                raise ValueError("slack_webhook config requires webhook_url")
        return self


class OutboundConnectionUpdate(BaseModel):
    """Partial update for an outbound-only connection."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.name is None and self.config is None and self.enabled is None:
            raise ValueError("Specify at least one field to update")
        return self
