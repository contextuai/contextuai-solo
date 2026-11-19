"""
Audit Service & AI Bill of Materials (ABOM) Generator.

Provides fire-and-forget sync and async audit logging backed directly by the
native SQLite ``AuditRepository``, plus compliance ABOM generation and JSON/CSV
audit export helpers.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from models.audit_models import AuditAction, AuditSeverity
from repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB streaming chunks
_DEFAULT_SYNC_HASH_LIMIT_BYTES = 256 * 1024 * 1024  # 256 MB
_SHA256_CACHE: Dict[Tuple[str, int, int], str] = {}
_SHA256_CACHE_LOCK = threading.Lock()
_BG_SHA256_LOCK = threading.Lock()
_BG_SHA256_INFLIGHT: Set[str] = set()
_BG_SHA256_QUEUE: Deque[str] = deque()
_BG_SHA256_WORKER: Optional[threading.Thread] = None

_CSV_COLUMNS = [
    "id",
    "timestamp",
    "action",
    "severity",
    "user_id",
    "resource_type",
    "resource_id",
    "airplane_lock",
    "details_json",
]

# Map actions to default severity
_SEVERITY_MAP = {
    AuditAction.LOGIN_FAILURE: AuditSeverity.WARNING,
    AuditAction.API_KEY_REVOKED: AuditSeverity.WARNING,
    AuditAction.AUTOMATION_FAILED: AuditSeverity.ERROR,
    AuditAction.USER_DELETED: AuditSeverity.WARNING,
    AuditAction.ROLE_CHANGED: AuditSeverity.WARNING,
    AuditAction.SETTINGS_CHANGED: AuditSeverity.WARNING,
    AuditAction.SYSTEM_ERROR: AuditSeverity.ERROR,
    AuditAction.MODEL_INTEGRITY_FAILED: AuditSeverity.CRITICAL,
    AuditAction.DLP_REDACTED: AuditSeverity.WARNING,
}


def _current_airplane_lock_state() -> bool:
    """Safely read the current Airplane Lock state without ever raising."""
    try:
        from services import net_guard

        return bool(net_guard.is_airplane_lock_enabled())
    except Exception:
        return False


def _get_cached_sha256(path: str) -> Optional[str]:
    """Return cached SHA-256 hex digest without hashing file contents."""
    try:
        from services import enterprise_policy as _ep

        return _ep.get_cached_file_sha256(path)
    except ImportError:
        pass

    abs_path = os.path.abspath(path)
    try:
        st = os.stat(abs_path)
    except OSError:
        return None
    cache_key = (abs_path, int(st.st_size), int(st.st_mtime_ns))
    with _SHA256_CACHE_LOCK:
        return _SHA256_CACHE.get(cache_key)


def compute_file_sha256_cached(path: str) -> str:
    """Compute streaming SHA-256 hex digest cached in RAM and persistent disk cache."""
    try:
        from services import enterprise_policy as _ep

        return _ep.compute_file_sha256(path)
    except ImportError:
        pass

    abs_path = os.path.abspath(path)
    st = os.stat(abs_path)
    cache_key = (abs_path, int(st.st_size), int(st.st_mtime_ns))

    with _SHA256_CACHE_LOCK:
        cached = _SHA256_CACHE.get(cache_key)
        if cached is not None:
            return cached

    digest = hashlib.sha256()
    with open(abs_path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    hex_digest = digest.hexdigest().lower()

    with _SHA256_CACHE_LOCK:
        _SHA256_CACHE[cache_key] = hex_digest
    return hex_digest


def _bg_sha256_worker() -> None:
    global _BG_SHA256_WORKER
    while True:
        with _BG_SHA256_LOCK:
            if not _BG_SHA256_QUEUE:
                _BG_SHA256_WORKER = None
                return
            path = _BG_SHA256_QUEUE.popleft()
        try:
            compute_file_sha256_cached(path)
        except Exception as exc:
            logger.warning("Background SHA-256 computation failed for %s: %s", path, exc)
        finally:
            with _BG_SHA256_LOCK:
                _BG_SHA256_INFLIGHT.discard(path)


def _schedule_background_sha256(paths: List[str]) -> None:
    """Queue uncached model files on a single daemon worker so ABOM stays non-blocking."""
    global _BG_SHA256_WORKER
    if not paths:
        return
    with _BG_SHA256_LOCK:
        added = False
        for p in paths:
            abs_p = os.path.abspath(os.path.expanduser(p))
            if abs_p not in _BG_SHA256_INFLIGHT:
                _BG_SHA256_INFLIGHT.add(abs_p)
                _BG_SHA256_QUEUE.append(abs_p)
                added = True
        if added and (_BG_SHA256_WORKER is None or not _BG_SHA256_WORKER.is_alive()):
            worker = threading.Thread(
                target=_bg_sha256_worker,
                name="vesper-abom-sha256",
                daemon=True,
            )
            _BG_SHA256_WORKER = worker
            worker.start()


def _build_audit_event(
    action: AuditAction | str,
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
    severity: Optional[AuditSeverity | str] = None,
) -> Dict[str, Any]:
    """Construct a normalized audit event payload with Airplane Lock posture."""
    resolved_action = action.value if isinstance(action, AuditAction) else str(action)
    if severity is not None:
        resolved_severity = (
            severity.value if isinstance(severity, AuditSeverity) else str(severity)
        )
    else:
        resolved_severity = _SEVERITY_MAP.get(action, AuditSeverity.INFO).value  # type: ignore[arg-type]

    event: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "action": resolved_action,
        "severity": resolved_severity,
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
        "airplane_lock": _current_airplane_lock_state(),
    }
    return {k: v for k, v in event.items() if v is not None}


class AuditService:
    """Records and queries audit events using the local SQLite AuditRepository."""

    def __init__(self, repository: Optional[AuditRepository] = None):
        self.repository = repository if repository is not None else AuditRepository()

    def log_sync(
        self,
        action: AuditAction | str,
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
        severity: Optional[AuditSeverity | str] = None,
    ) -> None:
        """Synchronously record an audit event (fire-and-forget, never raises)."""
        try:
            event = _build_audit_event(
                action,
                user_id=user_id,
                user_email=user_email,
                auth_type=auth_type,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                request_method=request_method,
                request_path=request_path,
                response_status=response_status,
                severity=severity,
            )
            self.repository.log_event_sync(event)
        except Exception as exc:
            logger.error("Audit log_sync failed: %s", exc)

    async def log(
        self,
        action: AuditAction | str,
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
        severity: Optional[AuditSeverity | str] = None,
    ) -> None:
        """Asynchronously record an audit event (fire-and-forget, never raises)."""
        try:
            event = _build_audit_event(
                action,
                user_id=user_id,
                user_email=user_email,
                auth_type=auth_type,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                request_method=request_method,
                request_path=request_path,
                response_status=response_status,
                severity=severity,
            )
            await self.repository.log_event(event)
        except Exception as exc:
            logger.error("Audit log failed: %s", exc)

    async def query(self, **kwargs) -> tuple:
        """Query audit logs. Returns ``(events, total_count)``."""
        return await self.repository.query(**kwargs)


# ------------------------------------------------------------------
# Convenience helpers (call from anywhere without injecting the service)
# ------------------------------------------------------------------


def audit_log_sync(
    action: AuditAction | str,
    *,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: Optional[AuditSeverity | str] = None,
    user_id: Optional[str] = "desktop-user",
    repo: Optional[AuditRepository] = None,
    **kwargs,
) -> None:
    """Synchronous fire-and-forget audit helper writing directly to SQLite."""
    try:
        svc = AuditService(repo or AuditRepository())
        svc.log_sync(
            action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            severity=severity,
            **kwargs,
        )
    except Exception as exc:
        logger.error("audit_log_sync convenience function failed: %s", exc)


async def audit_log(
    action: AuditAction | str,
    *,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: Optional[AuditSeverity | str] = None,
    user_id: Optional[str] = "desktop-user",
    repo: Optional[AuditRepository] = None,
    **kwargs,
) -> None:
    """Async fire-and-forget audit helper writing directly to SQLite."""
    try:
        svc = AuditService(repo or AuditRepository())
        await svc.log(
            action,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            severity=severity,
            **kwargs,
        )
    except Exception as exc:
        logger.error("audit_log convenience function failed: %s", exc)


# ------------------------------------------------------------------
# ABOM & Compliance Export
# ------------------------------------------------------------------


def generate_abom(
    repo: Optional[AuditRepository] = None,
    *,
    compute_missing_hashes: Optional[bool] = None,
    sync_hash_limit_bytes: int = _DEFAULT_SYNC_HASH_LIMIT_BYTES,
) -> Dict[str, Any]:
    """Generate Vesper's AI Bill of Materials (ABOM) compliance snapshot."""
    target_repo = repo or AuditRepository()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        from services import net_guard

        privacy_posture: Dict[str, Any] = dict(net_guard.get_egress_ledger())
    except Exception as exc:
        logger.warning("ABOM privacy_posture unavailable: %s", exc)
        privacy_posture = {"airplane_lock": False, "error": str(exc)}

    try:
        from services import dlp_service

        dlp_posture: Dict[str, Any] = dict(dlp_service.get_dlp_settings())
    except Exception as exc:
        logger.debug("ABOM dlp_posture degraded gracefully: %s", exc)
        dlp_posture = {"available": False, "enabled": False}

    try:
        from services import enterprise_policy

        catalog_policy: Dict[str, Any] = dict(enterprise_policy.get_enterprise_policy())
    except Exception as exc:
        logger.debug("ABOM catalog_policy degraded gracefully: %s", exc)
        catalog_policy = {"available": False}

    installed_models: List[Dict[str, Any]] = []
    paths_to_hash: List[str] = []
    try:
        from services import model_manager as _mm_mod

        raw_installed = _mm_mod.model_manager.list_installed()
        for item in raw_installed:
            entry = dict(item)
            if entry.get("sha256"):
                entry.setdefault("hash_status", "cached")
            else:
                model_path = entry.get("path")
                if isinstance(model_path, str) and os.path.isfile(model_path):
                    try:
                        cached_sha = _get_cached_sha256(model_path)
                        if cached_sha:
                            entry["sha256"] = cached_sha
                            entry["hash_status"] = "cached"
                        else:
                            should_compute_sync = (
                                compute_missing_hashes is True
                                or (
                                    compute_missing_hashes is None
                                    and os.path.getsize(model_path) <= sync_hash_limit_bytes
                                )
                            )
                            if should_compute_sync:
                                entry["sha256"] = compute_file_sha256_cached(model_path)
                                entry["hash_status"] = "computed"
                            else:
                                entry["sha256"] = None
                                entry["hash_status"] = "computing"
                                paths_to_hash.append(model_path)
                    except Exception as sha_exc:
                        logger.warning(
                            "Failed to compute SHA-256 for %s: %s", model_path, sha_exc
                        )
            expected_sha = entry.get("expected_sha256")
            if expected_sha and entry.get("sha256") and "integrity_verified" not in entry:
                entry["integrity_verified"] = (
                    str(entry["sha256"]).lower() == str(expected_sha).lower()
                )
            installed_models.append(entry)
        _schedule_background_sha256(paths_to_hash)
    except Exception as exc:
        logger.warning("ABOM installed_models unavailable: %s", exc)

    try:
        from services import local_model_service as _lms_mod

        active_model: Dict[str, Any] = dict(_lms_mod.local_model_service.get_status())
    except Exception as exc:
        logger.debug("ABOM active_model degraded gracefully: %s", exc)
        active_model = {"loaded": False}

    try:
        audit_summary: Dict[str, Any] = target_repo.summary_counts_sync()
    except Exception as exc:
        logger.warning("ABOM audit_summary unavailable: %s", exc)
        audit_summary = {"total": 0, "by_action": {}, "by_severity": {}}

    return {
        "generated_at": generated_at,
        "app_name": "Vesper",
        "app_version": "1.2.0",
        "privacy_posture": privacy_posture,
        "dlp_posture": dlp_posture,
        "catalog_policy": catalog_policy,
        "installed_models": installed_models,
        "active_model": active_model,
        "audit_summary": audit_summary,
    }


def export_audit_json(repo: Optional[AuditRepository] = None, limit: int = 5000) -> str:
    """Export ABOM snapshot together with up to ``limit`` audit events as JSON."""
    target_repo = repo or AuditRepository()
    abom = generate_abom(repo=target_repo)
    events, _total = target_repo.query_sync(page=1, page_size=max(1, int(limit)))
    return json.dumps({"abom": abom, "events": events}, indent=2, default=str)


def export_audit_csv(repo: Optional[AuditRepository] = None, limit: int = 5000) -> str:
    """Export up to ``limit`` audit events as RFC-4180 CSV."""
    target_repo = repo or AuditRepository()
    events, _total = target_repo.query_sync(page=1, page_size=max(1, int(limit)))

    buf = io.StringIO(newline="")
    writer = csv.writer(buf, dialect="excel", lineterminator="\r\n")
    writer.writerow(_CSV_COLUMNS)

    for ev in events:
        details = ev.get("details")
        if details is not None:
            details_json = json.dumps(details, sort_keys=True, default=str)
        elif ev.get("details_json") is not None:
            details_json = str(ev.get("details_json"))
        else:
            details_json = ""

        writer.writerow([
            ev.get("id") or "",
            ev.get("timestamp") or "",
            ev.get("action") or "",
            ev.get("severity") or "",
            ev.get("user_id") or "",
            ev.get("resource_type") or "",
            ev.get("resource_id") or "",
            1 if ev.get("airplane_lock") else 0,
            details_json,
        ])

    return buf.getvalue()
