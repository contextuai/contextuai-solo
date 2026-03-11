"""
Pydantic models for the Event Subscription / Watcher system.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Categories of subscribable events."""
    # Automation lifecycle
    AUTOMATION_CREATED = "automation.created"
    AUTOMATION_UPDATED = "automation.updated"
    AUTOMATION_DELETED = "automation.deleted"

    # Execution lifecycle
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"

    # Workspace / Project
    PROJECT_CREATED = "project.created"
    PROJECT_COMPLETED = "project.completed"
    PROJECT_FAILED = "project.failed"

    # Crew lifecycle
    CREW_RUN_STARTED = "crew.run.started"
    CREW_RUN_COMPLETED = "crew.run.completed"
    CREW_RUN_FAILED = "crew.run.failed"

    # Auth events
    LOGIN_FAILURE = "auth.login.failure"
    MFA_FAILURE = "auth.mfa.failure"

    # Data events
    DATA_EXPORTED = "data.exported"

    # Webhook inbound
    WEBHOOK_RECEIVED = "webhook.received"

    # Wildcard
    ALL = "*"


class DeliveryChannel(str, Enum):
    """Notification delivery channels."""
    WEBHOOK = "webhook"
    SLACK = "slack"
    EMAIL = "email"


class SubscriptionStatus(str, Enum):
    """Subscription lifecycle states."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


# ---------------------------------------------------------------------------
# Channel Configuration
# ---------------------------------------------------------------------------

class WebhookChannelConfig(BaseModel):
    """Config for webhook delivery."""
    url: str
    secret: Optional[str] = None   # For HMAC signature
    headers: Optional[Dict[str, str]] = None


class SlackChannelConfig(BaseModel):
    """Config for Slack delivery."""
    webhook_url: Optional[str] = None
    channel: Optional[str] = None


class EmailChannelConfig(BaseModel):
    """Config for email delivery."""
    to: List[str]
    subject_template: Optional[str] = None


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class CreateSubscriptionRequest(BaseModel):
    """Create a new event subscription."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    event_types: List[str] = Field(..., min_length=1)
    channel: DeliveryChannel
    channel_config: Dict[str, Any]
    filters: Optional[Dict[str, Any]] = None   # e.g. {"automation_id": "specific-id"}
    enabled: bool = True


class UpdateSubscriptionRequest(BaseModel):
    """Update an event subscription."""
    name: Optional[str] = None
    description: Optional[str] = None
    event_types: Optional[List[str]] = None
    channel: Optional[DeliveryChannel] = None
    channel_config: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    status: Optional[SubscriptionStatus] = None


class SubscriptionResponse(BaseModel):
    """Full subscription detail."""
    id: Optional[str] = None
    subscription_id: str
    user_id: str
    name: str
    description: Optional[str] = None
    event_types: List[str]
    channel: str
    channel_config: Dict[str, Any]
    filters: Optional[Dict[str, Any]] = None
    status: str
    delivery_count: int = 0
    last_delivered_at: Optional[str] = None
    failure_count: int = 0
    created_at: str
    updated_at: str


class SubscriptionListItem(BaseModel):
    """Lightweight subscription for listing."""
    subscription_id: str
    name: str
    event_types: List[str]
    channel: str
    status: str
    delivery_count: int = 0
    failure_count: int = 0
    created_at: str


class EventDeliveryLog(BaseModel):
    """Record of an event delivery attempt."""
    delivery_id: str
    subscription_id: str
    event_type: str
    channel: str
    status: str   # "delivered", "failed", "pending"
    response_code: Optional[int] = None
    error: Optional[str] = None
    payload_summary: Optional[str] = None
    delivered_at: str
