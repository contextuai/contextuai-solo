"""
Google Direct Service — call the Google Generative Language API directly.

Used by inference paths when the user has saved a Google AI / Gemini API key.
We use raw httpx rather than the ``google-genai`` SDK to avoid a new dep.

The model_id arrives prefixed with ``"google:"`` (e.g.
``"google:gemini-2.0-flash"``) — strip the prefix before sending.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

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
        """Stream tokens from the Google Gemini SSE endpoint.

        Yields normalized event dicts:
        - ``{"type": "delta", "content": "..."}``
        - ``{"type": "done", "finish_reason": "...", "usage": {...}}``
        """
        clean_model = model_id
        if clean_model.startswith("google:"):
            clean_model = clean_model[len("google:"):]

        # Split system message and convert roles.
        system_instruction: Optional[Dict[str, Any]] = None
        contents: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_instruction = {"parts": [{"text": content}]}
            else:
                # Google uses "model" instead of "assistant"
                google_role = "model" if role == "assistant" else "user"
                contents.append({"role": google_role, "parts": [{"text": content}]})

        url = f"{GOOGLE_API_BASE}/{clean_model}:streamGenerateContent"
        params = {"alt": "sse", "key": api_key}

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
                "topP": top_p,
            },
        }
        if system_instruction:
            body["systemInstruction"] = system_instruction
        if stop:
            body["generationConfig"]["stopSequences"] = stop

        input_tokens = 0
        output_tokens = 0
        finish_reason = "stop"

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS * 2) as client:
            async with client.stream("POST", url, params=params, json=body) as resp:
                if resp.status_code < 200 or resp.status_code >= 300:
                    body_text = await resp.aread()
                    raise RuntimeError(
                        f"Google stream failed: HTTP {resp.status_code} {body_text[:500].decode(errors='replace')}"
                    )
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    candidates = evt.get("candidates") or []
                    if candidates:
                        first = candidates[0] or {}
                        finish_reason = first.get("finishReason") or finish_reason
                        parts = (first.get("content") or {}).get("parts") or []
                        for part in parts:
                            text = part.get("text") or ""
                            if text:
                                yield {"type": "delta", "content": text}

                    usage = evt.get("usageMetadata") or {}
                    if usage:
                        input_tokens = int(usage.get("promptTokenCount") or input_tokens)
                        output_tokens = int(usage.get("candidatesTokenCount") or output_tokens)

        yield {
            "type": "done",
            "finish_reason": finish_reason,
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }
