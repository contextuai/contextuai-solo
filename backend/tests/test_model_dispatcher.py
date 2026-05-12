"""
Tests for services/model_dispatcher.py

Covers:
- Provider prefix parsing (_parse_provider)
- stream_chat routes correctly by prefix (all 5 cloud + local paths, mocked)
- ProviderUnavailable raised when key is missing
- __DEFAULT__ sentinel resolved via resolve_default_model
- resolve_default_model raises ProviderUnavailable when nothing is available
"""

from __future__ import annotations

import sys
import os
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helper: fake normalized stream
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
# _parse_provider unit tests
# ---------------------------------------------------------------------------

def test_parse_provider_anthropic():
    from services.model_dispatcher import _parse_provider
    provider, model = _parse_provider("anthropic:claude-sonnet-4-20250514")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-20250514"


def test_parse_provider_google():
    from services.model_dispatcher import _parse_provider
    provider, model = _parse_provider("google:gemini-2.0-flash")
    assert provider == "google"
    assert model == "gemini-2.0-flash"


def test_parse_provider_openai():
    from services.model_dispatcher import _parse_provider
    provider, model = _parse_provider("openai:gpt-4o")
    assert provider == "openai"
    assert model == "gpt-4o"


def test_parse_provider_bedrock():
    from services.model_dispatcher import _parse_provider
    provider, model = _parse_provider("bedrock:anthropic.claude-3-sonnet")
    assert provider == "bedrock"
    assert model == "anthropic.claude-3-sonnet"


def test_parse_provider_ollama():
    from services.model_dispatcher import _parse_provider
    provider, model = _parse_provider("ollama:qwen2.5:7b")
    assert provider == "ollama"
    assert model == "qwen2.5:7b"


def test_parse_provider_local_bare():
    from services.model_dispatcher import _parse_provider
    provider, model = _parse_provider("qwen2.5-coder-7b")
    assert provider == "local"
    assert model == "qwen2.5-coder-7b"


# ---------------------------------------------------------------------------
# stream_chat — Anthropic (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_anthropic_routes_correctly(db_proxy):
    """stream_chat routes anthropic: prefix to AnthropicDirectService."""
    # Seed a cloud_providers row for anthropic
    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "disp-ant-1",
        "provider_type": "anthropic",
        "display_name": "Test",
        "config": {"api_key": "test-key"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    events = []
    fake = _fake_stream(["Hello", " world"])
    with patch(
        "services.anthropic_direct_service.AnthropicDirectService.stream_chat",
        return_value=fake,
    ):
        from services.model_dispatcher import stream_chat
        async for evt in stream_chat(
            "anthropic:claude-sonnet-4-20250514",
            [{"role": "user", "content": "hi"}],
            db=db_proxy,
        ):
            events.append(evt)

    _creds_cache.clear()
    delta_events = [e for e in events if e["type"] == "delta"]
    done_events = [e for e in events if e["type"] == "done"]
    assert len(delta_events) == 2
    assert done_events[0]["finish_reason"] == "stop"


# ---------------------------------------------------------------------------
# stream_chat — Google (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_google_routes_correctly(db_proxy):
    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "disp-ggl-1",
        "provider_type": "google",
        "display_name": "Test",
        "config": {"api_key": "test-key-google"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    events = []
    fake = _fake_stream(["Hi"])
    with patch(
        "services.google_direct_service.GoogleDirectService.stream_chat",
        return_value=fake,
    ):
        from services.model_dispatcher import stream_chat
        async for evt in stream_chat(
            "google:gemini-2.0-flash",
            [{"role": "user", "content": "hi"}],
            db=db_proxy,
        ):
            events.append(evt)

    _creds_cache.clear()
    assert any(e["type"] == "delta" for e in events)
    assert any(e["type"] == "done" for e in events)


# ---------------------------------------------------------------------------
# stream_chat — OpenAI (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_openai_routes_correctly(db_proxy):
    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "disp-oai-1",
        "provider_type": "openai",
        "display_name": "Test",
        "config": {"api_key": "test-key-openai"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    events = []

    def _mock_stream_chat(self_or_messages, *args, **kwargs):
        return _fake_stream(["GPT", " here"])

    with patch(
        "services.openai_direct_service.OpenAIDirectService.stream_chat",
        new=_mock_stream_chat,
    ):
        from services.model_dispatcher import stream_chat
        async for evt in stream_chat(
            "openai:gpt-4o",
            [{"role": "user", "content": "hi"}],
            db=db_proxy,
        ):
            events.append(evt)

    _creds_cache.clear()
    delta_events = [e for e in events if e["type"] == "delta"]
    assert len(delta_events) == 2


# ---------------------------------------------------------------------------
# stream_chat — Ollama (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_ollama_routes_correctly(db_proxy):
    col = db_proxy["cloud_providers"]
    await col.insert_one({
        "_id": "disp-ollama-1",
        "provider_type": "ollama",
        "display_name": "Ollama local",
        "config": {"base_url": "http://localhost:11434"},
        "connected": False,
        "last_test_status": None,
    })

    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    events = []
    fake = _fake_stream(["Ollama", " reply"])
    with patch(
        "services.ollama_direct_service.OllamaDirectService.stream_chat",
        return_value=fake,
    ):
        from services.model_dispatcher import stream_chat
        async for evt in stream_chat(
            "ollama:qwen2.5:7b",
            [{"role": "user", "content": "hi"}],
            db=db_proxy,
        ):
            events.append(evt)

    _creds_cache.clear()
    assert any(e["type"] == "delta" for e in events)


# ---------------------------------------------------------------------------
# ProviderUnavailable — missing key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_provider_unavailable_when_key_missing(db_proxy):
    """stream_chat raises ProviderUnavailable when no credential exists."""
    from services.model_dispatcher import stream_chat, ProviderUnavailable
    from services.cloud_provider_service import _creds_cache
    _creds_cache.clear()

    # No anthropic row seeded — should raise.
    with pytest.raises(ProviderUnavailable, match="No saved credentials"):
        async for _ in stream_chat(
            "anthropic:claude-sonnet-4-20250514",
            [{"role": "user", "content": "hi"}],
            db=db_proxy,
        ):
            pass


# ---------------------------------------------------------------------------
# ProviderUnavailable — no db provided for cloud
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_provider_unavailable_when_db_none_for_cloud():
    from services.model_dispatcher import stream_chat, ProviderUnavailable

    with pytest.raises(ProviderUnavailable, match="db is required"):
        async for _ in stream_chat(
            "anthropic:claude-sonnet-4-20250514",
            [{"role": "user", "content": "hi"}],
            db=None,
        ):
            pass


# ---------------------------------------------------------------------------
# __DEFAULT__ resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_sentinel_resolves_to_first_installed_model(db_proxy):
    """__DEFAULT__ resolves to the first installed local model when no DB pref exists."""
    from services.model_dispatcher import resolve_default_model

    # DefaultModelService will return "" for local mode (no models in DB),
    # then model_manager.list_installed() is the fallback.
    fake_svc = MagicMock()
    fake_svc.get_ai_mode_preference = AsyncMock(return_value="local")
    fake_svc.get_default_model_id = AsyncMock(return_value="")

    fake_model_manager = MagicMock()
    fake_model_manager.list_installed.return_value = [{"id": "qwen2.5-coder-7b"}]

    with patch("services.default_model_service.DefaultModelService", return_value=fake_svc), \
         patch("services.model_manager.model_manager", fake_model_manager):
        result = await resolve_default_model(db_proxy)

    assert result == "qwen2.5-coder-7b"


@pytest.mark.asyncio
async def test_default_sentinel_raises_when_nothing_available(db_proxy):
    """resolve_default_model raises ProviderUnavailable when no model is found."""
    from services.model_dispatcher import resolve_default_model, ProviderUnavailable

    fake_svc = MagicMock()
    fake_svc.get_ai_mode_preference = AsyncMock(return_value="local")
    fake_svc.get_default_model_id = AsyncMock(return_value="")

    fake_model_manager = MagicMock()
    fake_model_manager.list_installed.return_value = []

    with patch("services.default_model_service.DefaultModelService", return_value=fake_svc), \
         patch("services.model_manager.model_manager", fake_model_manager):
        with pytest.raises(ProviderUnavailable, match="No model configured"):
            await resolve_default_model(db_proxy)
