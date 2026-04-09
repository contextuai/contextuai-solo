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
import concurrent.futures
from typing import Dict, Any, List, Optional, Union, AsyncGenerator
from functools import partial

from services.think_tag_parser import parse_think_tags, StreamingThinkParser

# Dedicated single-thread executor for all llama-cpp operations.
# llama-cpp-python's Llama object is NOT thread-safe — using it from
# different threads causes [Errno 22] on Windows.  A single-thread
# executor ensures every call (load, create_chat_completion, etc.)
# runs on the same OS thread.
_LLAMA_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="llama-worker"
)

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
        self._inference_lock = asyncio.Lock()
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
        runtime = (metadata.get("runtime") or "").lower()
        model_id = model_config.get("id") or model_config.get("_id") or ""
        return (
            provider == "local"
            or runtime in ("local", "llama-cpp")
            or str(model_id).startswith("local-")
            or str(model_id).startswith("local:")
        )

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def _resolve_model_path(self, model_id: str, model_config: Dict[str, Any] = None) -> str:
        """Determine the .gguf file path for the requested model.

        Resolution order:
        1. ``model_metadata.gguf_path`` (absolute path from seeder)
        2. ``model_metadata.hf_filename`` (look in MODELS_DIR root)
        3. ``model_metadata.local_model_file`` (legacy — look in MODELS_DIR/chat/)
        4. First ``.gguf`` file found in ``MODELS_DIR`` or ``MODELS_DIR/chat/``
        """
        metadata = (model_config or {}).get("model_metadata", {})

        # 1. Absolute path from seeder
        gguf_path = metadata.get("gguf_path")
        if gguf_path and os.path.isfile(gguf_path):
            return gguf_path

        # 2. HuggingFace filename from catalog seeder — check MODELS_DIR root
        #    Also try without vendor prefix (e.g. "google_gemma-4-..." → "gemma-4-...")
        hf_filename = metadata.get("hf_filename")
        if hf_filename:
            path = os.path.join(MODELS_DIR, hf_filename)
            if os.path.isfile(path):
                return path
            # Try stripped-prefix variant for manually downloaded models
            from services.local_model_seeder import _strip_vendor_prefix
            stripped = _strip_vendor_prefix(hf_filename)
            if stripped != hf_filename:
                path = os.path.join(MODELS_DIR, stripped)
                if os.path.isfile(path):
                    return path

        # 3. Legacy local_model_file — check MODELS_DIR/chat/
        local_file = metadata.get("local_model_file")
        if local_file:
            if os.path.isabs(local_file):
                path = local_file
            else:
                path = os.path.join(MODELS_DIR, "chat", local_file)
            if os.path.isfile(path):
                return path

        # 4. Fallback — scan both directories for any .gguf file
        for search_dir in [MODELS_DIR, os.path.join(MODELS_DIR, "chat")]:
            if os.path.isdir(search_dir):
                for fname in sorted(os.listdir(search_dir)):
                    if fname.lower().endswith(".gguf"):
                        return os.path.join(search_dir, fname)

        raise FileNotFoundError(
            f"No .gguf model files found in {MODELS_DIR}. "
            "Download a model from the Model Hub first."
        )

    def _ensure_model(self, model_path: str) -> Any:
        """Lazy-load (or swap) the Llama model."""
        if not LLAMA_CPP_AVAILABLE:
            raise RuntimeError(
                "llama-cpp-python is not installed. "
                "Install with: pip install llama-cpp-python"
            )

        # Normalize path for consistent comparison
        model_path = os.path.normpath(os.path.abspath(model_path))

        if self._model is not None and self._loaded_model_path == model_path:
            return self._model

        # Unload previous model if switching
        if self._model is not None:
            logger.info("Unloading previous model: %s", self._loaded_model_path)
            self.unload_model()

        logger.info("Loading GGUF model from %s …", model_path)

        # Determine context size — smaller for very large models to save RAM
        file_size_gb = os.path.getsize(model_path) / (1024 ** 3)
        if file_size_gb > 15:
            n_ctx = 2048
            logger.info("Large model (%.1f GB) — using n_ctx=%d to save RAM", file_size_gb, n_ctx)
        elif file_size_gb > 8:
            n_ctx = 4096
        else:
            n_ctx = 4096

        try:
            self._model = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=os.cpu_count() or 4,
                use_mmap=True,
                verbose=False,
            )
        except Exception as e:
            error_msg = str(e)
            combined = error_msg
            logger.error("Failed to load model %s: %s", model_path, error_msg)

            # Check for unsupported architecture (may appear in exception or stderr)
            if "unknown model architecture" in combined:
                import re
                import llama_cpp as _lc
                version = getattr(_lc, "__version__", "unknown")
                arch_match = re.search(r"unknown model architecture: '(\w+)'", combined)
                arch_name = arch_match.group(1) if arch_match else "unknown"
                raise RuntimeError(
                    f"This model uses the '{arch_name}' architecture which is not yet "
                    f"supported by llama-cpp-python v{version}. This usually means the "
                    f"model is very new. Support will be added in a future update. "
                    f"Please try a different model for now."
                ) from e

            # Check for out-of-memory / allocation failures
            if "failed to allocate" in combined.lower() or "out of memory" in combined.lower():
                raise RuntimeError(
                    f"Not enough RAM to load this model. "
                    f"Try closing other applications or using a smaller model."
                ) from e

            # Retry with minimal context if it failed for other reasons
            if n_ctx > 512:
                logger.info("Retrying with n_ctx=512...")
                try:
                    self._model = Llama(
                        model_path=model_path,
                        n_ctx=512,
                        n_threads=os.cpu_count() or 4,
                        use_mmap=True,
                        verbose=False,
                    )
                except Exception as retry_err:
                    retry_combined = str(retry_err)

                    # Check architecture on retry too
                    if "unknown model architecture" in retry_combined:
                        import re
                        import llama_cpp as _lc
                        version = getattr(_lc, "__version__", "unknown")
                        arch_match = re.search(r"unknown model architecture: '(\w+)'", retry_combined)
                        arch_name = arch_match.group(1) if arch_match else "unknown"
                        raise RuntimeError(
                            f"This model uses the '{arch_name}' architecture which is not yet "
                            f"supported by llama-cpp-python v{version}. This usually means the "
                            f"model is very new. Support will be added in a future update. "
                            f"Please try a different model for now."
                        ) from retry_err

                    raise RuntimeError(
                        f"Failed to load this model. It may be corrupted or incompatible. "
                        f"Try re-downloading or using a different model."
                    ) from retry_err
            else:
                raise

        self._loaded_model_path = model_path
        logger.info("Model loaded successfully: %s (%.1f GB, n_ctx=%d)", model_path, file_size_gb, n_ctx)
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
        # Run model loading on the dedicated llama thread to ensure all
        # llama-cpp operations happen on the same OS thread (Windows).
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_LLAMA_EXECUTOR, self._ensure_model, model_path)
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
            return self._locked_stream(messages, model_id, max_tokens, temperature, tools)
        else:
            async with self._inference_lock:
                return await self._sync_response(messages, model_id, max_tokens, temperature, tools)

    async def _locked_stream(
        self,
        messages: List[Dict[str, str]],
        model_id: str,
        max_tokens: int,
        temperature: float,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Wrap streaming with inference lock so concurrent requests wait."""
        async with self._inference_lock:
            async for chunk in self._stream_response(messages, model_id, max_tokens, temperature, tools):
                yield chunk

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
            _LLAMA_EXECUTOR,
            partial(self._model.create_chat_completion, **create_kwargs),
        )

        choice = response["choices"][0] if response.get("choices") else {}
        message = choice.get("message", {})
        content = message.get("content") or ""
        usage = response.get("usage", {})

        # Strip <think> tags and extract reasoning
        parsed = parse_think_tags(content)

        result: Dict[str, Any] = {
            "content": parsed.content,
            "model_id": model_id,
            "tokens_used": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "stop_reason": "end_turn",
        }

        if parsed.reasoning:
            result["reasoning"] = parsed.reasoning

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
        """Streaming inference, yielding SSE-compatible chunks.

        On Windows, llama-cpp-python's streaming iterator uses C file
        handles that cannot safely cross thread boundaries (causes
        ``[Errno 22] Invalid argument``).  We consume the entire stream
        in a single executor call, collecting all chunks, then yield
        them back to the async generator.  This trades true token-by-
        token streaming for reliability on Windows while still producing
        progressive SSE output.
        """
        loop = asyncio.get_event_loop()

        create_kwargs: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            create_kwargs["tools"] = tools

        # Use non-streaming completion to avoid Windows thread-safety issues
        # with llama-cpp-python's streaming iterator, then yield the result
        # as progressive chunks for SSE compatibility.
        non_stream_kwargs = {**create_kwargs, "stream": False}
        response = await loop.run_in_executor(
            _LLAMA_EXECUTOR,
            partial(self._model.create_chat_completion, **non_stream_kwargs),
        )

        choice = response["choices"][0] if response.get("choices") else {}
        full_text = (choice.get("message", {}).get("content") or "")

        # Simulate chunked output by splitting into word-boundary segments
        all_chunks = []
        for i, char in enumerate(full_text):
            all_chunks.append({
                "choices": [{"delta": {"content": char}, "finish_reason": None}]
            })
        if all_chunks:
            all_chunks[-1]["choices"][0]["finish_reason"] = "stop"

        think_parser = StreamingThinkParser()

        for chunk in all_chunks:
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            text = delta.get("content") or ""

            if text:
                for kind, segment_text in think_parser.feed(text):
                    if segment_text:
                        yield {
                            "chunk": segment_text if kind == "content" else "",
                            "thinking": segment_text if kind == "thinking" else "",
                            "model_id": model_id,
                            "is_final": False,
                            "status": "streaming",
                        }

        # Flush remaining buffered text from the think parser
        for kind, segment_text in think_parser.finish():
            if segment_text:
                yield {
                    "chunk": segment_text if kind == "content" else "",
                    "thinking": segment_text if kind == "thinking" else "",
                    "model_id": model_id,
                    "is_final": False,
                    "status": "streaming",
                }

        yield {
            "chunk": "",
            "model_id": model_id,
            "is_final": True,
            "status": "complete",
        }


    async def generate(self, model_id: str, prompt: str, max_tokens: int = 2048) -> str:
        """Simple text generation helper for workspace/crew agents.

        Returns the generated text as a plain string.
        """
        result = await self.call_model(
            prompt=prompt,
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=0.3,
            stream=False,
        )
        return result.get("content", "")


# Singleton
local_model_service = LocalModelService()
