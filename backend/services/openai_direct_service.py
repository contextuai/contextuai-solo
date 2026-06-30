"""
OpenAI Direct Service — call the OpenAI Chat Completions API directly.

Used by inference paths when the user has saved an OpenAI API key. The
model_id arrives prefixed with ``"openai:"`` (e.g. ``"openai:gpt-4o"``)
— strip the prefix before sending.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENAI_API_URL = f"{DEFAULT_BASE_URL}/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 60.0


def _chat_url(base_url: Optional[str]) -> str:
    """Resolve the chat-completions endpoint from a ``/v1`` base URL.

    Defaults to OpenAI. A custom OpenAI-compatible server (vLLM, LM Studio,
    llama.cpp server, TGI, Ollama's ``/v1``, …) passes its own base URL.
    """
    return f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/chat/completions"


def _is_openai_host(base_url: Optional[str]) -> bool:
    """True when talking to OpenAI itself (not a custom compatible server)."""
    return base_url is None or "api.openai.com" in base_url


def _token_limit_field(base_url: Optional[str]) -> str:
    """OpenAI's newer models (gpt-5.x, o-series) reject ``max_tokens`` and
    require ``max_completion_tokens``; it's accepted by their older models too.
    OpenAI-compatible servers (Ollama/vLLM/LM Studio/TGI) still expect the
    classic ``max_tokens``.
    """
    return "max_completion_tokens" if _is_openai_host(base_url) else "max_tokens"


def _is_reasoning_model(clean_model: str) -> bool:
    """OpenAI reasoning / gpt-5 models only accept default sampling params."""
    m = clean_model.lower()
    return m.startswith(("o1", "o3", "o4", "gpt-5"))


def _sampling_params(
    base_url: Optional[str], clean_model: str, temperature: float, top_p: Optional[float]
) -> Dict[str, Any]:
    """Sampling params that the target model accepts.

    OpenAI reasoning/gpt-5 models reject non-default ``temperature``/``top_p``
    (HTTP 400), so omit them and let the API use its defaults. Everything else
    (gpt-4o, and all OpenAI-compatible servers) takes them as usual.
    """
    if _is_openai_host(base_url) and _is_reasoning_model(clean_model):
        return {}
    params: Dict[str, Any] = {"temperature": temperature}
    if top_p is not None:
        params["top_p"] = top_p
    return params


def _strip_provider_prefix(model_id: str) -> str:
    for prefix in ("openai_compat:", "openai:"):
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


_STATUS_HINTS = {
    401: "invalid or missing API key",
    403: "access denied for this model/key",
    404: "model not found or no access",
    429: "rate limit or quota exceeded — check your plan/billing",
}


def _friendly_error(status_code: int, raw_body: bytes | str) -> str:
    """Turn an OpenAI(-compatible) error response into a readable message."""
    text = raw_body.decode(errors="replace") if isinstance(raw_body, bytes) else (raw_body or "")
    detail = ""
    try:
        body = json.loads(text)
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            detail = str(err.get("message") or "")
        elif isinstance(err, str):
            detail = err
    except Exception:
        detail = text[:200]
    hint = _STATUS_HINTS.get(status_code)
    parts = [f"HTTP {status_code}"]
    if hint:
        parts.append(hint)
    msg = " — ".join(parts)
    if detail:
        msg = f"{msg}: {detail}"
    return msg


class OpenAIDirectService:
    """Thin async client for the OpenAI (or OpenAI-compatible) Chat API."""

    async def call_model(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model_id: str = "gpt-4o",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        # api_key is optional for OpenAI-compatible servers (often keyless).
        clean_model = _strip_provider_prefix(model_id)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body: Dict[str, Any] = {
            "model": clean_model,
            "messages": messages,
            _token_limit_field(base_url): max_tokens,
            **_sampling_params(base_url, clean_model, temperature, None),
        }

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    _chat_url(base_url), headers=headers, json=body
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OpenAI API call failed: {exc}") from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            body_text = ""
            try:
                body_text = resp.text
            except Exception:
                pass
            raise RuntimeError(f"OpenAI: {_friendly_error(resp.status_code, body_text)}")

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"OpenAI API call failed: invalid JSON response — {exc}"
            ) from exc

        choices = data.get("choices") or []
        text = ""
        stop_reason = None
        if choices:
            first = choices[0] or {}
            msg = first.get("message") or {}
            text = msg.get("content") or ""
            stop_reason = first.get("finish_reason")

        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))

        return {
            "content": text,
            "model_id": model_id,
            "tokens_used": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "stop_reason": stop_reason,
        }

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model_id: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream tokens from an OpenAI(-compatible) Chat Completions SSE endpoint.

        ``api_key`` is optional (OpenAI-compatible servers are often keyless);
        ``base_url`` defaults to OpenAI. Yields normalized event dicts:
        - ``{"type": "delta", "content": "..."}``
        - ``{"type": "done", "finish_reason": "...", "usage": {...}}``
        """
        clean_model = _strip_provider_prefix(model_id)

        # Pass messages as-is — OpenAI format already matches.
        openai_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body: Dict[str, Any] = {
            "model": clean_model,
            "messages": openai_messages,
            _token_limit_field(base_url): max_tokens,
            **_sampling_params(base_url, clean_model, temperature, top_p),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if stop:
            body["stop"] = stop

        finish_reason = "stop"
        input_tokens = 0
        output_tokens = 0

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS * 2) as client:
            async with client.stream("POST", _chat_url(base_url), headers=headers, json=body) as resp:
                if resp.status_code < 200 or resp.status_code >= 300:
                    body_text = await resp.aread()
                    raise RuntimeError(f"OpenAI: {_friendly_error(resp.status_code, body_text)}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    # Usage chunk (stream_options)
                    usage = evt.get("usage")
                    if usage:
                        input_tokens = int(usage.get("prompt_tokens") or 0)
                        output_tokens = int(usage.get("completion_tokens") or 0)

                    choices = evt.get("choices") or []
                    if choices:
                        first = choices[0] or {}
                        finish_reason = first.get("finish_reason") or finish_reason
                        delta = first.get("delta") or {}
                        text = delta.get("content") or ""
                        if text:
                            yield {"type": "delta", "content": text}

        yield {
            "type": "done",
            "finish_reason": finish_reason,
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }
