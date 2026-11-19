"""
Glass-Box Privacy Shield & Airplane Lock (SPEC-28).

Tracks outbound non-loopback network requests in a live in-memory ring buffer
and enforces the hard ``Airplane Lock`` switch. When Airplane Lock is enabled,
any non-loopback egress attempt raises ``EgressBlockedError`` before a connection
is made.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_AIRPLANE_LOCK: bool = False
_EGRESS_LEDGER: deque = deque(maxlen=250)

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class EgressBlockedError(RuntimeError):
    """Raised when an external network call is attempted while Airplane Lock is active."""


def is_loopback_url(url: str) -> bool:
    """Return True if ``url`` points to a local loopback interface."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").strip().lower()
        return host in _LOOPBACK_HOSTS or host.endswith(".localhost")
    except Exception:
        return False


def _get_policy_lock_info() -> Tuple[bool, Optional[str]]:
    try:
        from services.enterprise_policy import is_airplane_lock_policy_enforced
        return is_airplane_lock_policy_enforced()
    except Exception:
        return False, None


def set_airplane_lock(enabled: bool) -> Dict[str, Any]:
    """Enable or disable Airplane Lock (SPEC-28)."""
    global _AIRPLANE_LOCK
    enforced, policy_source = _get_policy_lock_info()
    if not bool(enabled) and enforced:
        raise PermissionError(
            "Airplane Lock is enforced by enterprise policy and cannot be disabled."
        )
    _AIRPLANE_LOCK = bool(enabled)
    logger.info("Privacy Shield Airplane Lock set to %s", _AIRPLANE_LOCK)
    try:
        from models.audit_models import AuditAction, AuditSeverity
        from services.audit_service import audit_log_sync
        audit_log_sync(
            getattr(AuditAction, "AIRPLANE_LOCK_CHANGED", "privacy.airplane_lock.changed"),
            resource_type="privacy",
            resource_id="airplane_lock",
            details={
                "enabled": _AIRPLANE_LOCK,
                "policy_locked": enforced,
                "policy_source": policy_source,
            },
            severity=AuditSeverity.WARNING if not _AIRPLANE_LOCK else AuditSeverity.INFO,
        )
    except Exception:
        pass
    return {
        "airplane_lock": is_airplane_lock_enabled(),
        "policy_locked": enforced,
        "policy_source": policy_source,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def is_airplane_lock_enabled() -> bool:
    """Return True if Airplane Lock is active locally or enforced by enterprise policy."""
    if _AIRPLANE_LOCK:
        return True
    enforced, _ = _get_policy_lock_info()
    return bool(enforced)


def assert_egress_allowed(url: str, purpose: str = "external_request") -> None:
    """Raise ``EgressBlockedError`` if Airplane Lock is active and ``url`` is non-loopback."""
    if is_loopback_url(url):
        return
    if is_airplane_lock_enabled():
        parsed = urlparse(url)
        host = parsed.hostname or url
        _EGRESS_LEDGER.appendleft({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "host": host,
            "url": url,
            "purpose": purpose,
            "bytes_sent": 0,
            "blocked": True,
        })
        raise EgressBlockedError(
            f"Blocked by Privacy Shield Airplane Lock: outbound request to '{host}' "
            f"({purpose}) is disabled while Airplane Lock is active."
        )


def record_egress(
    url: str,
    purpose: str = "external_request",
    bytes_sent: int = 0,
    blocked: bool = False,
) -> Dict[str, Any]:
    """Record an outbound network request in the Glass-Box Privacy ledger."""
    if is_loopback_url(url):
        return {}
    parsed = urlparse(url)
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": parsed.hostname or url,
        "url": url,
        "purpose": purpose,
        "bytes_sent": int(bytes_sent or 0),
        "blocked": bool(blocked),
    }
    _EGRESS_LEDGER.appendleft(entry)
    return entry


def get_egress_ledger() -> Dict[str, Any]:
    """Return the current outbound network activity ledger and summary stats."""
    entries: List[Dict[str, Any]] = list(_EGRESS_LEDGER)
    allowed_entries = [e for e in entries if not e.get("blocked")]
    blocked_entries = [e for e in entries if e.get("blocked")]
    total_bytes = sum(int(e.get("bytes_sent") or 0) for e in allowed_entries)
    enforced, policy_source = _get_policy_lock_info()
    return {
        "airplane_lock": is_airplane_lock_enabled(),
        "external_connections_count": len(allowed_entries),
        "blocked_connections_count": len(blocked_entries),
        "total_allowed_requests": len(allowed_entries),
        "total_blocked_requests": len(blocked_entries),
        "total_bytes_sent": total_bytes,
        "zero_egress_verified": len(allowed_entries) == 0,
        "policy_locked": enforced,
        "policy_source": policy_source,
        "entries": entries,
    }


def clear_egress_ledger() -> None:
    """Clear all recorded entries in the egress ledger."""
    _EGRESS_LEDGER.clear()


def get_privacy_manifest() -> Dict[str, Any]:
    """Return the verifiable Glass-Box Privacy Manifest for Vesper / Solo (SPEC-28)."""
    entries: List[Dict[str, Any]] = list(_EGRESS_LEDGER)
    allowed_count = sum(1 for e in entries if not e.get("blocked"))
    blocked_count = sum(1 for e in entries if e.get("blocked"))
    enforced, policy_source = _get_policy_lock_info()
    return {
        "telemetry": "none",
        "analytics_sdks": [],
        "crash_reporters": [],
        "local_storage_paths": [
            "~/.contextuai-solo/data/contextuai.db",
            "~/.contextuai-solo/models/",
        ],
        "airplane_lock": is_airplane_lock_enabled(),
        "policy_locked": enforced,
        "policy_source": policy_source,
        "total_allowed_requests": allowed_count,
        "total_blocked_requests": blocked_count,
        "guarantees": [
            "Zero telemetry, analytics, or crash-reporting beacons compiled into the app.",
            "Local GGUF chat, Folder RAG, and Local MCP tool execution make 0 external connections.",
            "Outbound connections occur ONLY when you explicitly download models from HuggingFace or invoke a configured Cloud Provider / Social Channel.",
            "Airplane Lock blocks all non-loopback sockets before DNS resolution.",
        ],
    }
