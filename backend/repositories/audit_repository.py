"""
Audit Repository — Native SQLite storage for the Vesper local audit trail.

Provides thread-safe synchronous and async (``asyncio.to_thread``) operations
backed by SQLite in WAL mode so audit logging works reliably across sync hooks,
background threads, CLI scripts, and FastAPI async handlers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path, PurePath
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PATH_LOCKS: Dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    severity TEXT NOT NULL,
    user_id TEXT,
    user_email TEXT,
    auth_type TEXT,
    ip_address TEXT,
    user_agent TEXT,
    resource_type TEXT,
    resource_id TEXT,
    details_json TEXT,
    request_method TEXT,
    request_path TEXT,
    response_status INTEGER,
    airplane_lock INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp ON audit_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_action ON audit_events (action);
"""


def _get_path_lock(db_path: str) -> threading.RLock:
    """Return a re-entrant lock shared across instances targeting the same DB file."""
    if db_path == ":memory:":
        return threading.RLock()
    key = os.path.normcase(os.path.abspath(db_path))
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


def resolve_audit_db_path(db_path: Optional[Any] = None) -> str:
    """Resolve SQLite database path, gracefully ignoring legacy DB proxy objects."""
    if isinstance(db_path, (str, PurePath)):
        candidate = str(db_path).strip()
        if candidate:
            if candidate == ":memory:":
                return ":memory:"
            return os.path.expanduser(candidate)

    env_path = (os.getenv("VESPER_AUDIT_DB_PATH") or "").strip()
    if env_path:
        if env_path == ":memory:":
            return ":memory:"
        return os.path.expanduser(env_path)

    return os.path.join(os.path.expanduser("~"), ".contextuai-solo", "data", "audit.db")


def _normalize_timestamp(value: Any = None, *, is_end: bool = False) -> str:
    """Normalize datetime/date/ISO strings into canonical UTC ISO-8601 format."""
    if value is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    if isinstance(value, datetime):
        dt = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    if isinstance(value, date):
        if is_end:
            dt = datetime(value.year, value.month, value.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
        else:
            dt = datetime(value.year, value.month, value.day, 0, 0, 0, 0, tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    raw = str(value).strip()
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    if _DATE_ONLY_RE.match(raw):
        year, month, day = (int(part) for part in raw.split("-"))
        return _normalize_timestamp(date(year, month, day), is_end=is_end)

    try:
        parsed_input = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(parsed_input)
        return _normalize_timestamp(dt, is_end=is_end)
    except ValueError:
        return raw


def _escape_like(prefix: str) -> str:
    """Escape SQLite LIKE wildcards using backslash escape character."""
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _enum_or_str(value: Any) -> Optional[str]:
    """Extract string value from Enum or return stringified non-empty value."""
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    text = str(value)
    return text if text != "" else None


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a SQLite row into a normalized audit event dictionary."""
    details_raw = row["details_json"]
    details: Optional[Dict[str, Any]] = None
    if details_raw is not None and details_raw != "":
        try:
            parsed = json.loads(details_raw)
            details = parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            details = {"raw": details_raw}

    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "action": row["action"],
        "severity": row["severity"],
        "user_id": row["user_id"],
        "user_email": row["user_email"],
        "auth_type": row["auth_type"],
        "ip_address": row["ip_address"],
        "user_agent": row["user_agent"],
        "resource_type": row["resource_type"],
        "resource_id": row["resource_id"],
        "details": details,
        "request_method": row["request_method"],
        "request_path": row["request_path"],
        "response_status": row["response_status"],
        "airplane_lock": bool(row["airplane_lock"]),
    }


class AuditRepository:
    """Thread-safe SQLite repository for audit event storage and querying."""

    def __init__(self, db_path: Optional[Any] = None):
        self.db_path = resolve_audit_db_path(db_path)
        self._lock = _get_path_lock(self.db_path)
        self._mem_conn: Optional[sqlite3.Connection] = None
        self._init_schema()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self.db_path == ":memory:":
                if self._mem_conn is None:
                    self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
                    self._mem_conn.row_factory = sqlite3.Row
                yield self._mem_conn
                self._mem_conn.commit()
                return

            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
            try:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute("PRAGMA synchronous=NORMAL")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            if self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        """Close any persistent connection (relevant for ':memory:' databases)."""
        with self._lock:
            if self._mem_conn is not None:
                self._mem_conn.close()
                self._mem_conn = None

    def log_event_sync(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronously insert a single audit event into SQLite."""
        payload = dict(event or {})
        event_id = str(payload.get("id") or payload.get("_id") or uuid.uuid4())
        timestamp = _normalize_timestamp(payload.get("timestamp"))
        action = _enum_or_str(payload.get("action")) or "system.unknown"
        severity = _enum_or_str(payload.get("severity")) or "info"

        details = payload.get("details")
        details_json = payload.get("details_json")
        if details_json is None and details is not None:
            details_json = json.dumps(details, default=str)
        elif details is None and isinstance(details_json, str) and details_json.strip():
            try:
                parsed = json.loads(details_json)
                details = parsed if isinstance(parsed, dict) else {"value": parsed}
            except Exception:
                details = {"raw": details_json}

        response_status = payload.get("response_status")
        if response_status is not None:
            response_status = int(response_status)

        airplane_lock_int = 1 if payload.get("airplane_lock") else 0

        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO audit_events (
                    id, timestamp, action, severity,
                    user_id, user_email, auth_type, ip_address, user_agent,
                    resource_type, resource_id, details_json,
                    request_method, request_path, response_status, airplane_lock
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    timestamp,
                    action,
                    severity,
                    payload.get("user_id"),
                    payload.get("user_email"),
                    payload.get("auth_type"),
                    payload.get("ip_address"),
                    payload.get("user_agent"),
                    payload.get("resource_type"),
                    payload.get("resource_id"),
                    details_json,
                    payload.get("request_method"),
                    payload.get("request_path"),
                    response_status,
                    airplane_lock_int,
                ),
            )

        return {
            "id": event_id,
            "timestamp": timestamp,
            "action": action,
            "severity": severity,
            "user_id": payload.get("user_id"),
            "user_email": payload.get("user_email"),
            "auth_type": payload.get("auth_type"),
            "ip_address": payload.get("ip_address"),
            "user_agent": payload.get("user_agent"),
            "resource_type": payload.get("resource_type"),
            "resource_id": payload.get("resource_id"),
            "details": details,
            "request_method": payload.get("request_method"),
            "request_path": payload.get("request_path"),
            "response_status": response_status,
            "airplane_lock": bool(airplane_lock_int),
        }

    async def log_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Asynchronously insert a single audit event via thread pool."""
        return await asyncio.to_thread(self.log_event_sync, event)

    def query_sync(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        from_date: Optional[Any] = None,
        to_date: Optional[Any] = None,
        ip_address: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Synchronously query audit events with filters and pagination."""
        clauses: List[str] = []
        params: List[Any] = []

        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)

        norm_action = _enum_or_str(action)
        if norm_action:
            if norm_action.endswith(".*"):
                prefix = norm_action[:-1]
                clauses.append("action LIKE ? ESCAPE '\\'")
                params.append(_escape_like(prefix) + "%")
            elif norm_action.endswith("."):
                clauses.append("action LIKE ? ESCAPE '\\'")
                params.append(_escape_like(norm_action) + "%")
            else:
                clauses.append("action = ?")
                params.append(norm_action)

        norm_severity = _enum_or_str(severity)
        if norm_severity:
            clauses.append("severity = ?")
            params.append(norm_severity)

        if resource_type:
            clauses.append("resource_type = ?")
            params.append(resource_type)

        if resource_id:
            clauses.append("resource_id = ?")
            params.append(resource_id)

        if ip_address:
            clauses.append("ip_address = ?")
            params.append(ip_address)

        if from_date:
            clauses.append("timestamp >= ?")
            params.append(_normalize_timestamp(from_date, is_end=False))

        if to_date:
            clauses.append("timestamp <= ?")
            params.append(_normalize_timestamp(to_date, is_end=True))

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_page = max(1, int(page))
        safe_size = max(1, min(int(page_size), 50000))
        offset = (safe_page - 1) * safe_size

        with self._connection() as conn:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM audit_events {where_sql}",
                params,
            ).fetchone()
            total = int(total_row["cnt"]) if total_row else 0

            rows = conn.execute(
                f"""
                SELECT id, timestamp, action, severity,
                       user_id, user_email, auth_type, ip_address, user_agent,
                       resource_type, resource_id, details_json,
                       request_method, request_path, response_status, airplane_lock
                FROM audit_events
                {where_sql}
                ORDER BY timestamp DESC, rowid DESC
                LIMIT ? OFFSET ?
                """,
                [*params, safe_size, offset],
            ).fetchall()

        events = [_row_to_dict(row) for row in rows]
        return events, total

    async def query(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        from_date: Optional[Any] = None,
        to_date: Optional[Any] = None,
        ip_address: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Asynchronously query audit events with filters and pagination."""
        return await asyncio.to_thread(
            self.query_sync,
            user_id=user_id,
            action=action,
            severity=severity,
            resource_type=resource_type,
            resource_id=resource_id,
            from_date=from_date,
            to_date=to_date,
            ip_address=ip_address,
            page=page,
            page_size=page_size,
        )

    def summary_counts_sync(self) -> Dict[str, Any]:
        """Synchronously return aggregate audit counts by action and severity."""
        with self._connection() as conn:
            total_row = conn.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(CASE WHEN airplane_lock = 1 THEN 1 ELSE 0 END), 0) AS lock_cnt, "
                "MAX(timestamp) AS latest_ts "
                "FROM audit_events"
            ).fetchone()

            action_rows = conn.execute(
                "SELECT action, COUNT(*) AS cnt FROM audit_events GROUP BY action"
            ).fetchall()
            severity_rows = conn.execute(
                "SELECT severity, COUNT(*) AS cnt FROM audit_events GROUP BY severity"
            ).fetchall()

        by_action = {row["action"]: int(row["cnt"]) for row in action_rows}
        by_severity = {row["severity"]: int(row["cnt"]) for row in severity_rows}

        return {
            "total": int(total_row["total"]) if total_row else 0,
            "by_action": by_action,
            "by_severity": by_severity,
            "airplane_lock_events": int(total_row["lock_cnt"]) if total_row else 0,
            "latest_timestamp": total_row["latest_ts"] if total_row else None,
        }

    async def summary_counts(self) -> Dict[str, Any]:
        """Asynchronously return aggregate audit counts by action and severity."""
        return await asyncio.to_thread(self.summary_counts_sync)

    def clear_sync(self) -> None:
        """Synchronously delete all audit events (primarily for tests)."""
        with self._connection() as conn:
            conn.execute("DELETE FROM audit_events")

    async def clear(self) -> None:
        """Asynchronously delete all audit events."""
        await asyncio.to_thread(self.clear_sync)
