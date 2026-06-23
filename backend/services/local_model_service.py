"""
Local GGUF Model Service

Provides inference for locally-downloaded GGUF models via llama-cpp-python.
Mirrors the OllamaService interface so the universal model adapter can route
to local models transparently.
"""

import gc
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


def _supports_gpu_offload() -> bool:
    """Whether the installed llama-cpp build can offload to a GPU.

    This is the only reliable cross-vendor signal: it returns True for a
    wheel compiled with CUDA, Metal (macOS), or Vulkan support, and False
    for a CPU-only wheel — regardless of which vendor's GPU is present.
    """
    if not LLAMA_CPP_AVAILABLE:
        return False
    try:
        import llama_cpp

        fn = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        if fn is not None:
            return bool(fn())
    except Exception:  # pragma: no cover - defensive
        pass
    return False


def _resolve_gpu_layers() -> int:
    """Decide ``n_gpu_layers`` from the ``LOCAL_MODEL_GPU_LAYERS`` env var.

    - ``auto`` (default): offload all layers (``-1``) when the llama-cpp build
      supports GPU offload (CUDA / Metal / Vulkan), otherwise CPU (``0``).
    - ``0``: force CPU — useful to benchmark CPU vs GPU on the same machine.
    - ``<int>``: offload exactly that many layers.
    """
    raw = os.getenv("LOCAL_MODEL_GPU_LAYERS", "auto").strip().lower()
    if raw not in ("", "auto"):
        try:
            return int(raw)
        except ValueError:
            logger.warning(
                "Invalid LOCAL_MODEL_GPU_LAYERS=%r — falling back to auto", raw
            )
    return -1 if _supports_gpu_offload() else 0


class LocalModelService:
    """Service for running GGUF models locally via llama-cpp-python."""

    def __init__(self):
        self._model: Optional[Any] = None
        self._loaded_model_path: Optional[str] = None
        self._loaded_model_id: Optional[str] = None
        self._loaded_n_ctx: Optional[int] = None
        self._loaded_n_gpu_layers: Optional[int] = None
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

        n_threads = os.cpu_count() or 4
        n_batch = 1024 if file_size_gb < 10 else 512
        gpu_layers = _resolve_gpu_layers()

        if gpu_layers != 0:
            logger.info(
                "GPU offload enabled (n_gpu_layers=%d) — set LOCAL_MODEL_GPU_LAYERS=0 to force CPU",
                gpu_layers,
            )

        # Try progressively more conservative configs. The first attempt uses
        # the GPU (when available); subsequent attempts fall back to CPU and
        # then to a minimal context so a single bad config never hard-fails.
        attempts = [(n_ctx, n_batch, gpu_layers)]
        if gpu_layers != 0:
            attempts.append((n_ctx, n_batch, 0))  # GPU OOM / driver issue → CPU
        if n_ctx > 512:
            attempts.append((512, 512, 0))  # last resort: tiny CPU context

        last_err: Optional[Exception] = None
        for ctx, batch, layers in attempts:
            try:
                self._model = Llama(
                    model_path=model_path,
                    n_ctx=ctx,
                    n_batch=batch,
                    n_threads=n_threads,
                    n_gpu_layers=layers,
                    use_mmap=True,
                    verbose=False,
                )
                self._loaded_n_ctx = ctx
                self._loaded_n_gpu_layers = layers
                break
            except Exception as e:
                combined = str(e)

                # Unsupported architecture is unrecoverable — no fallback helps.
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

                last_err = e
                logger.warning(
                    "Model load attempt failed (n_ctx=%d, n_gpu_layers=%d): %s — trying next config",
                    ctx, layers, combined,
                )
        else:
            # Every attempt failed — classify the final error for the user.
            combined = str(last_err)
            logger.error("Failed to load model %s: %s", model_path, combined)
            if "failed to allocate" in combined.lower() or "out of memory" in combined.lower():
                raise RuntimeError(
                    "Not enough memory to load this model. "
                    "Try closing other applications or using a smaller model."
                ) from last_err
            raise RuntimeError(
                "Failed to load this model. It may be corrupted or incompatible. "
                "Try re-downloading or using a different model."
            ) from last_err

        self._loaded_model_path = model_path
        logger.info(
            "Model loaded successfully: %s (%.1f GB, n_ctx=%d, n_gpu_layers=%d)",
            model_path, file_size_gb, self._loaded_n_ctx, self._loaded_n_gpu_layers,
        )
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
            # Call close() only — letting GC run the finalizer afterwards.
            # Explicitly invoking __del__ here risks a double free (REL-8).
            try:
                if hasattr(self._model, "close"):
                    self._model.close()
            except Exception as e:
                logger.warning("Error closing model: %s", e)
            self._model = None
            self._loaded_model_path = None
            self._loaded_model_id = None
            self._loaded_n_ctx = None
            self._loaded_n_gpu_layers = None
            gc.collect()
            logger.info("Model unloaded and memory released: %s", model_path)

    # ------------------------------------------------------------------
    # Status / discovery
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return information about the currently loaded model."""
        gpu_supported = _supports_gpu_offload()
        if self._model is None:
            return {
                "loaded": False,
                "llama_cpp_available": LLAMA_CPP_AVAILABLE,
                "gpu_offload_supported": gpu_supported,
                "models_dir": MODELS_DIR,
            }
        return {
            "loaded": True,
            "model_path": self._loaded_model_path,
            "model_id": self._loaded_model_id,
            "n_ctx": self._loaded_n_ctx,
            "n_gpu_layers": self._loaded_n_gpu_layers,
            "gpu_offload_supported": gpu_supported,
            "gpu_active": bool(self._loaded_n_gpu_layers),
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

        On Windows, llama-cpp-python's model object is not thread-safe.
        All llama-cpp calls run on ``_LLAMA_EXECUTOR`` (a single-thread
        pool).  We consume the stream on that thread and push chunks
        through an :class:`asyncio.Queue` so the async generator can
        yield them token-by-token for a progressive UI experience.
        """
        import queue as _queue

        create_kwargs: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            create_kwargs["tools"] = tools

        # Thread-safe queue bridges the llama executor thread → async loop.
        chunk_queue: _queue.Queue = _queue.Queue()
        _SENTINEL = object()

        def _produce():
            """Runs on _LLAMA_EXECUTOR: consume stream, push chunks."""
            try:
                for chunk in self._model.create_chat_completion(**create_kwargs):
                    chunk_queue.put(chunk)
            except Exception as exc:
                chunk_queue.put(exc)
            finally:
                chunk_queue.put(_SENTINEL)

        # Fire-and-forget on the dedicated llama thread.  Because the
        # executor has max_workers=1 and _ensure_model already ran on it,
        # this is guaranteed to be the same OS thread.
        loop = asyncio.get_event_loop()
        fut = loop.run_in_executor(_LLAMA_EXECUTOR, _produce)

        think_parser = StreamingThinkParser()

        while True:
            # Block briefly in a thread so we don't starve the event loop
            try:
                chunk = await loop.run_in_executor(
                    None, lambda: chunk_queue.get(timeout=0.1)
                )
            except _queue.Empty:
                if fut.done():
                    break
                continue

            if chunk is _SENTINEL:
                break

            if isinstance(chunk, Exception):
                raise chunk

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
        # Look up model config from DB so _resolve_model_path gets the correct gguf_path
        model_config = None
        try:
            from database import get_database
            db = await get_database()
            model_config = await db["models"].find_one({"_id": f"local:{model_id}"})
            if not model_config:
                model_config = await db["models"].find_one({"_id": model_id})
        except Exception:
            pass

        result = await self.call_model(
            prompt=prompt,
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=0.3,
            stream=False,
            model_config=model_config,
        )
        return result.get("content", "")


# Singleton
local_model_service = LocalModelService()
