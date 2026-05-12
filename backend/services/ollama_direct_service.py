"""
Ollama Direct Service — stream chat completions from a local Ollama server.

Ollama exposes an OpenAI-compatible endpoint AND a native ``/api/chat``
endpoint.  We use the native endpoint here because it gives us richer
per-token metadata (token counts, eval stats) in the final "done" event.

Protocol: NDJSON streaming — one JSON object per line.
- Mid-stream line: ``{"message": {"role": "assistant", "content": "..."}, "done": false}``
- Final line:       ``{"done": true, "prompt_eval_count": N, "eval_count": M}``

Emits the same normalized event shape as the other direct services:
- ``{"type": "delta", "content": "..."}``
- ``{"type": "done", "finish_reason": "stop", "usage": {...}}``
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT_SECONDS = 120.0


class OllamaDirectService:
    """Thin async client for a local Ollama server."""

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        model_id: str,
        base_url: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream tokens from the Ollama ``/api/chat`` endpoint.

        Yields normalized event dicts:
        - ``{"type": "delta", "content": "..."}``
        - ``{"type": "done", "finish_reason": "stop", "usage": {...}}``
        """
        server = (base_url or DEFAULT_BASE_URL).rstrip("/")

        clean_model = model_id
        if clean_model.startswith("ollama:"):
            clean_model = clean_model[len("ollama:"):]

        # Convert messages list — Ollama accepts the same role names.
        ollama_messages = [
            {"role": m["role"], "content": m["content"]} for m in messages
        ]

        body: Dict[str, Any] = {
            "model": clean_model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            },
        }
        if stop:
            body["options"]["stop"] = stop

        url = f"{server}/api/chat"
        input_tokens = 0
        output_tokens = 0

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            async with client.stream("POST", url, json=body) as resp:
                if resp.status_code < 200 or resp.status_code >= 300:
                    body_text = await resp.aread()
                    raise RuntimeError(
                        f"Ollama stream failed: HTTP {resp.status_code} "
                        f"{body_text[:500].decode(errors='replace')}"
                    )

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if evt.get("done"):
                        input_tokens = int(evt.get("prompt_eval_count") or 0)
                        output_tokens = int(evt.get("eval_count") or 0)
                        break

                    msg = evt.get("message") or {}
                    text = msg.get("content") or ""
                    if text:
                        yield {"type": "delta", "content": text}

        yield {
            "type": "done",
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }

    async def list_models(self, base_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return the list of models pulled locally in Ollama.

        GET ``{base_url}/api/tags`` → ``{"models": [{"name": "qwen2.5:7b", ...}]}``

        Returns a list of dicts with at least ``name`` and ``size`` keys.
        Raises ``RuntimeError`` on connectivity failure.
        """
        server = (base_url or DEFAULT_BASE_URL).rstrip("/")
        url = f"{server}/api/tags"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)

        if resp.status_code < 200 or resp.status_code >= 300:
            raise RuntimeError(
                f"Ollama /api/tags failed: HTTP {resp.status_code} {resp.text[:200]}"
            )

        data = resp.json()
        return data.get("models") or []
