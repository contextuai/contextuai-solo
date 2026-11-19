"""
Comprehensive tests for Issue #77: On-Device PII & Secret Redaction / Local DLP.

Covers:
- Built-in secret/PII detectors (API keys, PEM keys, Bearer/assignments, emails,
  US/international phones, SSNs, Luhn-validated credit cards)
- False-positive protection (non-Luhn numbers, ISO dates, semver, UUIDs, epoch timestamps)
- Policy persistence at VESPER_DLP_POLICY_PATH & env overrides (VESPER_DLP_ENABLED, VESPER_DLP_REDACT_LOGS)
- Custom regex validation (ValueError) & execution
- redact_messages non-mutation for string and list-of-parts content
- DlpLogFilter log scrubbing
- /api/v1/dlp/* FastAPI router endpoints via TestClient (including HTTP 400 on bad regex)
- model_dispatcher.stream_chat cloud redaction, dlp_redacted event, clean pass-through,
  loopback Ollama exemption, and Airplane Lock egress enforcement
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, AsyncIterator, Dict, List
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def isolated_dlp_env(tmp_path, monkeypatch):
    """Ensure every test runs against isolated temp DLP policy and audit DB paths."""
    policy_file = tmp_path / "dlp_policy.json"
    audit_db = tmp_path / "audit.db"
    monkeypatch.setenv("VESPER_DLP_POLICY_PATH", str(policy_file))
    monkeypatch.setenv("VESPER_AUDIT_DB_PATH", str(audit_db))
    monkeypatch.delenv("VESPER_DLP_ENABLED", raising=False)
    monkeypatch.delenv("VESPER_DLP_REDACT_LOGS", raising=False)

    import services.dlp_service as dlp_service
    from services import net_guard

    dlp_service._policy_cache = None
    net_guard.set_airplane_lock(False)
    net_guard.clear_egress_ledger()
    yield policy_file
    dlp_service._policy_cache = None
    net_guard.set_airplane_lock(False)
    net_guard.clear_egress_ledger()


# ---------------------------------------------------------------------------
# Built-in detectors
# ---------------------------------------------------------------------------

def test_detects_all_builtin_api_keys_and_pem():
    from services.dlp_service import scan_and_redact

    openai_key = "sk-testkey1234567890abcdef"
    openai_proj = "sk-proj-testprojectkey1234567890"
    anthropic_key = "sk-ant-api03-testkey1234567890abcd"
    aws_key = "AKIAIOSFODNN7EXAMPLE"
    gh_classic = "ghp_1234567890abcdef1234567890abcdef1234"
    gh_oauth = "gho_abcdef1234567890abcdef1234567890abcd"
    gh_pat = "github_pat_11ABCDEFG0123456789_xyz"
    slack_key = "xoxb-123456789012-123456789012-abcdef123456"
    google_key = "AIza" + ("A1b2C3d4E5" * 3) + "XyZ98"  # exactly 35 chars after AIza
    pem_block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIBOgIBAAJBALeFakeKeyMaterialLineOne1234567890\n"
        "-----END RSA PRIVATE KEY-----"
    )
    bearer_header = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload123.sig456"
    secret_assign = 'client_secret="super_secret_value_99"'

    text = "\n".join([
        openai_key,
        openai_proj,
        anthropic_key,
        aws_key,
        gh_classic,
        gh_oauth,
        gh_pat,
        slack_key,
        google_key,
        pem_block,
        bearer_header,
        secret_assign,
    ])

    res = scan_and_redact(text)
    assert res.total_redactions == 12
    assert res.categories == ["api_keys"]
    assert res.counts_by_category == {"api_keys": 12}

    for secret in [
        openai_key,
        openai_proj,
        anthropic_key,
        aws_key,
        gh_classic,
        gh_oauth,
        gh_pat,
        slack_key,
        google_key,
        "MIIBOgIBAAJBALeFakeKeyMaterialLineOne1234567890",
        "eyJhbGciOiJIUzI1NiJ9.payload123.sig456",
        "super_secret_value_99",
    ]:
        assert secret not in res.redacted_text

    assert "[REDACTED:PRIVATE_KEY]" in res.redacted_text
    assert "Authorization: Bearer [REDACTED:API_KEY]" in res.redacted_text
    assert 'client_secret="[REDACTED:API_KEY]"' in res.redacted_text
    # Ensure raw secrets never appear in summary
    summary_str = json.dumps(res.to_summary())
    assert openai_proj not in summary_str
    assert aws_key not in summary_str


def test_api_key_false_positive_guards():
    from services.dlp_service import scan_and_redact

    safe = (
        "Bearer authentication is documented in RFC 6750. "
        'Use api_key = os.getenv("OPENAI_API_KEY"), token = config.api_token, '
        "and password = self.settings.password."
    )
    res = scan_and_redact(safe)
    assert res.total_redactions == 0
    assert res.redacted_text == safe

    trailing_dot = scan_and_redact("token = my_secret_12345.")
    assert trailing_dot.total_redactions == 1
    assert trailing_dot.redacted_text == "token = [REDACTED:API_KEY]."


def test_emails_ssns_and_credit_cards_with_luhn():
    from services.dlp_service import scan_and_redact

    # 4532-0151-1283-0366 is Luhn-valid; 4532-0151-1283-0367 is Luhn-invalid
    # 1234-5678-9012-3456 is Luhn-invalid; 0000-0000-0000-0000 is rejected
    text = (
        "Contact alice.smith+dev@example.com, SSN 123-45-6789, "
        "valid card 4532-0151-1283-0366, spaced 4111 1111 1111 1111, "
        "invalid card 4532-0151-1283-0367, bad card 1234-5678-9012-3456, "
        "zeros 0000-0000-0000-0000, mention @dlp-guard."
    )
    res = scan_and_redact(text)

    assert "alice.smith+dev@example.com" not in res.redacted_text
    assert "123-45-6789" not in res.redacted_text
    assert "4532-0151-1283-0366" not in res.redacted_text
    assert "4111 1111 1111 1111" not in res.redacted_text

    # Non-Luhn / invalid numbers & @mention must be preserved intact
    assert "4532-0151-1283-0367" in res.redacted_text
    assert "1234-5678-9012-3456" in res.redacted_text
    assert "0000-0000-0000-0000" in res.redacted_text
    assert "@dlp-guard" in res.redacted_text

    assert res.counts_by_category == {
        "emails": 1,
        "ssns": 1,
        "credit_cards": 2,
    }
    assert res.categories == ["credit_cards", "emails", "ssns"]
    assert res.total_redactions == 4


def test_phones_match_us_and_intl_but_ignore_dates_semver_uuids_and_timestamps():
    from services.dlp_service import scan_and_redact

    text = (
        "US: (415) 555-0199 and 415-555-0123 and +1-800-555-0144 and 415.555.0188; "
        "Intl: +44 20 7946 0958 and +91 98765 43210. "
        "Keep ISO date 2026-11-19 and timestamp 2026-11-19T15:42:52Z, "
        "semver v1.2.3 and 12.34.56, "
        "UUID 550e8400-e29b-41d4-a716-446655440000 and 12345678-1234-5678-9012-123456789012, "
        "IPv4 192.168.1.100, and epoch 1732030972."
    )
    res = scan_and_redact(text)

    for phone in [
        "(415) 555-0199",
        "415-555-0123",
        "+1-800-555-0144",
        "415.555.0188",
        "+44 20 7946 0958",
        "+91 98765 43210",
    ]:
        assert phone not in res.redacted_text

    for safe_token in [
        "2026-11-19",
        "2026-11-19T15:42:52Z",
        "v1.2.3",
        "12.34.56",
        "550e8400-e29b-41d4-a716-446655440000",
        "12345678-1234-5678-9012-123456789012",
        "192.168.1.100",
        "1732030972",
    ]:
        assert safe_token in res.redacted_text

    assert res.categories == ["phones"]
    assert res.total_redactions == 6


# ---------------------------------------------------------------------------
# Policy persistence, category toggles, custom rules, env overrides
# ---------------------------------------------------------------------------

def test_custom_rules_validation_and_execution(isolated_dlp_env):
    from services.dlp_service import get_dlp_settings, scan_and_redact, update_dlp_settings

    # Invalid regex raises ValueError
    with pytest.raises(ValueError, match="Invalid regex"):
        update_dlp_settings({
            "custom_rules": [
                {"name": "Broken", "pattern": "([unclosed", "placeholder": "[BAD]", "enabled": True}
            ]
        })

    # Valid rule persists to disk
    updated = update_dlp_settings({
        "categories": {"emails": False},
        "custom_rules": [
            {
                "id": "emp-id",
                "name": "Employee ID",
                "pattern": r"EMP-\d{6}",
                "placeholder": "[REDACTED:EMP_ID]",
                "enabled": True,
            },
            {
                "id": "disabled-rule",
                "name": "Disabled Rule",
                "pattern": r"PROJ-\d{3}",
                "placeholder": "[REDACTED:PROJ]",
                "enabled": False,
            },
        ],
    })
    assert isolated_dlp_env.exists()
    assert updated["categories"]["emails"] is False
    assert len(updated["custom_rules"]) == 2

    reloaded = get_dlp_settings()
    assert reloaded["custom_rules"][0]["id"] == "emp-id"

    res = scan_and_redact("User alice@example.com has EMP-123456 on PROJ-999")
    assert "alice@example.com" in res.redacted_text  # emails disabled
    assert "EMP-123456" not in res.redacted_text
    assert "[REDACTED:EMP_ID]" in res.redacted_text
    assert "PROJ-999" in res.redacted_text  # disabled rule ignored
    assert res.categories == ["custom"]
    assert res.total_redactions == 1


def test_env_overrides_dlp_enabled(monkeypatch):
    from services.dlp_service import get_dlp_settings, scan_and_redact, update_dlp_settings

    update_dlp_settings({"enabled": True})
    monkeypatch.setenv("VESPER_DLP_ENABLED", "false")
    settings = get_dlp_settings()
    assert settings["enabled"] is False

    res = scan_and_redact("Key sk-testkey1234567890abcdef and bob@example.com")
    assert res.total_redactions == 0
    assert "sk-testkey1234567890abcdef" in res.redacted_text


# ---------------------------------------------------------------------------
# redact_messages non-mutation & list-of-parts
# ---------------------------------------------------------------------------

def test_redact_messages_non_mutation_string_and_parts():
    from services.dlp_service import redact_messages

    original_messages = [
        {"role": "system", "content": "Contact admin@corp.com"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Use key AKIAIOSFODNN7EXAMPLE"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
            ],
        },
        {"role": "assistant", "content": None},
    ]

    redacted, summary = redact_messages(original_messages)

    # Original objects must remain completely untouched
    assert original_messages[0]["content"] == "Contact admin@corp.com"
    assert original_messages[1]["content"][0]["text"] == "Use key AKIAIOSFODNN7EXAMPLE"
    assert redacted is not original_messages
    assert redacted[1] is not original_messages[1]
    assert redacted[1]["content"] is not original_messages[1]["content"]
    assert redacted[1]["content"][0] is not original_messages[1]["content"][0]

    assert redacted[0]["content"] == "Contact [REDACTED:EMAIL]"
    assert redacted[1]["content"][0]["text"] == "Use key [REDACTED:API_KEY]"
    assert redacted[1]["content"][1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}}
    assert redacted[2]["content"] is None

    assert summary["total_redactions"] == 2
    assert summary["total"] == 2
    assert summary["categories"] == ["api_keys", "emails"]
    assert summary["counts_by_category"] == {"emails": 1, "api_keys": 1}


# ---------------------------------------------------------------------------
# DlpLogFilter
# ---------------------------------------------------------------------------

def test_dlp_log_filter_respects_redact_logs_setting(monkeypatch):
    from services.dlp_service import DlpLogFilter

    test_logger = logging.getLogger("test.vesper.dlp")
    test_logger.setLevel(logging.INFO)
    test_logger.propagate = False

    captured: List[str] = []

    class _MemHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(self.format(record))

    handler = _MemHandler()
    handler.addFilter(DlpLogFilter())
    test_logger.handlers = [handler]

    secret = "sk-proj-secretlogkey1234567890ab"
    email = "secret.user@example.com"

    # Default VESPER_DLP_REDACT_LOGS=false -> logs left untouched
    test_logger.info("Sending %s to %s", secret, email)
    assert secret in captured[-1]
    assert email in captured[-1]

    # Enable VESPER_DLP_REDACT_LOGS=true -> logs scrubbed
    monkeypatch.setenv("VESPER_DLP_REDACT_LOGS", "true")
    test_logger.info("Sending %s to %s", secret, email)
    assert secret not in captured[-1]
    assert email not in captured[-1]
    assert "[REDACTED:API_KEY]" in captured[-1]
    assert "[REDACTED:EMAIL]" in captured[-1]

    test_logger.handlers = []


# ---------------------------------------------------------------------------
# Router endpoints via TestClient
# ---------------------------------------------------------------------------

def test_dlp_router_endpoints():
    from routers.dlp import router as dlp_router

    app = FastAPI()
    app.include_router(dlp_router)
    client = TestClient(app)

    # GET settings
    r_get = client.get("/api/v1/dlp/settings")
    assert r_get.status_code == 200
    body = r_get.json()
    assert body["enabled"] is True
    assert body["redact_logs"] is False
    assert body["categories"]["api_keys"] is True

    # PUT invalid custom regex -> HTTP 400
    r_bad = client.put(
        "/api/v1/dlp/settings",
        json={
            "custom_rules": [
                {"name": "Bad", "pattern": "[unclosed", "placeholder": "[X]", "enabled": True}
            ]
        },
    )
    assert r_bad.status_code == 400

    # PUT valid update
    r_put = client.put(
        "/api/v1/dlp/settings",
        json={
            "redact_logs": True,
            "categories": {"phones": False},
            "custom_rules": [
                {
                    "id": "acct-1",
                    "name": "Account",
                    "pattern": r"ACCT-\d{4}",
                    "placeholder": "[REDACTED:ACCT]",
                    "enabled": True,
                }
            ],
        },
    )
    assert r_put.status_code == 200
    updated = r_put.json()
    assert updated["redact_logs"] is True
    assert updated["categories"]["phones"] is False
    assert len(updated["custom_rules"]) == 1

    # POST /test dry-run
    r_test = client.post(
        "/api/v1/dlp/test",
        json={"text": "Account ACCT-4242 email dev@example.com phone 415-555-0199"},
    )
    assert r_test.status_code == 200
    res = r_test.json()
    assert res["total_redactions"] == 2
    assert res["categories"] == ["custom", "emails"]
    assert "[REDACTED:ACCT]" in res["redacted_text"]
    assert "[REDACTED:EMAIL]" in res["redacted_text"]
    assert "415-555-0199" in res["redacted_text"]  # phones disabled


# ---------------------------------------------------------------------------
# model_dispatcher.stream_chat integration
# ---------------------------------------------------------------------------

async def _fake_provider_stream(tokens: List[str]) -> AsyncIterator[Dict[str, Any]]:
    for tok in tokens:
        yield {"type": "delta", "content": tok}
    yield {"type": "done", "finish_reason": "stop", "usage": {"total_tokens": len(tokens)}}


@pytest.mark.asyncio
async def test_model_dispatcher_redacts_cloud_messages_and_emits_event(db_proxy):
    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "dlp-oai-1",
        "provider_type": "openai",
        "display_name": "OpenAI",
        "config": {"api_key": "test-openai-key"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    captured_messages: List[Dict[str, Any]] = []

    def _mock_stream(self_or_msgs, messages, *args, **kwargs):
        captured_messages.extend(messages)
        return _fake_provider_stream(["OK"])

    input_messages = [
        {"role": "user", "content": "Email alice@example.com with sk-proj-secret1234567890abcd"}
    ]

    with patch("services.openai_direct_service.OpenAIDirectService.stream_chat", new=_mock_stream):
        from services.model_dispatcher import stream_chat
        events = [
            evt
            async for evt in stream_chat("openai:gpt-4o", input_messages, db=db_proxy)
        ]

    _creds_cache.clear()

    # Original caller messages not mutated
    assert "alice@example.com" in input_messages[0]["content"]
    # Outbound cloud messages were sanitized
    assert "alice@example.com" not in captured_messages[0]["content"]
    assert "sk-proj-secret1234567890abcd" not in captured_messages[0]["content"]
    assert "[REDACTED:EMAIL]" in captured_messages[0]["content"]
    assert "[REDACTED:API_KEY]" in captured_messages[0]["content"]

    # dlp_redacted event emitted before deltas
    assert events[0]["type"] == "dlp_redacted"
    assert events[0]["summary"]["total_redactions"] == 2
    assert events[0]["summary"]["categories"] == ["api_keys", "emails"]
    assert events[1]["type"] == "delta"
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_model_dispatcher_clean_messages_emit_no_dlp_event(db_proxy):
    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "dlp-oai-2",
        "provider_type": "openai",
        "display_name": "OpenAI",
        "config": {"api_key": "test-openai-key"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    def _mock_stream(self_or_msgs, messages, *args, **kwargs):
        return _fake_provider_stream(["Hello"])

    with patch("services.openai_direct_service.OpenAIDirectService.stream_chat", new=_mock_stream):
        from services.model_dispatcher import stream_chat
        events = [
            evt
            async for evt in stream_chat(
                "openai:gpt-4o",
                [{"role": "user", "content": "Explain photosynthesis on 2026-11-19."}],
                db=db_proxy,
            )
        ]

    _creds_cache.clear()
    assert not any(e["type"] == "dlp_redacted" for e in events)
    assert [e["type"] for e in events] == ["delta", "done"]


@pytest.mark.asyncio
async def test_model_dispatcher_loopback_ollama_skips_dlp_and_allows_airplane_lock(db_proxy):
    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "dlp-ollama-local",
        "provider_type": "ollama",
        "display_name": "Local Ollama",
        "config": {"base_url": "http://localhost:11434"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    from services import net_guard
    _creds_cache.clear()
    net_guard.set_airplane_lock(True)

    captured_messages: List[Dict[str, Any]] = []

    def _mock_ollama(self_or_msgs, messages, *args, **kwargs):
        captured_messages.extend(messages)
        return _fake_provider_stream(["Local reply"])

    secret_msg = "Check key sk-proj-localtest1234567890ab"
    with patch("services.ollama_direct_service.OllamaDirectService.stream_chat", new=_mock_ollama):
        from services.model_dispatcher import stream_chat
        events = [
            evt
            async for evt in stream_chat(
                "ollama:qwen2.5:7b",
                [{"role": "user", "content": secret_msg}],
                db=db_proxy,
            )
        ]

    _creds_cache.clear()
    # Local loopback Ollama stays unredacted even under Airplane Lock
    assert captured_messages[0]["content"] == secret_msg
    assert not any(e["type"] == "dlp_redacted" for e in events)


@pytest.mark.asyncio
async def test_model_dispatcher_airplane_lock_blocks_cloud_egress(db_proxy):
    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "dlp-ant-blocked",
        "provider_type": "anthropic",
        "display_name": "Anthropic",
        "config": {"api_key": "test-ant-key"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    from services import net_guard
    from services.model_dispatcher import stream_chat

    _creds_cache.clear()
    net_guard.set_airplane_lock(True)

    with pytest.raises(net_guard.EgressBlockedError):
        async for _ in stream_chat(
            "anthropic:claude-sonnet-4-20250514",
            [{"role": "user", "content": "hi"}],
            db=db_proxy,
        ):
            pass

    _creds_cache.clear()


@pytest.mark.asyncio
async def test_model_dispatcher_remote_openai_compat_redacts(db_proxy):
    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "dlp-compat-remote",
        "provider_type": "openai_compat",
        "display_name": "Remote Compat",
        "config": {"base_url": "https://openrouter.ai/api/v1", "api_key": "or-key"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    captured_messages: List[Dict[str, Any]] = []

    def _mock_stream(self_or_msgs, messages, *args, **kwargs):
        captured_messages.extend(messages)
        return _fake_provider_stream(["Remote OK"])

    with patch("services.openai_direct_service.OpenAIDirectService.stream_chat", new=_mock_stream):
        from services.model_dispatcher import stream_chat
        events = [
            evt
            async for evt in stream_chat(
                "openai_compat:meta-llama/llama-3.3-70b",
                [{"role": "user", "content": "SSN 123-45-6789"}],
                db=db_proxy,
            )
        ]

    _creds_cache.clear()
    assert captured_messages[0]["content"] == "SSN [REDACTED:SSN]"
    assert events[0]["type"] == "dlp_redacted"
    assert events[0]["summary"]["categories"] == ["ssns"]


@pytest.mark.asyncio
async def test_dlp_audit_events_recorded_without_raw_secrets(db_proxy):
    """Verify DLP_POLICY_UPDATED and DLP_REDACTED land in SQLite audit log with zero raw secrets."""
    from repositories.audit_repository import AuditRepository
    from routers.dlp import router as dlp_router

    app = FastAPI()
    app.include_router(dlp_router)
    client = TestClient(app)

    r_put = client.put("/api/v1/dlp/settings", json={"categories": {"emails": True}})
    assert r_put.status_code == 200

    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "dlp-google-audit",
        "provider_type": "google",
        "display_name": "Google",
        "config": {"api_key": "test-google-key"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    raw_secret = "sk-ant-api03-auditsecret1234567890"
    with patch(
        "services.google_direct_service.GoogleDirectService.stream_chat",
        return_value=_fake_provider_stream(["ok"]),
    ):
        from services.model_dispatcher import stream_chat
        events = [
            evt
            async for evt in stream_chat(
                "google:gemini-2.0-flash",
                [{"role": "user", "content": f"Check {raw_secret}"}],
                db=db_proxy,
            )
        ]

    _creds_cache.clear()
    assert events[0]["type"] == "dlp_redacted"

    repo = AuditRepository()
    audit_rows, total = await repo.query(page=1, page_size=20)
    assert total >= 2
    actions = {row["action"] for row in audit_rows}
    assert "dlp.policy.updated" in actions
    assert "dlp.redacted" in actions
    assert raw_secret not in json.dumps(audit_rows)
