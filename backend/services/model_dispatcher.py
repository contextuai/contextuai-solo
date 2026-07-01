"""
Model Dispatcher — provider-agnostic streaming chat.

Extracted from ``routers/openai_compat.py`` so the workflow engine and other
services can call model inference directly without an HTTP round-trip.

Dispatching by model-id prefix:
    anthropic:<model>  ->  AnthropicDirectService.stream_chat()
    google:<model>     ->  GoogleDirectService.stream_chat()
    openai:<model>     ->  OpenAIDirectService.stream_chat()
    bedrock:<model>    ->  UniversalModelAdapter.stream_chat()
    ollama:<model>     ->  OllamaDirectService.stream_chat()
    <bare name>        ->  local llama-cpp

Yields normalized events:
    {"type": "delta",  "content": "..."}
    {"type": "done",   "finish_reason": "stop", "usage": {...}}

Raises ProviderUnavailable if a cloud key is missing or the local model
is not installed.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

# Order matters: "openai_compat" must come before "openai" so an
# "openai_compat:<model>" id isn't mis-parsed (though the ":" separator
# already prevents overlap, keep it explicit and unambiguous).
_KNOWN_PREFIXES = ("anthropic", "google", "openai_compat", "openai", "bedrock", "ollama")

DEFAULT_SENTINEL = "__DEFAULT__"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ProviderUnavailable(Exception):
    """Raised when a required credential or model is missing."""


# ---------------------------------------------------------------------------
# Provider prefix parsing (same logic as openai_compat._parse_provider)
# ---------------------------------------------------------------------------

def _parse_provider(model_id: str) -> tuple[str, str]:
    """Return (provider, clean_model_id).

    Provider is one of: anthropic | google | openai | bedrock | ollama | local.
    The ``local:`` and ``local-`` prefixes are stripped — the seeder writes
    local model rows with ``_id = "local:<catalog_id>"`` so any default-model
    resolution will carry the prefix.
    """
    for prefix in _KNOWN_PREFIXES:
        if model_id.startswith(f"{prefix}:"):
            return prefix, model_id[len(prefix) + 1:]
    # Local sentinels — strip and dispatch to llama-cpp.
    if model_id.startswith("local:"):
        return "local", model_id[len("local:"):]
    if model_id.startswith("local-"):
        return "local", model_id[len("local-"):]
    return "local", model_id


# ---------------------------------------------------------------------------
# Default model resolution
# ---------------------------------------------------------------------------

async def resolve_default_model(db) -> str:
    """Resolve ``__DEFAULT__`` to a concrete model ID.

    Resolution order:
    1. Saved AI-mode preference + default model from settings collection.
    2. First enabled local model from the models collection.
    3. First installed GGUF on disk (via model_manager).
    4. Raises ProviderUnavailable if none found.
    """
    # 1. Check settings/preferences for a default_model_id override.
    try:
        settings_col = db["settings"]
        pref = await settings_col.find_one({"_id": "default_model_id"})
        if pref and pref.get("model_id"):
            return str(pref["model_id"])
    except Exception:
        pass

    # 2. Delegate to DefaultModelService for the first enabled local model.
    try:
        from services.default_model_service import DefaultModelService
        svc = DefaultModelService(db)
        mode = await svc.get_ai_mode_preference()
        model_id = await svc.get_default_model_id(mode)
        if model_id:
            return model_id
    except Exception as exc:
        logger.debug("DefaultModelService lookup failed: %s", exc)

    # 3. Scan disk for the first installed GGUF.
    try:
        from services.model_manager import model_manager
        installed = model_manager.list_installed()
        if installed:
            return installed[0]["id"]
    except Exception as exc:
        logger.debug("model_manager scan failed: %s", exc)

    raise ProviderUnavailable(
        "No model configured. Pick one in the role config."
    )


# ---------------------------------------------------------------------------
# Cloud provider stream helpers
# ---------------------------------------------------------------------------

async def _cloud_stream(
    provider: str,
    clean_model: str,
    creds: Dict[str, Any],
    messages: List[Dict[str, Any]],
    *,
    temperature: float,
    max_tokens: int,
    top_p: float,
    stop: Optional[List[str]],
) -> AsyncIterator[Dict[str, Any]]:
    """Return a normalized async iterator for a cloud provider."""
    kwargs: Dict[str, Any] = dict(
        model_id=clean_model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        stop=stop or None,
    )

    if provider == "anthropic":
        api_key = creds.get("api_key") or ""
        if not api_key:
            raise ProviderUnavailable("Anthropic API key not configured")
        from services.anthropic_direct_service import AnthropicDirectService
        svc = AnthropicDirectService()
        return svc.stream_chat(messages, api_key=api_key, **kwargs)

    if provider == "openai":
        api_key = creds.get("api_key") or ""
        if not api_key:
            raise ProviderUnavailable("OpenAI API key not configured")
        from services.openai_direct_service import OpenAIDirectService
        svc = OpenAIDirectService()
        return svc.stream_chat(messages, api_key=api_key, **kwargs)

    if provider == "google":
        api_key = creds.get("api_key") or ""
        if not api_key:
            raise ProviderUnavailable("Google API key not configured")
        from services.google_direct_service import GoogleDirectService
        svc = GoogleDirectService()
        return svc.stream_chat(messages, api_key=api_key, **kwargs)

    if provider == "bedrock":
        aws_key = creds.get("aws_access_key_id") or ""
        aws_secret = creds.get("aws_secret_access_key") or ""
        if not (aws_key and aws_secret):
            raise ProviderUnavailable("AWS Bedrock credentials not configured")
        from services.universal_model_adapter import UniversalModelAdapter
        adapter = UniversalModelAdapter(bedrock_credentials=creds)
        kw = {k: v for k, v in kwargs.items() if k != "model_id"}
        return adapter.stream_chat(messages, model_id=clean_model, **kw)

    if provider == "ollama":
        base_url = creds.get("base_url")
        from services.ollama_direct_service import OllamaDirectService
        svc = OllamaDirectService()
        return svc.stream_chat(messages, base_url=base_url, **kwargs)

    if provider == "openai_compat":
        base_url = creds.get("base_url")
        if not base_url:
            raise ProviderUnavailable("OpenAI-compatible base_url not configured")
        api_key = creds.get("api_key") or None  # optional for keyless servers
        from services.openai_direct_service import OpenAIDirectService
        svc = OpenAIDirectService()
        return svc.stream_chat(messages, api_key=api_key, base_url=base_url, **kwargs)

    raise ProviderUnavailable(f"Unknown provider: {provider!r}")


# ---------------------------------------------------------------------------
# Local llama-cpp streaming (yields normalized events)
# ---------------------------------------------------------------------------

async def _local_stream(
    model_id: str,
    messages: List[Dict[str, Any]],
    *,
    temperature: float,
    max_tokens: int,
    top_p: float,
    stop: Optional[List[str]],
) -> AsyncIterator[Dict[str, Any]]:
    """Wrap llama-cpp local inference as a normalized async generator."""
    from services.local_model_service import local_model_service, LLAMA_CPP_AVAILABLE
    from services.model_catalog import LOCAL_MODEL_CATALOG

    if not LLAMA_CPP_AVAILABLE:
        raise ProviderUnavailable("llama-cpp-python is not installed")

    # Resolve catalog entry
    catalog_entry: Optional[Dict[str, Any]] = None
    name_lower = model_id.lower().strip()
    for entry in LOCAL_MODEL_CATALOG:
        if entry["id"] == name_lower:
            catalog_entry = entry
            break
    if catalog_entry is None:
        raise ProviderUnavailable(
            f"Model '{model_id}' not found in local catalog. "
            "Download it from the Model Hub first."
        )

    from services.model_manager import model_manager
    if not model_manager.is_installed(catalog_entry["id"]):
        raise ProviderUnavailable(
            f"Model '{model_id}' is in the catalog but not downloaded. "
            "Download it from the Model Hub first."
        )

    model_config = {
        "model_metadata": {
            "runtime": "llama-cpp",
            "hf_filename": catalog_entry["hf_filename"],
        }
    }
    model_path = local_model_service._resolve_model_path(catalog_entry["id"], model_config)
    llm = local_model_service._ensure_model(model_path)
    local_model_service._loaded_model_id = catalog_entry["id"]

    loop = asyncio.get_event_loop()

    stream_iter = await loop.run_in_executor(
        None,
        partial(
            llm.create_chat_completion,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop or None,
            stream=True,
        ),
    )

    def _next(it):
        try:
            return next(it)
        except StopIteration:
            return None

    content_parts: List[str] = []

    while True:
        chunk = await loop.run_in_executor(None, _next, stream_iter)
        if chunk is None:
            break
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        text = delta.get("content") or ""
        finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")
        if text:
            content_parts.append(text)
            yield {"type": "delta", "content": text}
        if finish_reason:
            yield {
                "type": "done",
                "finish_reason": finish_reason,
                "usage": chunk.get("usage", {}),
            }
            return

    # Fell off the end without an explicit finish_reason chunk
    yield {"type": "done", "finish_reason": "stop", "usage": {}}


# This is an async generator factory — it cannot be a plain async function
# that returns an iterator because the local path IS an async generator.
# We wrap both paths so callers always do ``async for event in stream_chat(...)``.

async def stream_chat(
    model_id: str,
    messages: List[Dict[str, Any]],
    *,
    db=None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    top_p: float = 1.0,
    stop: Optional[List[str]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Provider-agnostic streaming chat.

    Yields normalized events:
        {"type": "delta",  "content": "..."}
        {"type": "done",   "finish_reason": "stop", "usage": {...}}

    Args:
        model_id: May include a provider prefix (``anthropic:model-name``) or
            be a bare local model ID.  The sentinel ``__DEFAULT__`` is resolved
            via ``resolve_default_model(db)`` — *db* must not be None in that
            case.
        messages: OpenAI-format message list.
        db: Database proxy (required when model_id is ``__DEFAULT__`` or a
            cloud provider key lookup is needed).
        temperature: Sampling temperature (default 0.7).
        max_tokens: Maximum tokens to generate (default 4096).
        top_p: Nucleus sampling parameter (default 1.0).
        stop: Optional list of stop sequences.

    Raises:
        ProviderUnavailable: When a required credential or model is missing.
    """
    # Resolve the __DEFAULT__ sentinel before anything else.
    if model_id == DEFAULT_SENTINEL:
        if db is None:
            raise ProviderUnavailable(
                "db is required to resolve the __DEFAULT__ model sentinel"
            )
        model_id = await resolve_default_model(db)

    provider, clean_model = _parse_provider(model_id)

    if provider == "local":
        # Local is an async generator — yield directly.
        async for event in _local_stream(
            clean_model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
        ):
            yield event
        return

    # Cloud providers: fetch credentials, get iterator, yield.
    if db is None:
        raise ProviderUnavailable(
            f"db is required to fetch credentials for provider '{provider}'"
        )
    from services.cloud_provider_service import CloudProviderService
    cred_svc = CloudProviderService(db)
    creds = await cred_svc.get_credentials(provider)
    if not creds:
        raise ProviderUnavailable(
            f"No saved credentials for provider '{provider}'. "
            "Add a key in Settings -> AI Providers."
        )

    cloud_iter = await _cloud_stream(
        provider,
        clean_model,
        creds,
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stop=stop,
    )
    async for event in cloud_iter:
        yield event
