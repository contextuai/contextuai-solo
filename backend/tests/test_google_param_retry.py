"""Adaptive param-drop retry for the Google direct service."""

import json

import pytest

from services.google_direct_service import (
    GoogleDirectService,
    _detect_google_param_fix,
)


def test_detect_drops_temperature_on_unsupported():
    fix = _detect_google_param_fix(
        "Temperature is not supported for this model",
        {"temperature": 0.7, "topP": 1.0},
    )
    assert fix == "drop_temperature"


def test_detect_drops_topp_on_invalid():
    fix = _detect_google_param_fix(
        "Invalid value for topP on this model",
        {"topP": 1.0},
    )
    assert fix == "drop_topP"


def test_detect_returns_none_when_param_absent():
    # error mentions temperature but body no longer carries it → nothing to drop
    assert _detect_google_param_fix("temperature unsupported", {"topP": 1.0}) is None


def test_detect_returns_none_on_unrelated_error():
    assert _detect_google_param_fix("quota exceeded", {"temperature": 0.7}) is None


class _Resp:
    """Minimal async streaming response stand-in for httpx."""

    def __init__(self, status_code, *, err=b"", lines=None):
        self.status_code = status_code
        self._err = err
        self._lines = lines or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def aread(self):
        return self._err

    async def aiter_lines(self):
        for ln in self._lines:
            yield ln


class _Client:
    """Fails the first N stream() calls with a 400, then serves a good stream.

    Records each request body so the test can assert temperature was dropped.
    """

    def __init__(self, fail_bodies, good_lines):
        self._fail_bodies = list(fail_bodies)
        self._good_lines = good_lines
        self.sent_bodies = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, params=None, json=None):
        # capture a deep-ish copy of generationConfig at call time
        self.sent_bodies.append(dict((json or {}).get("generationConfig") or {}))
        if self._fail_bodies:
            err = self._fail_bodies.pop(0)
            return _Resp(400, err=err)
        return _Resp(200, lines=self._good_lines)


class _UnaryResp:
    """Non-streaming httpx response stand-in for the generateContent fallback."""

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FallbackClient:
    """streamGenerateContent 403s (method-restricted key); post() serves unary."""

    def __init__(self, unary_payload):
        self._unary_payload = unary_payload
        self.stream_calls = 0
        self.post_calls = 0
        self.post_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, params=None, json=None):
        self.stream_calls += 1
        return _Resp(
            403,
            err=b'{"error":{"code":403,"message":"The caller does not have permission","status":"PERMISSION_DENIED"}}',
        )

    async def post(self, url, params=None, json=None):
        self.post_calls += 1
        self.post_urls.append(url)
        return _UnaryResp(200, self._unary_payload)


@pytest.mark.asyncio
async def test_stream_falls_back_to_unary_on_403(monkeypatch):
    """A streaming-403 (ephemeral/method-restricted key) falls back to unary."""
    unary_payload = {
        "candidates": [{
            "content": {"parts": [{"text": "GEMINI OK"}]},
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 3},
    }
    client = _FallbackClient(unary_payload)
    monkeypatch.setattr(
        "services.google_direct_service.httpx.AsyncClient", lambda *a, **k: client
    )

    svc = GoogleDirectService()
    events = []
    async for evt in svc.stream_chat(
        [{"role": "user", "content": "hey"}],
        model_id="google:gemini-2.5-flash",
        api_key="AQ.restricted",
        max_tokens=50,
    ):
        events.append(evt)

    assert client.stream_calls == 1          # streaming attempted
    assert client.post_calls == 1            # then unary fallback
    assert client.post_urls[0].endswith(":generateContent")
    assert {"type": "delta", "content": "GEMINI OK"} in events
    assert events[-1]["type"] == "done"
    assert events[-1]["finish_reason"] == "STOP"
    assert events[-1]["usage"]["total_tokens"] == 11


@pytest.mark.asyncio
async def test_stream_retries_after_dropping_temperature(monkeypatch):
    good_lines = [
        "data: " + json.dumps({
            "candidates": [{"content": {"parts": [{"text": "hi"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
        }),
    ]
    client = _Client(
        fail_bodies=[b'{"error":{"message":"Temperature is not supported for this model"}}'],
        good_lines=good_lines,
    )

    monkeypatch.setattr(
        "services.google_direct_service.httpx.AsyncClient", lambda *a, **k: client
    )

    svc = GoogleDirectService()
    events = []
    async for evt in svc.stream_chat(
        [{"role": "user", "content": "hey"}],
        model_id="google:gemini-2.5-pro",
        api_key="AIza-x",
        temperature=0.7,
        top_p=1.0,
    ):
        events.append(evt)

    # first attempt carried temperature; retry dropped it
    assert "temperature" in client.sent_bodies[0]
    assert "temperature" not in client.sent_bodies[1]
    # stream still produced content + a done event
    assert {"type": "delta", "content": "hi"} in events
    assert events[-1]["type"] == "done"
    assert events[-1]["usage"]["total_tokens"] == 4
