"""
Audit Service — Records and queries audit trail events.

Provides fire-and-forget logging that never blocks the main request.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from models.audit_models import AuditAction, AuditSeverity

logger = logging.getLogger(__name__)

# Map actions to default severity
_SEVERITY_MAP = {
    AuditAction.LOGIN_FAILURE: AuditSeverity.WARNING,
    AuditAction.API_KEY_REVOKED: AuditSeverity.WARNING,
    AuditAction.AUTOMATION_FAILED: AuditSeverity.ERROR,
    AuditAction.USER_DELETED: AuditSeverity.WARNING,
    AuditAction.ROLE_CHANGED: AuditSeverity.WARNING,
    AuditAction.SETTINGS_CHANGED: AuditSeverity.WARNING,
    AuditAction.SYSTEM_ERROR: AuditSeverity.ERROR,
}


class AuditService:
    """Records audit events to MongoDB."""

    def __init__(self, repository):
        self.repository = repository

    async def log(
        self,
        action: AuditAction,
        *,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        auth_type: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        response_status: Optional[int] = None,
        severity: Optional[AuditSeverity] = None,
    ) -> None:
        """
        Record an audit event. Designed to be fire-and-forget.

        Never raises — errors are logged but do not propagate.
        """
        try:
            event = {
                "timestamp": datetime.utcnow().isoformat(),
                "action": action.value if isinstance(action, AuditAction) else action,
                "severity": (
                    severity.value if severity
                    else _SEVERITY_MAP.get(action, AuditSeverity.INFO).value
                ),
                "user_id": user_id,
                "user_email": user_email,
                "auth_type": auth_type,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "details": details,
                "request_method": request_method,
                "request_path": request_path,
                "response_status": response_status,
            }
            # Strip None values to keep documents lean
            event = {k: v for k, v in event.items() if v is not None}
            await self.repository.log_event(event)
        except Exception as e:
            logger.error(f"Audit log failed: {e}")

    async def query(self, **kwargs) -> tuple:
        """Query audit logs. Returns (events, total_count)."""
        return await self.repository.query(**kwargs)


# ------------------------------------------------------------------
# Convenience helper (call from anywhere without injecting the service)
# ------------------------------------------------------------------

async def audit_log(
    action: AuditAction,
    **kwargs,
) -> None:
    """
    Module-level convenience function for logging audit events.

    Usage:
        from services.audit_service import audit_log, AuditAction
        await audit_log(AuditAction.LOGIN_SUCCESS, user_id="123", ip_address="1.2.3.4")
    """
    try:
        from database import get_database
        from repositories.audit_repository import AuditRepository

        db = await get_database()
        svc = AuditService(AuditRepository(db))
        await svc.log(action, **kwargs)
    except Exception as e:
        logger.error(f"audit_log convenience function failed: {e}")
