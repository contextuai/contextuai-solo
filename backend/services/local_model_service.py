"""
Local GGUF Model Service

Provides inference for locally-downloaded GGUF models via llama-cpp-python.
Mirrors the OllamaService interface so the universal model adapter can route
to local models transparently.
"""

import os
import asyncio
import logging
import pathlib
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
from functools import partial

logger = logging.getLogger(__name__)

try:
    from llama_cpp import Llama

    LLAMA_CPP_AVAILABLE = True
except ImportError:
    Llama = None
    LLAMA_CPP_AVAILABLE = False
    logger.warning(
        "llama-cpp-python is not installed. Local GGUF model inference will be unavailable. "
        "Install with: pip install llama-cpp-python"
    )

MODELS_DIR = os.getenv(
    "MODELS_DIR",
    os.path.join(pathlib.Path.home(), ".contextuai-solo", "models"),
)


class LocalModelService:
    """Service for running GGUF models locally via llama-cpp-python."""

    def __init__(self):
        self._model: Optional[Any] = None
        self._loaded_model_path: Optional[str] = None
        self._loaded_model_id: Optional[str] = None
        logger.info(
            "LocalModelService initialized – models dir: %s, llama-cpp available: %s",
            MODELS_DIR,
            LLAMA_CPP_AVAILABLE,
        )

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    @staticmethod
    def is_local_model(model_config: Dict[str, Any]) -> bool:
        """Check if a model config targets local GGUF inference."""
        provider = (model_config.get("provider") or "").lower()
        metadata = model_config.get("model_metadata", {})
        return provider == "local" or metadata.get("runtime") == "local"

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def _resolve_model_path(self, model_id: str, model_config: Dict[str, Any] = None) -> str:
        """Determine the .gguf file path for the requested model.

        Resolution order:
        1. ``model_metadata.local_model_file`` (explicit filename)
        2. First ``.gguf`` file found in ``MODELS_DIR/chat/``
        """
        metadata = (model_config or {}).get("model_metadata", {})
        local_file = metadata.get("local_model_file")

        if local_file:
            # Accept absolute paths as-is; relative paths resolve under MODELS_DIR/chat/
            if os.path.isabs(local_file):
                path = local_file
            else:
                path = os.path.join(MODELS_DIR, "chat", local_file)
            if not os.path.isfile(path):
                raise FileNotFoundError(
                    f"Configured local_model_file not found: {path}"
                )
            return path

        # Fallback – scan MODELS_DIR/chat/ for the first .gguf file
        chat_dir = os.path.join(MODELS_DIR, "chat")
        if os.path.isdir(chat_dir):
            for fname in sorted(os.listdir(chat_dir)):
                if fname.lower().endswith(".gguf"):
                    return os.path.join(chat_dir, fname)

        raise FileNotFoundError(
            f"No .gguf model files found in {chat_dir}. "
            "Download a model or set 'local_model_file' in model metadata."
        )

    def _ensure_model(self, model_path: str) -> Any:
        """Lazy-load (or swap) the Llama model."""
        if not LLAMA_CPP_AVAILABLE:
            raise RuntimeError(
                "llama-cpp-python is not installed. "
                "Install with: pip install llama-cpp-python"
            )

        if self._model is not None and self._loaded_model_path == model_path:
            return self._model

        # Unload previous model if switching
        if self._model is not None:
            logger.info("Unloading previous model: %s", self._loaded_model_path)
            self.unload_model()

        logger.info("Loading GGUF model from %s …", model_path)
        self._model = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_threads=os.cpu_count() or 4,
        )
        self._loaded_model_path = model_path
        logger.info("Model loaded successfully: %s", model_path)
        return self._model

    def load_model(self, model_path: str, model_id: str = None) -> None:
        """Explicitly load a model into RAM (used by the /load endpoint)."""
        self._ensure_model(model_path)
        if model_id:
            self._loaded_model_id = model_id

    def unload_model(self) -> None:
        """Free RAM by releasing the loaded model."""
        if self._model is not None:
            model_path = self._loaded_model_path
            del self._model
            self._model = None
            self._loaded_model_path = None
            self._loaded_model_id = None
            logger.info("Model unloaded: %s", model_path)

    # ------------------------------------------------------------------
    # Status / discovery
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return information about the currently loaded model."""
        if self._model is None:
            return {
                "loaded": False,
                "llama_cpp_available": LLAMA_CPP_AVAILABLE,
                "models_dir": MODELS_DIR,
            }
        return {
            "loaded": True,
            "model_path": self._loaded_model_path,
            "model_id": self._loaded_model_id,
            "llama_cpp_available": LLAMA_CPP_AVAILABLE,
            "models_dir": MODELS_DIR,
        }

    def list_downloaded_models(self) -> List[Dict[str, Any]]:
        """Scan ``MODELS_DIR/chat/`` for .gguf files and return metadata."""
        chat_dir = os.path.join(MODELS_DIR, "chat")
        models: List[Dict[str, Any]] = []
        if not os.path.isdir(chat_dir):
            return models

        for fname in sorted(os.listdir(chat_dir)):
            if not fname.lower().endswith(".gguf"):
                continue
            full_path = os.path.join(chat_dir, fname)
            try:
                size_bytes = os.path.getsize(full_path)
            except OSError:
                size_bytes = 0
            models.append(
                {
                    "filename": fname,
                    "path": full_path,
                    "size_bytes": size_bytes,
                    "size_gb": round(size_bytes / (1024**3), 2),
                    "loaded": full_path == self._loaded_model_path,
                }
            )
        return models

    # ------------------------------------------------------------------
    # Message building (mirrors OllamaService)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_messages(
        prompt: str,
        persona_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []

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
        return messages

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

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
        """Run inference on a local GGUF model.

        Signature and return shapes intentionally match ``OllamaService.call_model``.
        """
        model_path = self._resolve_model_path(model_id, model_config)
        self._ensure_model(model_path)
        self._loaded_model_id = model_id

        messages = self._build_messages(prompt, persona_context, conversation_history)

        # Optional tool-calling support
        tools = kwargs.get("tools")

        logger.info(
            "Local model request: model_id=%s, path=%s, stream=%s, messages=%d, tools=%s",
            model_id,
            model_path,
            stream,
            len(messages),
            bool(tools),
        )

        if stream:
            return self._stream_response(messages, model_id, max_tokens, temperature, tools)
        else:
            return await self._sync_response(messages, model_id, max_tokens, temperature, tools)

    async def _sync_response(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Non-streaming inference, offloaded to a thread executor."""
        loop = asyncio.get_event_loop()

        create_kwargs: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            create_kwargs["tools"] = tools

        response = await loop.run_in_executor(
            None,
            partial(self._model.create_chat_completion, **create_kwargs),
        )

        choice = response["choices"][0] if response.get("choices") else {}
        message = choice.get("message", {})
        content = message.get("content") or ""
        usage = response.get("usage", {})

        result: Dict[str, Any] = {
            "content": content,
            "model_id": model_id,
            "tokens_used": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "stop_reason": "end_turn",
        }

        # Attach tool calls if the model produced any
        tool_calls = message.get("tool_calls")
        if tool_calls:
            result["tool_calls"] = tool_calls

        return result

    async def _stream_response(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming inference, yielding SSE-compatible chunks."""
        loop = asyncio.get_event_loop()

        create_kwargs: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            create_kwargs["tools"] = tools

        # llama-cpp-python returns a blocking iterator when stream=True;
        # we pull chunks one-at-a-time from the executor.
        stream_iter = await loop.run_in_executor(
            None,
            partial(self._model.create_chat_completion, **create_kwargs),
        )

        accumulated_text = ""

        def _next_chunk(it):
            """Pull one chunk from the blocking iterator (runs in executor)."""
            try:
                return next(it)
            except StopIteration:
                return None

        while True:
            chunk = await loop.run_in_executor(None, _next_chunk, stream_iter)
            if chunk is None:
                # Stream exhausted – emit final frame
                yield {
                    "chunk": "",
                    "model_id": model_id,
                    "is_final": True,
                    "status": "complete",
                }
                return

            delta = chunk.get("choices", [{}])[0].get("delta", {})
            text = delta.get("content") or ""
            finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")

            if finish_reason:
                yield {
                    "chunk": text,
                    "model_id": model_id,
                    "is_final": True,
                    "status": "complete",
                }
                return
            elif text:
                accumulated_text += text
                yield {
                    "chunk": text,
                    "model_id": model_id,
                    "is_final": False,
                    "status": "streaming",
                }


# Singleton
local_model_service = LocalModelService()
