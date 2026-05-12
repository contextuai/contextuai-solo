"""
Tests for the OpenAI-compat /v1 dispatcher.

Covers:
- Provider prefix parsing (_parse_provider helper)
- POST /v1/chat/completions: non-streaming cloud paths (mocked upstream)
- POST /v1/chat/completions: streaming cloud path (mocked upstream)
- System message forwarded to Google systemInstruction
- Missing API key → 401
- Bare model name still routes through local path (mock _resolve_model_and_load)
- GET /v1/models returns cloud-prefixed entries when keys are saved

All upstream HTTP calls are mocked via unittest.mock so no real API calls
are made.  The cloud_providers collection is seeded with fake rows.
"""

from __future__ import annotations

import json
import sys
import os
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helper: fake normalized stream from a provider service
# ---------------------------------------------------------------------------

async def _fake_stream(tokens: list[str], finish_reason: str = "stop") -> AsyncIterator[dict]:
    for tok in tokens:
        yield {"type": "delta", "content": tok}
    yield {
        "type": "done",
        "finish_reason": finish_reason,
        "usage": {"prompt_tokens": 5, "completion_tokens": len(tokens), "total_tokens": 5 + len(tokens)},
    }


# ---------------------------------------------------------------------------
# _parse_provider unit tests (pure, no fixtures needed)
# ---------------------------------------------------------------------------

def test_parse_provider_anthropic():
    from routers.openai_compat import _parse_provider
    provider, model = _parse_provider("anthropic:claude-sonnet-4-20250514")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-20250514"


def test_parse_provider_google():
    from routers.openai_compat import _parse_provider
    provider, model = _parse_provider("google:gemini-2.0-flash")
    assert provider == "google"
    assert model == "gemini-2.0-flash"


def test_parse_provider_openai():
    from routers.openai_compat import _parse_provider
    provider, model = _parse_provider("openai:gpt-4o")
    assert provider == "openai"
    assert model == "gpt-4o"


def test_parse_provider_bedrock():
    from routers.openai_compat import _parse_provider
    provider, model = _parse_provider("bedrock:anthropic.claude-3-sonnet")
    assert provider == "bedrock"
    assert model == "anthropic.claude-3-sonnet"


def test_parse_provider_ollama():
    from routers.openai_compat import _parse_provider
    provider, model = _parse_provider("ollama:qwen2.5:7b")
    assert provider == "ollama"
    assert model == "qwen2.5:7b"


def test_parse_provider_local_bare():
    from routers.openai_compat import _parse_provider
    provider, model = _parse_provider("qwen2.5-coder-7b")
    assert provider == "local"
    assert model == "qwen2.5-coder-7b"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_app_with_cloud_key(db_proxy):
    """TestClient with a fake Anthropic key seeded into cloud_providers."""
    from fastapi.testclient import TestClient
    import database
    from app import app
    from database import get_db, get_database
    from services.auth_service import get_current_user, get_current_user_optional

    _USER = {
        "user_id": "test-user",
        "email": "test@test.local",
        "role": "admin",
        "organization": "solo",
        "department": None,
        "auth_type": "desktop",
        "scopes": ["*"],
    }

    async def _get_db():
        return db_proxy

    async def _get_user():
        return _USER

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_database] = _get_db
    app.dependency_overrides[get_current_user] = _get_user
    app.dependency_overrides[get_current_user_optional] = _get_user

    client = TestClient(app)

    async def _get_database():
        return db_proxy

    database.get_database = _get_database
    database.get_db = _get_database
    database._async_db = db_proxy
    app.state.db = db_proxy

    yield client

    database._async_db = None
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — non-streaming, Anthropic
# ---------------------------------------------------------------------------

def test_anthropic_non_stream_returns_chat_completion(test_app_with_cloud_key, db_proxy):
    """non-streaming anthropic: model returns chat.completion envelope."""
    async def _seed():
        col = db_proxy["cloud_providers"]
        await col.insert_one({
            "_id": "test-ant-1",
            "provider_type": "anthropic",
            "display_name": "Test",
            "config": {"api_key": "test-key-ant"},
            "connected": False,
            "last_test_status": None,
        })

    import asyncio
    asyncio.get_event_loop().run_until_complete(_seed())

    # Invalidate creds cache so fresh key is picked up
    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    fake_iter = _fake_stream(["Hello", " world"])

    with patch(
        "services.anthropic_direct_service.AnthropicDirectService.stream_chat",
        return_value=fake_iter,
    ):
        resp = test_app_with_cloud_key.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic:claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "anthropic:claude-sonnet-4-20250514"
    assert body["choices"][0]["message"]["content"] == "Hello world"

    # Cleanup
    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — streaming, OpenAI
# ---------------------------------------------------------------------------

def test_openai_stream_returns_sse_done(test_app_with_cloud_key, db_proxy):
    """streaming openai: model yields SSE chunks ending in data: [DONE]."""
    async def _seed():
        col = db_proxy["cloud_providers"]
        await col.insert_one({
            "_id": "test-oai-1",
            "provider_type": "openai",
            "display_name": "Test",
            "config": {"api_key": "test-key-oai"},
            "connected": False,
            "last_test_status": None,
        })

    import asyncio
    asyncio.get_event_loop().run_until_complete(_seed())

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    # stream_chat is an async generator — mock it as a regular method returning one
    def _mock_stream_chat(self_or_messages, *args, **kwargs):
        return _fake_stream(["Hi", " there"])

    with patch(
        "services.openai_direct_service.OpenAIDirectService.stream_chat",
        new=_mock_stream_chat,
    ):
        resp = test_app_with_cloud_key.post(
            "/v1/chat/completions",
            json={
                "model": "openai:gpt-4o",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        )

    assert resp.status_code == 200
    raw = resp.text
    assert "data: [DONE]" in raw
    # At least one delta chunk
    lines = [ln for ln in raw.splitlines() if ln.startswith("data:") and "[DONE]" not in ln]
    assert len(lines) >= 1
    parsed = json.loads(lines[0][5:])
    assert parsed["object"] == "chat.completion.chunk"

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()


# ---------------------------------------------------------------------------
# Google system message → systemInstruction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_google_system_message_forwarded():
    """stream_chat() splits the system message into systemInstruction."""
    import httpx
    from services.google_direct_service import GoogleDirectService

    captured_body: dict = {}

    _sse_lines = [
        'data: {"candidates":[{"content":{"parts":[{"text":"hi"}]},"finishReason":"STOP"}]}',
    ]

    class _FakeGoogleResp:
        status_code = 200

        async def aread(self):
            return b""

        async def aiter_lines(self):
            for line in _sse_lines:
                yield line

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

    def _capturing_stream(self, method, url, **kwargs):
        nonlocal captured_body
        captured_body = kwargs.get("json", {})
        return _FakeGoogleResp()

    svc = GoogleDirectService()
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "hello"},
    ]

    with patch.object(httpx.AsyncClient, "stream", _capturing_stream):
        events = []
        async for evt in svc.stream_chat(
            messages,
            model_id="google:gemini-2.0-flash",
            api_key="test-key",
        ):
            events.append(evt)

    # systemInstruction must be present and NOT in contents
    assert "systemInstruction" in captured_body
    assert captured_body["systemInstruction"]["parts"][0]["text"] == "You are helpful."
    for msg in captured_body.get("contents", []):
        assert msg.get("role") != "system"


# ---------------------------------------------------------------------------
# Missing API key → 401
# ---------------------------------------------------------------------------

def test_missing_api_key_returns_401(test_app_with_cloud_key):
    """Missing key for a cloud provider returns 401."""
    # No cloud_providers row exists for "google" in this client's db
    # (the db is fresh per fixture; only anthropic and openai rows were seeded
    # in the other tests — each test gets its own db_proxy)
    resp = test_app_with_cloud_key.post(
        "/v1/chat/completions",
        json={
            "model": "google:gemini-2.0-flash",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Bare model → local path (mock _resolve_model_and_load)
# ---------------------------------------------------------------------------

def test_bare_model_routes_local(test_app_with_cloud_key):
    """A bare model name (no prefix) routes to the local llama-cpp path."""
    fake_llm = MagicMock()
    fake_llm.create_chat_completion.return_value = {
        "id": "cmpl-x",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen2.5-coder-7b",
        "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
        "usage": {},
    }

    with patch(
        "routers.openai_compat._resolve_model_and_load",
        return_value=(fake_llm, {"id": "qwen2.5-coder-7b"}),
    ):
        resp = test_app_with_cloud_key.post(
            "/v1/chat/completions",
            json={
                "model": "qwen2.5-coder-7b",
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["choices"][0]["message"]["content"] == "pong"


# ---------------------------------------------------------------------------
# GET /v1/models — cloud entries present when key is saved
# ---------------------------------------------------------------------------

def test_list_models_includes_cloud_entries(test_app_with_cloud_key, db_proxy):
    """GET /v1/models returns anthropic: entries when a key is saved."""
    async def _seed():
        col = db_proxy["cloud_providers"]
        await col.insert_one({
            "_id": "test-ant-models",
            "provider_type": "anthropic",
            "display_name": "Test Anthropic",
            "config": {"api_key": "test-key-models"},
            "connected": False,
            "last_test_status": None,
        })

    import asyncio
    asyncio.get_event_loop().run_until_complete(_seed())

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    # Ollama unreachable — should not break the endpoint
    with patch(
        "services.ollama_direct_service.OllamaDirectService.list_models",
        side_effect=Exception("unreachable"),
    ):
        resp = test_app_with_cloud_key.get("/v1/models")

    assert resp.status_code == 200
    ids = {m["id"] for m in resp.json()["data"]}
    assert any(mid.startswith("anthropic:") for mid in ids), f"No anthropic entries in {ids}"

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()
