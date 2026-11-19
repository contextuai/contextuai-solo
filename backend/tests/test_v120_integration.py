"""End-to-end integration tests for Vesper v1.2.0 Wave 2 backend wiring."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List
from unittest.mock import patch

import pytest


@pytest.fixture
def isolated_vesper_env(monkeypatch, tmp_path):
    """Isolate all Vesper JSON/SQLite state files into a temporary directory."""
    monkeypatch.setenv("VESPER_DLP_POLICY_PATH", str(tmp_path / "dlp_policy.json"))
    monkeypatch.setenv("VESPER_AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    monkeypatch.setenv(
        "VESPER_ENTERPRISE_SETTINGS_PATH", str(tmp_path / "enterprise_settings.json")
    )
    monkeypatch.setenv(
        "VESPER_DEVELOPER_SETTINGS_PATH", str(tmp_path / "developer_settings.json")
    )
    monkeypatch.delenv("VESPER_DLP_ENABLED", raising=False)
    monkeypatch.delenv("VESPER_DLP_REDACT_LOGS", raising=False)
    monkeypatch.delenv("VESPER_AIRPLANE_LOCK_ENFORCED", raising=False)

    # Reset in-memory DLP policy cache and isolate model_manager models_dir
    # so ABOM tests don't SHA-256 hash tens of GBs of real user GGUF models.
    from services import dlp_service
    from services.model_manager import model_manager

    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(model_manager, "models_dir", models_dir)

    dlp_service._policy_cache = None
    yield tmp_path
    dlp_service._policy_cache = None


def test_dlp_settings_and_test_endpoints(test_app, isolated_vesper_env):
    resp = test_app.get("/api/v1/dlp/settings")
    assert resp.status_code == 200, resp.text
    settings_data = resp.json()
    assert settings_data["enabled"] is True
    assert "api_keys" in settings_data["categories"]

    upd = test_app.put(
        "/api/v1/dlp/settings",
        json={
            "enabled": True,
            "categories": {"emails": True, "api_keys": True},
        },
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["enabled"] is True

    test_res = test_app.post(
        "/api/v1/dlp/test",
        json={"text": "Contact alice@example.com with sk-ant-secretvalue1234567890"},
    )
    assert test_res.status_code == 200, test_res.text
    body = test_res.json()
    assert body["total_redactions"] >= 2
    assert "alice@example.com" not in body["redacted_text"]
    assert "sk-ant-secretvalue1234567890" not in body["redacted_text"]
    assert "emails" in body["categories"]
    assert "api_keys" in body["categories"]


def test_audit_events_abom_and_exports(test_app, isolated_vesper_env):
    # Trigger an audit event via DLP policy update
    upd = test_app.put("/api/v1/dlp/settings", json={"redact_logs": False})
    assert upd.status_code == 200

    events_resp = test_app.get("/api/v1/audit/events")
    assert events_resp.status_code == 200, events_resp.text
    events_body = events_resp.json()
    assert "events" in events_body
    assert events_body["total"] >= 1

    abom_resp = test_app.get("/api/v1/audit/abom")
    assert abom_resp.status_code == 200, abom_resp.text
    abom = abom_resp.json()
    assert abom["app_name"] == "Vesper"
    assert "privacy_posture" in abom
    assert "dlp_posture" in abom

    json_export = test_app.get("/api/v1/audit/export?format=json")
    assert json_export.status_code == 200
    assert "vesper-audit-abom.json" in json_export.headers.get("content-disposition", "")
    parsed_bundle = json.loads(json_export.text)
    assert "abom" in parsed_bundle and "events" in parsed_bundle

    csv_export = test_app.get("/api/v1/audit/export?format=csv")
    assert csv_export.status_code == 200
    assert "vesper-audit-abom.csv" in csv_export.headers.get("content-disposition", "")
    assert "id,timestamp,action,severity" in csv_export.text


def test_enterprise_policy_endpoint(test_app, isolated_vesper_env):
    resp = test_app.get("/api/v1/enterprise/policy")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "catalog_exclusive" in data
    assert "require_sha256" in data

    upd = test_app.put(
        "/api/v1/enterprise/policy",
        json={"require_sha256": True},
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["require_sha256"] is True


def test_local_server_config_toggle_gates_v1_endpoints(test_app, isolated_vesper_env):
    cfg = test_app.get("/api/v1/local-models/server-config")
    assert cfg.status_code == 200, cfg.text
    cfg_data = cfg.json()
    assert cfg_data["enabled"] is True
    assert cfg_data["server_enabled"] is True
    assert cfg_data["endpoint_base"] == "http://127.0.0.1:18741/v1"

    # Disable local /v1 server
    off = test_app.post("/api/v1/local-models/server-config", json={"enabled": False})
    assert off.status_code == 200, off.text
    assert off.json()["enabled"] is False
    assert off.json()["server_enabled"] is False

    chat_blocked = test_app.post(
        "/v1/chat/completions",
        json={
            "model": "qwen2.5-7b",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert chat_blocked.status_code == 503
    assert "Settings -> Developer" in chat_blocked.json()["detail"]

    comp_blocked = test_app.post(
        "/v1/completions",
        json={"model": "qwen2.5-7b", "prompt": "def add(a, b):"},
    )
    assert comp_blocked.status_code == 503

    # Re-enable local /v1 server
    on = test_app.post("/api/v1/local-models/server-config", json={"enabled": True})
    assert on.status_code == 200, on.text
    assert on.json()["enabled"] is True

    # With server re-enabled, missing model returns 404 (not 503)
    unblocked = test_app.post(
        "/v1/chat/completions",
        json={
            "model": "nonexistent-local-model-xyz",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert unblocked.status_code == 404


@pytest.mark.parametrize(
    "retired_path",
    [
        "/api/v1/reddit/account",
        "/api/v1/twitter/account",
        "/api/v1/connections",
        "/api/v1/distribution/channels",
    ],
)
def test_retired_social_and_distribution_routes_return_404(test_app, retired_path: str):
    resp = test_app.get(retired_path)
    assert resp.status_code == 404


def test_ai_chat_file_ids_and_cloud_dispatcher_streaming_metadata(
    test_app, db_proxy, isolated_vesper_env, tmp_path
):
    from services.cloud_provider_service import _creds_cache
    from services.file_storage_service import file_storage_service

    # Seed fake OpenAI credentials in temp DB
    async def _seed_creds():
        await db_proxy["cloud_providers"].insert_one(
            {
                "_id": "test-openai-integration",
                "provider_type": "openai",
                "display_name": "Test OpenAI",
                "config": {"api_key": "sk-test-provider-key-not-in-prompt"},
                "connected": True,
            }
        )

    asyncio.get_event_loop().run_until_complete(_seed_creds())
    _creds_cache.clear()

    # Upload an attached text file through FileStorageService
    upload_res = asyncio.get_event_loop().run_until_complete(
        file_storage_service.upload_file(
            user_id="test-user",
            filename="vesper_notes.txt",
            content=b"Vesper stores all local audit logs in SQLite WAL mode.",
            content_type="text/plain",
        )
    )
    file_id = upload_res["file_id"]

    captured_messages: List[Dict[str, Any]] = []

    async def _fake_openai_stream(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> AsyncIterator[Dict[str, Any]]:
        captured_messages.extend(messages)
        yield {"type": "delta", "content": "Based on [1], "}
        yield {"type": "delta", "content": "audit logs use SQLite WAL mode."}
        yield {
            "type": "done",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        }

    with patch(
        "services.openai_direct_service.OpenAIDirectService.stream_chat",
        new=_fake_openai_stream,
    ):
        resp = test_app.post(
            "/api/v1/ai-chat/",
            json={
                "prompt": "Summarize vesper_notes.txt and ignore sk-ant-leaksecret1234567890",
                "model_id": "openai:gpt-4o-mini",
                "stream": True,
                "file_ids": [file_id],
            },
        )

    _creds_cache.clear()
    assert resp.status_code == 200, resp.text

    # Verify outbound cloud messages included the attached file and redacted the secret
    assert len(captured_messages) >= 1
    outbound_user_text = captured_messages[-1]["content"]
    assert "SQLite WAL mode" in outbound_user_text
    assert "sk-ant-leaksecret1234567890" not in outbound_user_text

    # Parse SSE lines and assert is_final metadata + [DONE]
    lines = [
        line.strip()
        for line in resp.text.splitlines()
        if line.strip().startswith("data:")
    ]
    assert lines[-1] == "data: [DONE]"

    payloads = [
        json.loads(line[len("data:") :].strip())
        for line in lines[:-1]
        if line != "data: [DONE]"
    ]
    final_events = [p for p in payloads if p.get("is_final") is True]
    assert len(final_events) == 1, f"Expected 1 is_final metadata chunk, got: {payloads}"

    meta = final_events[0]["metadata"]
    assert meta["rag_mode"] == "full_context"
    assert len(meta["citations"]) == 1
    assert meta["citations"][0]["filename"] == "vesper_notes.txt"
    assert meta["dlp_redaction"]["total_redactions"] >= 1
    assert "api_keys" in meta["dlp_redaction"]["categories"]
