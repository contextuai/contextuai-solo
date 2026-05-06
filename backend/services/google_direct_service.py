"""
Google Direct Service — call the Google Generative Language API directly.

Used by inference paths when the user has saved a Google AI / Gemini API key.
We use raw httpx rather than the ``google-genai`` SDK to avoid a new dep.

The model_id arrives prefixed with ``"google:"`` (e.g.
``"google:gemini-2.0-flash"``) — strip the prefix before sending.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_TIMEOUT_SECONDS = 60.0


class GoogleDirectService:
    """Thin async client for the Google generateContent endpoint."""

    async def call_model(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model_id: str = "gemini-2.0-flash",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not api_key:
            raise RuntimeError(
                "Google AI API key not configured. "
                "Save one in Settings → Models → Cloud."
            )

        clean_model = model_id
        if clean_model.startswith("google:"):
            clean_model = clean_model[len("google:"):]

        url = f"{GOOGLE_API_BASE}/{clean_model}:generateContent"
        params = {"key": api_key}
        body: Dict[str, Any] = {
            "contents": [
                {"parts": [{"text": prompt}]},
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, params=params, json=body)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Google API call failed: {exc}") from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            body_text = ""
            try:
                body_text = resp.text
            except Exception:
                pass
            raise RuntimeError(
                f"Google API call failed: HTTP {resp.status_code} {body_text[:500]}"
            )

        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"Google API call failed: invalid JSON response — {exc}"
            ) from exc

        text = ""
        stop_reason = None
        candidates = data.get("candidates") or []
        if candidates:
            first = candidates[0] or {}
            stop_reason = first.get("finishReason")
            content = first.get("content") or {}
            parts = content.get("parts") or []
            text_parts = []
            for part in parts:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(part.get("text") or "")
            text = "".join(text_parts)

        usage = data.get("usageMetadata") or {}
        input_tokens = int(usage.get("promptTokenCount") or 0)
        output_tokens = int(usage.get("candidatesTokenCount") or 0)
        total_tokens = int(usage.get("totalTokenCount") or (input_tokens + output_tokens))

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
