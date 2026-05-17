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

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 60.0


class OpenAIDirectService:
    """Thin async client for the OpenAI Chat Completions API."""

    async def call_model(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model_id: str = "gpt-4o",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not api_key:
            raise RuntimeError(
                "OpenAI API key not configured. "
                "Save one in Settings → Models → Cloud."
            )

        clean_model = model_id
        if clean_model.startswith("openai:"):
            clean_model = clean_model[len("openai:"):]

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "model": clean_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    OPENAI_API_URL, headers=headers, json=body
                )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OpenAI API call failed: {exc}") from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            body_text = ""
            try:
                body_text = resp.text
            except Exception:
                pass
            raise RuntimeError(
                f"OpenAI API call failed: HTTP {resp.status_code} {body_text[:500]}"
            )

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
        api_key: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream tokens from the OpenAI Chat Completions SSE endpoint.

        Yields normalized event dicts:
        - ``{"type": "delta", "content": "..."}``
        - ``{"type": "done", "finish_reason": "...", "usage": {...}}``
        """
        clean_model = model_id
        if clean_model.startswith("openai:"):
            clean_model = clean_model[len("openai:"):]

        # Pass messages as-is — OpenAI format already matches.
        openai_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "model": clean_model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if stop:
            body["stop"] = stop

        finish_reason = "stop"
        input_tokens = 0
        output_tokens = 0

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS * 2) as client:
            async with client.stream("POST", OPENAI_API_URL, headers=headers, json=body) as resp:
                if resp.status_code < 200 or resp.status_code >= 300:
                    body_text = await resp.aread()
                    raise RuntimeError(
                        f"OpenAI stream failed: HTTP {resp.status_code} {body_text[:500].decode(errors='replace')}"
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
