"""
OpenAI Direct Service — call the OpenAI Chat Completions API directly.

Used by inference paths when the user has saved an OpenAI API key. The
model_id arrives prefixed with ``"openai:"`` (e.g. ``"openai:gpt-4o"``)
— strip the prefix before sending.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

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
