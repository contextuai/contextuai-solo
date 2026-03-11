"""
Pydantic models for the Audit Trail system.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class AuditAction(str, Enum):
    """Categories of auditable actions."""
    # Auth
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    TOKEN_REFRESH = "auth.token.refresh"
    API_KEY_CREATED = "auth.api_key.created"
    API_KEY_REVOKED = "auth.api_key.revoked"
    API_KEY_ROTATED = "auth.api_key.rotated"
    API_KEY_USED = "auth.api_key.used"

    # User management
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    ROLE_CHANGED = "user.role.changed"

    # Automations
    AUTOMATION_CREATED = "automation.created"
    AUTOMATION_UPDATED = "automation.updated"
    AUTOMATION_DELETED = "automation.deleted"
    AUTOMATION_EXECUTED = "automation.executed"
    AUTOMATION_FAILED = "automation.failed"
    WEBHOOK_TRIGGERED = "automation.webhook.triggered"

    # Chat / AI
    CHAT_MESSAGE_SENT = "chat.message.sent"
    SESSION_CREATED = "chat.session.created"

    # Workspace
    PROJECT_CREATED = "workspace.project.created"
    PROJECT_EXECUTED = "workspace.project.executed"

    # Data access
    DATA_EXPORTED = "data.exported"
    DATA_ACCESSED = "data.accessed"

    # Admin
    SETTINGS_CHANGED = "admin.settings.changed"
    PERSONA_CREATED = "admin.persona.created"
    PERSONA_UPDATED = "admin.persona.updated"
    PERSONA_DELETED = "admin.persona.deleted"

    # MFA
    MFA_SETUP_STARTED = "auth.mfa.setup_started"
    MFA_ENABLED = "auth.mfa.enabled"
    MFA_DISABLED = "auth.mfa.disabled"
    MFA_VERIFIED = "auth.mfa.verified"
    MFA_FAILED = "auth.mfa.failed"
    MFA_RECOVERY_USED = "auth.mfa.recovery_used"

    # System
    SYSTEM_ERROR = "system.error"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# --- Request models ---

class AuditQueryRequest(BaseModel):
    """Query parameters for searching audit logs."""
    user_id: Optional[str] = None
    action: Optional[str] = None
    severity: Optional[AuditSeverity] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    ip_address: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


# --- Response models ---

class AuditEventResponse(BaseModel):
    """Single audit event in API responses."""
    id: str
    timestamp: datetime
    action: str
    severity: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    auth_type: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    response_status: Optional[int] = None


class AuditListResponse(BaseModel):
    """Paginated list of audit events."""
    events: List[AuditEventResponse]
    total: int
    page: int
    page_size: int
