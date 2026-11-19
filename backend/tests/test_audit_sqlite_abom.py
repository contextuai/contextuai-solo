"""Tests for Issue #78: Local SQLite Audit Log, ABOM generation, exports, router & ToolLoopCircuitBreaker audit."""

from __future__ import annotations

import csv
import hashlib
import inspect
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.audit_models import AuditAction, AuditSeverity
from repositories import audit_repository as audit_repo_module
from repositories.audit_repository import AuditRepository
from routers.audit import router as audit_router
from services import net_guard
from services.audit_service import (
    AuditService,
    audit_log,
    audit_log_sync,
    compute_file_sha256_cached,
    export_audit_csv,
    export_audit_json,
    generate_abom,
)
from services.model_manager import model_manager
from services.tool_call_guard import ToolLoopCircuitBreaker


def test_audit_models_actions_and_no_motor_dependency():
    assert AuditAction.AUTOMATION_FAILED == "automation.failed"
    expected_actions = {
        "MODEL_LOADED": "model.loaded",
        "MODEL_DOWNLOADED": "model.downloaded",
        "MODEL_INTEGRITY_FAILED": "model.integrity_failed",
        "AIRPLANE_LOCK_CHANGED": "privacy.airplane_lock.changed",
        "DLP_REDACTED": "dlp.redacted",
        "DLP_POLICY_UPDATED": "dlp.policy.updated",
        "TOOL_EXECUTED": "tool.executed",
        "CATALOG_REFRESHED": "catalog.refreshed",
        "AUDIT_EXPORTED": "audit.exported",
    }
    for attr, value in expected_actions.items():
        assert getattr(AuditAction, attr).value == value

    repo_source = inspect.getsource(audit_repo_module)
    assert "motor" not in repo_source


async def test_sqlite_persistence_across_repository_instances(tmp_path, monkeypatch):
    db_file = tmp_path / "nested" / "audit.db"
    monkeypatch.setenv("VESPER_AUDIT_DB_PATH", str(db_file))

    repo1 = AuditRepository()
    assert Path(repo1.db_path) == db_file

    # Legacy non-path proxy object should be gracefully ignored
    legacy_proxy_repo = AuditRepository(MagicMock(name="LegacyDatabaseProxy"))
    assert Path(legacy_proxy_repo.db_path) == db_file

    repo1.log_event_sync(
        {
            "action": AuditAction.MODEL_LOADED.value,
            "severity": AuditSeverity.INFO.value,
            "user_id": "desktop-user",
            "resource_type": "model",
            "resource_id": "gemma4-e2b",
            "details": {"n_ctx": 8192},
            "airplane_lock": False,
        }
    )
    await repo1.log_event(
        {
            "action": AuditAction.DLP_REDACTED.value,
            "severity": AuditSeverity.WARNING.value,
            "user_id": "desktop-user",
            "resource_type": "cloud_chat",
            "resource_id": "openai",
            "details": {"total_redactions": 2, "categories": ["api_keys"]},
            "airplane_lock": True,
        }
    )

    # New instance pointing to same SQLite file reads persisted data
    repo2 = AuditRepository(str(db_file))
    events, total = await repo2.query()
    assert total == 2
    assert len(events) == 2

    summary = await repo2.summary_counts()
    assert summary["total"] == 2
    assert summary["by_action"]["model.loaded"] == 1
    assert summary["by_action"]["dlp.redacted"] == 1
    assert summary["by_severity"]["info"] == 1
    assert summary["by_severity"]["warning"] == 1

    # Verify SQLite WAL mode & indexes directly
    conn = sqlite3.connect(str(db_file))
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(journal_mode).lower() == "wal"
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(audit_events)").fetchall()
        }
        assert "idx_audit_events_timestamp" in indexes
        assert "idx_audit_events_action" in indexes
    finally:
        conn.close()

    repo2.clear_sync()
    events_after, total_after = await repo2.query()
    assert total_after == 0
    assert events_after == []


async def test_filtering_and_pagination(tmp_path):
    db_file = tmp_path / "filter_audit.db"
    repo = AuditRepository(str(db_file))

    samples = [
        ("2026-11-10T09:00:00Z", "model.downloaded", "info", "model", "m1", "u1"),
        ("2026-11-11T10:00:00Z", "model.loaded", "info", "model", "m1", "u1"),
        ("2026-11-12T11:00:00Z", "model.integrity_failed", "critical", "model", "m2", "u1"),
        ("2026-11-13T12:00:00Z", "dlp.redacted", "warning", "cloud", "openai", "u2"),
        ("2026-11-14T13:00:00Z", "tool.executed", "info", "tool", "web_search", "u1"),
    ]
    for ts, action, sev, rtype, rid, uid in samples:
        repo.log_event_sync(
            {
                "timestamp": ts,
                "action": action,
                "severity": sev,
                "resource_type": rtype,
                "resource_id": rid,
                "user_id": uid,
            }
        )

    # Prefix matching
    model_events, model_total = await repo.query(action="model.*")
    assert model_total == 3
    assert [e["action"] for e in model_events] == [
        "model.integrity_failed",
        "model.loaded",
        "model.downloaded",
    ]

    # Exact action + severity
    crit_events, crit_total = await repo.query(severity="critical")
    assert crit_total == 1
    assert crit_events[0]["resource_id"] == "m2"

    # Date range filtering (inclusive YYYY-MM-DD)
    ranged, ranged_total = await repo.query(
        from_date="2026-11-11",
        to_date=datetime(2026, 11, 13, 23, 59, 59, tzinfo=timezone.utc),
    )
    assert ranged_total == 3
    assert [e["action"] for e in ranged] == [
        "dlp.redacted",
        "model.integrity_failed",
        "model.loaded",
    ]

    # Pagination
    page1, p_total = await repo.query(page=1, page_size=2)
    page2, _ = await repo.query(page=2, page_size=2)
    page3, _ = await repo.query(page=3, page_size=2)
    assert p_total == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1
    assert page1[0]["action"] == "tool.executed"
    assert page3[0]["action"] == "model.downloaded"


async def test_audit_log_sync_and_async_stamp_airplane_lock(tmp_path, monkeypatch):
    db_file = tmp_path / "svc_audit.db"
    monkeypatch.setenv("VESPER_AUDIT_DB_PATH", str(db_file))
    net_guard.set_airplane_lock(False)

    try:
        audit_log_sync(
            AuditAction.CATALOG_REFRESHED,
            resource_type="catalog",
            resource_id="test_sync",
            details={"merged_count": 3},
        )
        net_guard.set_airplane_lock(True)
        await audit_log(
            AuditAction.MODEL_LOADED,
            resource_type="model",
            resource_id="test_async",
            details={"n_ctx": 4096},
        )
    finally:
        net_guard.set_airplane_lock(False)

    repo = AuditRepository(str(db_file))
    sync_events, sync_total = await repo.query(resource_id="test_sync")
    assert sync_total == 1
    assert sync_events[0]["action"] == "catalog.refreshed"
    assert sync_events[0]["airplane_lock"] is False
    assert sync_events[0]["user_id"] == "desktop-user"

    async_events, async_total = await repo.query(resource_id="test_async")
    assert async_total == 1
    assert async_events[0]["action"] == "model.loaded"
    assert async_events[0]["airplane_lock"] is True

    # Fire-and-forget never raises even when repository raises
    broken_repo = MagicMock()
    broken_repo.log_event_sync.side_effect = RuntimeError("disk full")
    AuditService(broken_repo).log_sync(AuditAction.SYSTEM_ERROR)


def test_generate_abom_with_synthetic_gguf_sha256(tmp_path, monkeypatch):
    db_file = tmp_path / "abom_audit.db"
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    gguf_path = models_dir / "synthetic-test-model.gguf"
    payload = b"GGUF" + b"\x00\x01vesper-test-weights" * 2048
    gguf_path.write_bytes(payload)
    expected_sha = hashlib.sha256(payload).hexdigest()

    monkeypatch.setenv("VESPER_AUDIT_DB_PATH", str(db_file))
    monkeypatch.setattr(model_manager, "models_dir", str(models_dir))

    repo = AuditRepository(str(db_file))
    audit_log_sync(
        AuditAction.MODEL_DOWNLOADED,
        resource_type="model",
        resource_id="synthetic-test-model",
        repo=repo,
    )

    abom = generate_abom(repo=repo)
    assert abom["app_name"] == "Vesper"
    assert abom["app_version"] == "1.2.0"
    assert abom["generated_at"]
    assert isinstance(abom["privacy_posture"], dict)
    assert "airplane_lock" in abom["privacy_posture"]
    assert isinstance(abom["dlp_posture"], dict)
    assert isinstance(abom["catalog_policy"], dict)
    assert isinstance(abom["active_model"], dict)
    assert abom["audit_summary"]["total"] == 1
    assert abom["audit_summary"]["by_action"]["model.downloaded"] == 1

    installed = abom["installed_models"]
    assert len(installed) == 1
    assert installed[0]["filename"] == "synthetic-test-model.gguf"
    assert installed[0]["sha256"] == expected_sha
    # Cached computation matches
    assert compute_file_sha256_cached(str(gguf_path)) == expected_sha


def test_export_json_and_csv_rfc4180(tmp_path, monkeypatch):
    db_file = tmp_path / "export_audit.db"
    models_dir = tmp_path / "empty_models"
    models_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VESPER_AUDIT_DB_PATH", str(db_file))
    monkeypatch.setattr(model_manager, "models_dir", str(models_dir))

    repo = AuditRepository(str(db_file))
    audit_log_sync(
        AuditAction.DLP_REDACTED,
        resource_type="cloud_chat",
        resource_id="anthropic",
        details={"note": 'contains, "quotes"\nand newline', "total": 1},
        repo=repo,
    )

    json_text = export_audit_json(repo=repo, limit=5000)
    bundle = json.loads(json_text)
    assert bundle["abom"]["app_name"] == "Vesper"
    assert len(bundle["events"]) == 1
    assert bundle["events"][0]["action"] == "dlp.redacted"

    csv_text = export_audit_csv(repo=repo, limit=5000)
    assert "\r\n" in csv_text
    reader = csv.DictReader(io.StringIO(csv_text))
    assert reader.fieldnames == [
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
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["action"] == "dlp.redacted"
    assert rows[0]["severity"] == "warning"
    assert json.loads(rows[0]["details_json"]) == {
        "note": 'contains, "quotes"\nand newline',
        "total": 1,
    }


def test_audit_router_endpoints(tmp_path, monkeypatch):
    db_file = tmp_path / "router_audit.db"
    models_dir = tmp_path / "router_models"
    models_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VESPER_AUDIT_DB_PATH", str(db_file))
    monkeypatch.setattr(model_manager, "models_dir", str(models_dir))

    audit_log_sync(
        AuditAction.MODEL_LOADED,
        resource_type="model",
        resource_id="qwen3-4b",
        details={"n_ctx": 8192},
    )
    audit_log_sync(
        AuditAction.DLP_REDACTED,
        resource_type="cloud_chat",
        resource_id="openai",
        details={"total_redactions": 3},
    )

    test_app = FastAPI()
    test_app.include_router(audit_router)
    client = TestClient(test_app)

    resp_events = client.get("/api/v1/audit/events?action=model.*")
    assert resp_events.status_code == 200
    payload = resp_events.json()
    assert payload["total"] == 1
    assert payload["events"][0]["action"] == "model.loaded"

    resp_bad_date = client.get("/api/v1/audit/events?from_date=not-a-date")
    assert resp_bad_date.status_code == 400

    resp_abom = client.get("/api/v1/audit/abom")
    assert resp_abom.status_code == 200
    abom = resp_abom.json()
    assert abom["app_name"] == "Vesper"
    assert abom["app_version"] == "1.2.0"
    assert abom["audit_summary"]["total"] == 2

    resp_json = client.get("/api/v1/audit/export?format=json")
    assert resp_json.status_code == 200
    assert (
        resp_json.headers.get("content-disposition")
        == 'attachment; filename="vesper-audit-abom.json"'
    )
    exported_json = resp_json.json()
    assert exported_json["abom"]["app_name"] == "Vesper"
    assert any(e["action"] == "audit.exported" for e in exported_json["events"])

    resp_csv = client.get("/api/v1/audit/export?format=csv")
    assert resp_csv.status_code == 200
    assert (
        resp_csv.headers.get("content-disposition")
        == 'attachment; filename="vesper-audit-abom.csv"'
    )
    csv_rows = list(csv.DictReader(io.StringIO(resp_csv.text)))
    assert any(r["action"] == "audit.exported" for r in csv_rows)

    resp_bad_fmt = client.get("/api/v1/audit/export?format=xml")
    assert resp_bad_fmt.status_code == 400


async def test_tool_loop_circuit_breaker_emits_audit_events(tmp_path, monkeypatch):
    db_file = tmp_path / "tool_guard_audit.db"
    monkeypatch.setenv("VESPER_AUDIT_DB_PATH", str(db_file))

    breaker = ToolLoopCircuitBreaker(max_identical=2, max_total=5)
    first = breaker.record_call("web_search", {"q": "vesper"})
    second = breaker.record_call("web_search", {"q": "vesper"})

    assert first["allowed"] is True
    assert first["tripped"] is False
    assert second["allowed"] is False
    assert second["tripped"] is True

    repo = AuditRepository(str(db_file))
    events, total = await repo.query(action=AuditAction.TOOL_EXECUTED.value)
    assert total == 2
    # Newest first
    assert events[0]["severity"] == AuditSeverity.WARNING.value
    assert events[0]["resource_type"] == "tool"
    assert events[0]["resource_id"] == "web_search"
    assert events[0]["details"]["tripped"] is True
    assert events[0]["details"]["allowed"] is False
    assert events[0]["details"]["identical_count"] == 2
    assert events[1]["details"]["tripped"] is False
    assert events[1]["details"]["allowed"] is True


def test_sha256_disk_cache_persists_across_memory_clear(tmp_path, monkeypatch):
    import hashlib
    from services import enterprise_policy

    cache_file = tmp_path / "model_sha256_cache.json"
    monkeypatch.setenv("VESPER_SHA256_CACHE_PATH", str(cache_file))

    gguf = tmp_path / "persisted.gguf"
    payload = b"vesper-gguf-payload-v1"
    gguf.write_bytes(payload)

    with enterprise_policy._SHA256_LOCK:
        enterprise_policy._SHA256_CACHE.clear()

    digest1 = enterprise_policy.compute_file_sha256(str(gguf))
    assert digest1 == hashlib.sha256(payload).hexdigest()
    assert cache_file.is_file()

    with enterprise_policy._SHA256_LOCK:
        enterprise_policy._SHA256_CACHE.clear()

    assert enterprise_policy.get_cached_file_sha256(str(gguf)) == digest1

    mutated = b"vesper-gguf-payload-mutated-size"
    gguf.write_bytes(mutated)
    with enterprise_policy._SHA256_LOCK:
        enterprise_policy._SHA256_CACHE.clear()

    assert enterprise_policy.get_cached_file_sha256(str(gguf)) is None
    digest2 = enterprise_policy.compute_file_sha256(str(gguf))
    assert digest2 == hashlib.sha256(mutated).hexdigest()
    assert digest2 != digest1


def test_generate_abom_hashes_large_models_async_and_caches(tmp_path, monkeypatch):
    import hashlib
    from repositories.audit_repository import AuditRepository
    from services import audit_service, enterprise_policy

    repo = AuditRepository(db_path=tmp_path / "audit_async_abom.db")
    monkeypatch.setenv("VESPER_SHA256_CACHE_PATH", str(tmp_path / "model_sha256_cache.json"))
    monkeypatch.setenv("VESPER_DLP_POLICY_PATH", str(tmp_path / "dlp.json"))
    monkeypatch.setenv("VESPER_ENTERPRISE_SETTINGS_PATH", str(tmp_path / "ent.json"))

    with enterprise_policy._SHA256_LOCK:
        enterprise_policy._SHA256_CACHE.clear()
    with audit_service._SHA256_CACHE_LOCK:
        audit_service._SHA256_CACHE.clear()

    small_gguf = tmp_path / "small.gguf"
    large_gguf = tmp_path / "large.gguf"
    small_bytes = b"s" * 512
    large_bytes = b"l" * 4096
    small_gguf.write_bytes(small_bytes)
    large_gguf.write_bytes(large_bytes)

    monkeypatch.setattr(
        "services.model_manager.model_manager.list_installed",
        lambda: [
            {
                "id": "local:small.gguf",
                "name": "Small Model",
                "filename": "small.gguf",
                "path": str(small_gguf),
                "size_gb": 0.001,
            },
            {
                "id": "local:large.gguf",
                "name": "Large Model",
                "filename": "large.gguf",
                "path": str(large_gguf),
                "size_gb": 20.0,
            },
        ],
    )

    abom1 = audit_service.generate_abom(repo=repo, sync_hash_limit_bytes=1024)
    by_id1 = {m["id"]: m for m in abom1["installed_models"]}

    assert by_id1["local:small.gguf"]["sha256"] == hashlib.sha256(small_bytes).hexdigest()
    assert by_id1["local:small.gguf"]["hash_status"] == "computed"
    assert by_id1["local:large.gguf"]["sha256"] is None
    assert by_id1["local:large.gguf"]["hash_status"] == "computing"

    worker = audit_service._BG_SHA256_WORKER
    if worker is not None:
        worker.join(timeout=5.0)

    abom2 = audit_service.generate_abom(repo=repo, sync_hash_limit_bytes=1024)
    by_id2 = {m["id"]: m for m in abom2["installed_models"]}

    assert by_id2["local:small.gguf"]["sha256"] == hashlib.sha256(small_bytes).hexdigest()
    assert by_id2["local:small.gguf"]["hash_status"] == "cached"
    assert by_id2["local:large.gguf"]["sha256"] == hashlib.sha256(large_bytes).hexdigest()
    assert by_id2["local:large.gguf"]["hash_status"] == "cached"

