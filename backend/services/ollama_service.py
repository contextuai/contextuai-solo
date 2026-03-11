"""
Ollama Local Model Service

Provides integration with Ollama for running local LLMs.
Uses the official `ollama` Python SDK for chat completions.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Union, AsyncGenerator

from ollama import AsyncClient

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")


class OllamaService:
    """Service for invoking local models via the Ollama Python SDK."""

    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self._client: Optional[AsyncClient] = None
        logger.info(f"OllamaService initialized with base URL: {self.base_url}")

    @property
    def client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient(host=self.base_url)
        return self._client

    @staticmethod
    def is_ollama_model(model_config: Dict[str, Any]) -> bool:
        """Check if a model config targets Ollama."""
        provider = (model_config.get("provider") or "").lower()
        metadata = model_config.get("model_metadata", {})
        return provider == "ollama" or metadata.get("runtime") == "ollama"

    async def health_check(self) -> Dict[str, Any]:
        """Check if Ollama is reachable and list pulled models."""
        try:
            response = await self.client.list()
            models = [m.model for m in response.models]
            return {"status": "healthy", "models": models}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def call_model(
        self,
        prompt: str,
        model_id: str,
        persona_context: Dict[str, Any] = None,
        conversation_history: List[Dict[str, Any]] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        stream: bool = False,
        model_config: Dict[str, Any] = None,
        **kwargs,
    ) -> Union[Dict[str, Any], AsyncGenerator[Dict[str, Any], None]]:
        """Call an Ollama model using the official SDK."""

        # Resolve the actual Ollama model name from config
        metadata = (model_config or {}).get("model_metadata", {})
        ollama_model = metadata.get("ollama_model") or model_id

        # Build messages array
        messages = []

        # System prompt from persona
        if persona_context and persona_context.get("system_prompt"):
            messages.append({"role": "system", "content": persona_context["system_prompt"]})

        # Conversation history
        if conversation_history:
            for msg in conversation_history:
                role = msg.get("role", msg.get("message_type", "user"))
                if role == "assistant_message":
                    role = "assistant"
                elif role == "user_message":
                    role = "user"
                content = msg.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})

        # Current user message
        messages.append({"role": "user", "content": prompt})

        options = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }

        logger.info(f"Ollama request: model={ollama_model}, stream={stream}, messages={len(messages)}")

        if stream:
            return self._stream_response(ollama_model, messages, options, model_id)
        else:
            return await self._sync_response(ollama_model, messages, options, model_id)

    async def _sync_response(
        self, ollama_model: str, messages: List[Dict], options: Dict, model_id: str
    ) -> Dict[str, Any]:
        """Non-streaming call to Ollama."""
        response = await self.client.chat(
            model=ollama_model,
            messages=messages,
            options=options,
        )

        content = response.message.content or ""
        prompt_tokens = response.prompt_eval_count or 0
        completion_tokens = response.eval_count or 0

        return {
            "content": content,
            "model_id": model_id,
            "tokens_used": {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "stop_reason": "end_turn",
        }

    async def _stream_response(
        self, ollama_model: str, messages: List[Dict], options: Dict, model_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming call to Ollama, yielding SSE-compatible chunks."""
        stream = await self.client.chat(
            model=ollama_model,
            messages=messages,
            options=options,
            stream=True,
        )

        async for chunk in stream:
            text = chunk.message.content or ""
            if chunk.done:
                yield {
                    "chunk": text,
                    "model_id": model_id,
                    "is_final": True,
                    "status": "complete",
                    "tokens_used": {
                        "input_tokens": chunk.prompt_eval_count or 0,
                        "output_tokens": chunk.eval_count or 0,
                        "total_tokens": (chunk.prompt_eval_count or 0) + (chunk.eval_count or 0),
                    },
                }
                return
            elif text:
                yield {
                    "chunk": text,
                    "model_id": model_id,
                    "is_final": False,
                    "status": "streaming",
                }


# Singleton
ollama_service = OllamaService()
