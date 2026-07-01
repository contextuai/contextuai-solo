"""
Anthropic Direct Service — call the Anthropic Messages API directly.

Used by inference paths (automation_executor, chat) when the user has saved
an Anthropic API key under Settings -> Models -> Cloud. Bypasses Bedrock and
talks to ``https://api.anthropic.com/v1/messages``.

The model_id arrives prefixed with ``"anthropic:"`` (e.g.
``"anthropic:claude-sonnet-4-6"``) — strip the prefix before sending.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TIMEOUT_SECONDS = 60.0
_MAX_PARAM_RETRIES = 3


def _detect_anthropic_param_fix(error_text: str, body: dict) -> Optional[str]:
    """Detect a param incompatibility we can adapt to and retry.

    Claude models differ on sampling params: some reject temperature+top_p
    together ("use only one"), and the newest (e.g. sonnet-5) deprecate
    temperature entirely. Adapt at runtime instead of hardcoding per-model.
    """
    t = error_text.lower()
    if "temperature" in t and "temperature" in body and (
        "deprecat" in t or "not supported" in t or "unsupported" in t
        or "cannot both" in t or "only one" in t
    ):
        return "drop_temperature"
    if "top_p" in t and "top_p" in body and (
        "deprecat" in t or "not supported" in t or "unsupported" in t
        or "cannot both" in t or "only one" in t
    ):
        return "drop_top_p"
    return None


class AnthropicDirectService:
    """Thin async client for the Anthropic Messages API."""

    async def call_model(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model_id: str = "claude-sonnet-4-6",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not api_key:
            raise RuntimeError(
                "Anthropic API key not configured. "
                "Save one in Settings → Models → Cloud."
            )

        # Strip the "anthropic:" namespace before sending to Anthropic.
        clean_model = model_id
        if clean_model.startswith("anthropic:"):
            clean_model = clean_model[len("anthropic:"):]

        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body: Dict[str, Any] = {
            "model": clean_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    ANTHROPIC_API_URL, headers=headers, json=body
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Anthropic API call failed: {exc}") from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            body_text = ""
            try:
                body_text = resp.text
            except Exception:
                pass
            raise RuntimeError(
                f"Anthropic API call failed: HTTP {resp.status_code} {body_text[:500]}"
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"Anthropic API call failed: invalid JSON response — {exc}"
            ) from exc

        # content is a list of blocks; concatenate text blocks.
        content_blocks = data.get("content") or []
        text_parts = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        text = "".join(text_parts)

        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)

        return {
            "content": text,
            "model_id": model_id,
            "tokens_used": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            "stop_reason": data.get("stop_reason"),
        }

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model_id: str,
        api_key: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream tokens from the Anthropic Messages SSE API.

        Yields normalized event dicts:
        - ``{"type": "delta", "content": "..."}``
        - ``{"type": "done", "finish_reason": "...", "usage": {...}}``
        """
        clean_model = model_id
        if clean_model.startswith("anthropic:"):
            clean_model = clean_model[len("anthropic:"):]

        # Split system message from the conversation.
        system_text: Optional[str] = None
        user_messages: List[Dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_text = msg.get("content", "")
            else:
                user_messages.append({"role": msg["role"], "content": msg["content"]})

        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        # Anthropic rejects temperature + top_p together ("use only one") on
        # newer models — send just temperature (the primary control).
        body: Dict[str, Any] = {
            "model": clean_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "messages": user_messages,
        }
        if system_text is not None:
            body["system"] = system_text
        if stop:
            body["stop_sequences"] = stop

        input_tokens = 0
        output_tokens = 0
        finish_reason = "stop"

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS * 2) as client:
            attempt = 0
            while True:
                async with client.stream("POST", ANTHROPIC_API_URL, headers=headers, json=body) as resp:
                    if resp.status_code < 200 or resp.status_code >= 300:
                        err_body = await resp.aread()
                        fix = (
                            _detect_anthropic_param_fix(err_body.decode(errors="replace"), body)
                            if attempt < _MAX_PARAM_RETRIES
                            else None
                        )
                        if fix:
                            body.pop("temperature" if fix == "drop_temperature" else "top_p", None)
                            attempt += 1
                            continue  # retry with adjusted params
                        raise RuntimeError(
                            f"Anthropic stream failed: HTTP {resp.status_code} "
                            f"{err_body[:500].decode(errors='replace')}"
                        )
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

                        evt_type = evt.get("type", "")
                        if evt_type == "message_start":
                            usage = evt.get("message", {}).get("usage") or {}
                            input_tokens = int(usage.get("input_tokens") or 0)
                        elif evt_type == "content_block_delta":
                            delta = evt.get("delta") or {}
                            if delta.get("type") == "text_delta":
                                text = delta.get("text") or ""
                                if text:
                                    yield {"type": "delta", "content": text}
                        elif evt_type == "message_delta":
                            usage = evt.get("usage") or {}
                            output_tokens = int(usage.get("output_tokens") or 0)
                            finish_reason = evt.get("delta", {}).get("stop_reason") or "stop"
                        elif evt_type == "message_stop":
                            break
                break  # streamed successfully

        yield {
            "type": "done",
            "finish_reason": finish_reason,
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }
