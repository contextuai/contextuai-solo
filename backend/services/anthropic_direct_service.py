"""
Anthropic Direct Service — call the Anthropic Messages API directly.

Used by inference paths (automation_executor, chat) when the user has saved
an Anthropic API key under Settings -> Models -> Cloud. Bypasses Bedrock and
talks to ``https://api.anthropic.com/v1/messages``.

The model_id arrives prefixed with ``"anthropic:"`` (e.g.
``"anthropic:claude-sonnet-4-6"``) — strip the prefix before sending.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TIMEOUT_SECONDS = 60.0


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
