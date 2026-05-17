"""
Tests for OllamaDirectService.

Mocks the Ollama HTTP server so no real server is required.
Covers:
- stream_chat() yields delta events and a final done event
- stream_chat() strips the "ollama:" prefix before sending
- list_models() parses the /api/tags response
- list_models() raises on HTTP error
"""

from __future__ import annotations

import json
import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers — fake NDJSON stream
# ---------------------------------------------------------------------------

def _ndjson(*objs: dict) -> bytes:
    return b"\n".join(json.dumps(o).encode() for o in objs) + b"\n"


FAKE_STREAM_LINES = [
    {"message": {"role": "assistant", "content": "Hello"}, "done": False},
    {"message": {"role": "assistant", "content": " world"}, "done": False},
    {"done": True, "prompt_eval_count": 5, "eval_count": 2},
]


class _FakeLine:
    def __init__(self, lines: list[str]):
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration


class _FakeStreamResponse:
    status_code = 200

    def __init__(self, lines: list[str]):
        self._lines = lines

    async def aread(self):
        return b""

    def aiter_lines(self):
        return _FakeLine(self._lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class _FakeTagsResponse:
    status_code = 200

    def __init__(self, data: dict):
        self._data = data

    def json(self):
        return self._data


# ---------------------------------------------------------------------------
# stream_chat tests
# ---------------------------------------------------------------------------

def _make_stream_mock(fake_resp: _FakeStreamResponse):
    """Return a MagicMock that acts as ``httpx.AsyncClient.stream`` context manager."""
    m = MagicMock()
    m.return_value = fake_resp
    # httpx.AsyncClient.stream is used as: async with client.stream(...) as r
    # So the mock's __call__ must return an async context manager.
    # We reuse fake_resp itself which implements __aenter__/__aexit__.
    m.return_value = fake_resp
    return m


@pytest.mark.asyncio
async def test_stream_chat_yields_deltas():
    """stream_chat() yields delta events for each non-done line."""
    import httpx
    from services.ollama_direct_service import OllamaDirectService

    lines = [json.dumps(obj) for obj in FAKE_STREAM_LINES]
    fake_resp = _FakeStreamResponse(lines)

    svc = OllamaDirectService()
    with patch.object(httpx.AsyncClient, "stream", return_value=fake_resp):
        events = []
        async for evt in svc.stream_chat(
            [{"role": "user", "content": "hi"}],
            model_id="qwen2.5:7b",
        ):
            events.append(evt)

    deltas = [e for e in events if e["type"] == "delta"]
    done = [e for e in events if e["type"] == "done"]

    assert len(deltas) == 2
    assert deltas[0]["content"] == "Hello"
    assert deltas[1]["content"] == " world"
    assert len(done) == 1
    assert done[0]["finish_reason"] == "stop"
    assert done[0]["usage"]["prompt_tokens"] == 5
    assert done[0]["usage"]["completion_tokens"] == 2


@pytest.mark.asyncio
async def test_stream_chat_strips_ollama_prefix():
    """stream_chat() strips 'ollama:' before sending model name."""
    import httpx
    from services.ollama_direct_service import OllamaDirectService

    captured_body: dict = {}
    lines = [json.dumps(FAKE_STREAM_LINES[-1])]  # just done
    fake_resp = _FakeStreamResponse(lines)

    original_stream = httpx.AsyncClient.stream

    def _capturing_stream(self, method, url, **kwargs):
        nonlocal captured_body
        captured_body = kwargs.get("json", {})
        return fake_resp

    svc = OllamaDirectService()
    with patch.object(httpx.AsyncClient, "stream", _capturing_stream):
        async for _ in svc.stream_chat(
            [{"role": "user", "content": "hi"}],
            model_id="ollama:qwen2.5:7b",
        ):
            pass

    # Model name sent to Ollama must not contain the "ollama:" prefix
    assert captured_body.get("model") == "qwen2.5:7b"


@pytest.mark.asyncio
async def test_stream_chat_uses_custom_base_url():
    """stream_chat() uses the provided base_url when given."""
    import httpx
    from services.ollama_direct_service import OllamaDirectService

    captured_url: str = ""
    lines = [json.dumps(FAKE_STREAM_LINES[-1])]
    fake_resp = _FakeStreamResponse(lines)

    def _capturing_stream(self, method, url, **kwargs):
        nonlocal captured_url
        captured_url = url
        return fake_resp

    svc = OllamaDirectService()
    with patch.object(httpx.AsyncClient, "stream", _capturing_stream):
        async for _ in svc.stream_chat(
            [{"role": "user", "content": "hi"}],
            model_id="llama3",
            base_url="http://192.168.1.100:11434",
        ):
            pass

    assert captured_url.startswith("http://192.168.1.100:11434")


# ---------------------------------------------------------------------------
# list_models tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_models_parses_tags():
    """list_models() returns the models array from /api/tags."""
    import httpx
    from services.ollama_direct_service import OllamaDirectService

    payload = {
        "models": [
            {"name": "qwen2.5:7b", "size": 4000000000},
            {"name": "llama3:8b", "size": 5000000000},
        ]
    }

    async def _mock_get(url, **kwargs):
        return _FakeTagsResponse(payload)

    svc = OllamaDirectService()
    with patch.object(httpx.AsyncClient, "get", side_effect=_mock_get):
        result = await svc.list_models()

    assert len(result) == 2
    assert result[0]["name"] == "qwen2.5:7b"
    assert result[1]["name"] == "llama3:8b"


@pytest.mark.asyncio
async def test_list_models_raises_on_error():
    """list_models() raises RuntimeError on non-2xx response."""
    import httpx
    from services.ollama_direct_service import OllamaDirectService

    class _ErrResp:
        status_code = 500
        text = "Internal Server Error"

        def json(self):
            return {}

    async def _mock_get(url, **kwargs):
        return _ErrResp()

    svc = OllamaDirectService()
    with patch.object(httpx.AsyncClient, "get", side_effect=_mock_get):
        with pytest.raises(RuntimeError, match="Ollama /api/tags failed"):
            await svc.list_models()
