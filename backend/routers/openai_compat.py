"""
OpenAI-Compatible API Router

Exposes ``/v1/chat/completions``, ``/v1/completions``, and ``/v1/models``
so external tools (Aider, Continue.dev, Cursor, Cody, Tabby, any OpenAI SDK
client) can use Solo's local GGUF models as a drop-in replacement — or any
cloud provider by prefixing the model name.

Dispatching by model-id prefix:
    anthropic:<model>  →  AnthropicDirectService.stream_chat()
    google:<model>     →  GoogleDirectService.stream_chat()
    openai:<model>     →  OpenAIDirectService.stream_chat()
    bedrock:<model>    →  UniversalModelAdapter.stream_chat()
    ollama:<model>     →  OllamaDirectService.stream_chat()
    <bare name>        →  local llama-cpp (existing path)

Chat completions:
    curl http://localhost:18741/v1/chat/completions \
      -d '{"model":"qwen2.5-7b","messages":[{"role":"user","content":"hello"}]}'
    curl http://localhost:18741/v1/chat/completions \
      -d '{"model":"anthropic:claude-sonnet-4-20250514","messages":[...]}'

Text / FIM completions (inline autocomplete):
    curl http://localhost:18741/v1/completions \
      -d '{"model":"qwen2.5-7b","prompt":"def fib(n):\\n    ","suffix":"\\n    return result","max_tokens":128}'
"""

import asyncio
import json
import logging
import time
import uuid
from functools import partial
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import get_database
from services.local_model_service import local_model_service, LLAMA_CPP_AVAILABLE
from services.model_catalog import LOCAL_MODEL_CATALOG
from services.think_tag_parser import parse_think_tags, StreamingThinkParser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["openai-compat"])

# ── Cloud provider model catalogs (short curated lists) ─────────────────────
# Mirrors the frontend settings.tsx provider model lists.

_CLOUD_MODELS: Dict[str, List[str]] = {
    "anthropic": [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-3-5-haiku-20241022",
    ],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1-preview"],
    "google": ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-flash"],
    "bedrock": [
        "anthropic.claude-3-sonnet",
        "anthropic.claude-3-haiku",
        "amazon.titan-text-express",
    ],
    # Ollama models are discovered dynamically via list_models().
}

_KNOWN_PREFIXES = ("anthropic", "google", "openai", "bedrock", "ollama")


# ── Request / Response models ────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    top_p: Optional[float] = 1.0
    stream: Optional[bool] = False
    stop: Optional[Any] = None
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0


class CompletionRequest(BaseModel):
    """OpenAI-compatible /v1/completions request.

    Supports Fill-in-the-Middle (FIM) via the ``suffix`` parameter.
    IDE extensions (Continue.dev, Tabby, Cody, etc.) send a ``prompt``
    containing code before the cursor and ``suffix`` with code after it.
    """
    model_config = {"protected_namespaces": ()}

    model: str
    prompt: str = ""
    suffix: Optional[str] = None
    max_tokens: Optional[int] = 128
    temperature: Optional[float] = 0.2
    top_p: Optional[float] = 0.95
    stream: Optional[bool] = False
    stop: Optional[Any] = None
    echo: Optional[bool] = False
    n: Optional[int] = 1


# ── Model resolution ────────────────────────────────────────────────────────

def _resolve_model(model_name: str) -> Optional[Dict]:
    """Find a catalog entry by id, name fragment, or family+size pattern."""
    name_lower = model_name.lower().strip()

    # Direct id match
    for entry in LOCAL_MODEL_CATALOG:
        if entry["id"] == name_lower:
            return entry

    # Fuzzy: match against id with/without dots, dashes
    normalized = name_lower.replace("-", "").replace(".", "").replace(" ", "")
    for entry in LOCAL_MODEL_CATALOG:
        entry_norm = entry["id"].replace("-", "").replace(".", "").replace(" ", "")
        if entry_norm == normalized:
            return entry

    # Substring match (e.g. "qwen3.5" matches first qwen3.5 entry)
    for entry in LOCAL_MODEL_CATALOG:
        if name_lower in entry["id"] or name_lower in entry["name"].lower():
            return entry

    return None


def _generate_id(prefix: str = "chatcmpl") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ── Provider dispatch helpers ────────────────────────────────────────────────

def _parse_provider(model_name: str) -> Tuple[str, str]:
    """Return (provider, clean_model_id).

    Provider is one of: anthropic | google | openai | bedrock | ollama | local.
    """
    for prefix in _KNOWN_PREFIXES:
        if model_name.startswith(f"{prefix}:"):
            return prefix, model_name[len(prefix) + 1:]
    return "local", model_name


def _emit_openai_chunk(
    completion_id: str,
    model_id: str,
    created: int,
    content: str = "",
    finish_reason: Optional[str] = None,
) -> str:
    """Serialize a single OpenAI SSE chat.completion.chunk to ``data: {...}\\n\\n``."""
    chunk: Dict[str, Any] = {
        "id": completion_id,
        "created": created,
        "model": model_id,
        "object": "chat.completion.chunk",
        "choices": [{
            "index": 0,
            "delta": {"content": content} if content else {},
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(chunk)}\n\n"


# ── FIM (Fill-in-the-Middle) helpers ─────────────────────────────────────────

# FIM token formats by model family.  When a model supports FIM natively we
# wrap the prompt/suffix with the model's own special tokens.  For models
# without native FIM we fall back to an instruction-style prompt.
_FIM_TOKENS = {
    "qwen":   {"prefix": "<|fim_prefix|>", "suffix": "<|fim_suffix|>", "middle": "<|fim_middle|>"},
    "deepseek": {"prefix": "<|fim▁begin|>", "suffix": "<|fim▁hole|>", "middle": "<|fim▁end|>"},
    "starcoder": {"prefix": "<fim_prefix>", "suffix": "<fim_suffix>", "middle": "<fim_middle>"},
    "codellama": {"prefix": "<PRE>", "suffix": " <SUF>", "middle": " <MID>"},
}


def _build_fim_prompt(prompt: str, suffix: str, model_family: str) -> str:
    """Build a Fill-in-the-Middle prompt using model-specific tokens.

    If the model family has known FIM tokens, use them.
    Otherwise fall back to a plain instruction format that still
    produces reasonable completions.
    """
    family_lower = (model_family or "").lower()
    for key, tokens in _FIM_TOKENS.items():
        if key in family_lower:
            return (
                f"{tokens['prefix']}{prompt}"
                f"{tokens['suffix']}{suffix}"
                f"{tokens['middle']}"
            )

    # Fallback: no special tokens — just concatenate with a hint
    return f"{prompt}"


def _resolve_model_and_load(model_name: str):
    """Resolve a model name to catalog entry + loaded Llama instance.

    Returns (llm, catalog_entry) or raises HTTPException.
    """
    if not LLAMA_CPP_AVAILABLE:
        raise HTTPException(503, "llama-cpp-python is not installed")

    catalog_entry = _resolve_model(model_name)
    if not catalog_entry:
        raise HTTPException(404, f"Model '{model_name}' not found in catalog")

    from services.model_manager import model_manager
    if not model_manager.is_installed(catalog_entry["id"]):
        raise HTTPException(
            404,
            f"Model '{catalog_entry['id']}' is in the catalog but not downloaded. "
            "Download it from the Model Hub first.",
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
    return llm, catalog_entry


# ── GET /v1/models ───────────────────────────────────────────────────────────

@router.get("/v1/models")
async def list_models(db=Depends(get_database)):
    """List all available models in OpenAI format.

    Includes:
    - Installed local GGUF models (from catalog + manually added)
    - Cloud provider models for each saved provider key
    - Ollama models discovered from a running local Ollama server
    """
    from services.model_manager import model_manager
    from services.cloud_provider_service import CloudProviderService

    models: List[Dict[str, Any]] = []
    seen_ids: set = set()

    # ── Local catalog models ─────────────────────────────────────────────────
    for entry in LOCAL_MODEL_CATALOG:
        if model_manager.is_installed(entry["id"]):
            seen_ids.add(entry["id"])
            models.append({
                "id": entry["id"],
                "object": "model",
                "created": 0,
                "owned_by": entry.get("provider", "local"),
                "permission": [],
                "root": entry["id"],
                "parent": None,
            })

    # Manually-added models (not in catalog)
    for installed in model_manager.list_installed():
        mid = installed["id"]
        if mid not in seen_ids:
            models.append({
                "id": mid,
                "object": "model",
                "created": 0,
                "owned_by": installed.get("provider", "Custom"),
                "permission": [],
                "root": mid,
                "parent": None,
            })

    # ── Cloud provider models ────────────────────────────────────────────────
    svc = CloudProviderService(db)
    for provider, model_list in _CLOUD_MODELS.items():
        try:
            creds = await svc.get_credentials(provider)
            if not creds:
                continue
            # At least one real credential must be present.
            has_cred = bool(
                creds.get("api_key")
                or creds.get("aws_access_key_id")
                or creds.get("base_url")
            )
            if not has_cred:
                continue
            for m in model_list:
                full_id = f"{provider}:{m}"
                if full_id not in seen_ids:
                    seen_ids.add(full_id)
                    models.append({
                        "id": full_id,
                        "object": "model",
                        "created": 0,
                        "owned_by": provider,
                        "permission": [],
                        "root": full_id,
                        "parent": None,
                    })
        except Exception:
            logger.debug("Could not fetch %s credentials for /v1/models", provider)

    # ── Ollama models (dynamic) ──────────────────────────────────────────────
    try:
        from services.cloud_provider_service import CloudProviderService as _CPS
        ollama_creds = await svc.get_credentials("ollama")
        ollama_base = (ollama_creds or {}).get("base_url")

        from services.ollama_direct_service import OllamaDirectService
        ollama_svc = OllamaDirectService()
        ollama_models = await ollama_svc.list_models(base_url=ollama_base)
        for m in ollama_models:
            name = m.get("name") or m.get("model") or ""
            if not name:
                continue
            full_id = f"ollama:{name}"
            if full_id not in seen_ids:
                seen_ids.add(full_id)
                models.append({
                    "id": full_id,
                    "object": "model",
                    "created": 0,
                    "owned_by": "ollama",
                    "permission": [],
                    "root": full_id,
                    "parent": None,
                })
    except Exception:
        # Ollama not running or not configured — non-fatal.
        pass

    return {"object": "list", "data": models}


# ── POST /v1/chat/completions ────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    http_request: Request,
    db=Depends(get_database),
):
    """OpenAI-compatible chat completions endpoint.

    Routes by model-id prefix to the appropriate provider.
    Bare model names use the local llama-cpp path.
    """
    include_thinking = http_request.query_params.get("include_thinking", "").lower() in ("true", "1", "yes")

    provider, clean_model = _parse_provider(request.model)
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    completion_id = _generate_id()
    created = int(time.time())

    # ── Cloud provider path ──────────────────────────────────────────────────
    if provider != "local":
        from services.cloud_provider_service import CloudProviderService
        svc = CloudProviderService(db)
        creds = await svc.get_credentials(provider)
        if not creds:
            raise HTTPException(
                status_code=401,
                detail=f"No saved credentials for provider '{provider}'. "
                       "Add a key in Settings → AI Providers.",
            )

        # Build the adapter's stream iterator
        try:
            stream_iter = await _cloud_stream_iter(
                provider=provider,
                clean_model=clean_model,
                creds=creds,
                messages=messages,
                request=request,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(502, f"Provider error: {exc}") from exc

        if request.stream:
            return StreamingResponse(
                _stream_cloud_chat(stream_iter, completion_id, request.model, created),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        else:
            return await _sync_cloud_chat(stream_iter, completion_id, request.model, created)

    # ── Local llama-cpp path (unchanged) ────────────────────────────────────
    llm, catalog_entry = _resolve_model_and_load(request.model)

    if request.stream:
        return StreamingResponse(
            _stream_chat(llm, messages, request, completion_id, created, catalog_entry["id"], include_thinking),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        return await _sync_chat(llm, messages, request, completion_id, created, catalog_entry["id"], include_thinking)


async def _cloud_stream_iter(
    *,
    provider: str,
    clean_model: str,
    creds: Dict[str, Any],
    messages: List[Dict[str, Any]],
    request: ChatCompletionRequest,
) -> AsyncIterator[Dict[str, Any]]:
    """Build and return the provider-specific normalized stream iterator."""
    stop = request.stop
    if isinstance(stop, str):
        stop = [stop]

    kwargs: Dict[str, Any] = dict(
        model_id=clean_model,
        max_tokens=request.max_tokens or 2048,
        temperature=request.temperature or 0.7,
        top_p=request.top_p or 1.0,
        stop=stop or None,
    )

    if provider == "anthropic":
        api_key = creds.get("api_key") or ""
        if not api_key:
            raise HTTPException(401, "Anthropic API key not configured")
        from services.anthropic_direct_service import AnthropicDirectService
        svc = AnthropicDirectService()
        return svc.stream_chat(messages, api_key=api_key, **kwargs)

    if provider == "openai":
        api_key = creds.get("api_key") or ""
        if not api_key:
            raise HTTPException(401, "OpenAI API key not configured")
        from services.openai_direct_service import OpenAIDirectService
        svc = OpenAIDirectService()
        return svc.stream_chat(messages, api_key=api_key, **kwargs)

    if provider == "google":
        api_key = creds.get("api_key") or ""
        if not api_key:
            raise HTTPException(401, "Google API key not configured")
        from services.google_direct_service import GoogleDirectService
        svc = GoogleDirectService()
        return svc.stream_chat(messages, api_key=api_key, **kwargs)

    if provider == "bedrock":
        aws_key = creds.get("aws_access_key_id") or ""
        aws_secret = creds.get("aws_secret_access_key") or ""
        if not (aws_key and aws_secret):
            raise HTTPException(401, "AWS Bedrock credentials not configured")
        from services.universal_model_adapter import UniversalModelAdapter
        adapter = UniversalModelAdapter(bedrock_credentials=creds)
        return adapter.stream_chat(messages, model_id=clean_model, **{
            k: v for k, v in kwargs.items() if k != "model_id"
        })

    if provider == "ollama":
        base_url = creds.get("base_url")
        from services.ollama_direct_service import OllamaDirectService
        svc = OllamaDirectService()
        return svc.stream_chat(messages, base_url=base_url, **kwargs)

    raise HTTPException(400, f"Unknown provider: {provider!r}")


async def _stream_cloud_chat(
    stream_iter: AsyncIterator[Dict[str, Any]],
    completion_id: str,
    model_id: str,
    created: int,
):
    """Convert normalized provider events to OpenAI SSE chunks."""
    async for event in stream_iter:
        if event["type"] == "delta":
            yield _emit_openai_chunk(completion_id, model_id, created, content=event["content"])
        elif event["type"] == "done":
            yield _emit_openai_chunk(
                completion_id, model_id, created,
                finish_reason=event.get("finish_reason", "stop"),
            )
    yield "data: [DONE]\n\n"


async def _sync_cloud_chat(
    stream_iter: AsyncIterator[Dict[str, Any]],
    completion_id: str,
    model_id: str,
    created: int,
) -> Dict[str, Any]:
    """Accumulate the normalized stream and return a single chat.completion."""
    content_parts: List[str] = []
    finish_reason = "stop"
    usage: Dict[str, int] = {}

    async for event in stream_iter:
        if event["type"] == "delta":
            content_parts.append(event["content"])
        elif event["type"] == "done":
            finish_reason = event.get("finish_reason", "stop")
            usage = event.get("usage", {})

    full_content = "".join(content_parts)
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model_id,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": full_content},
            "finish_reason": finish_reason,
        }],
        "usage": usage,
    }


async def _sync_chat(
    llm,
    messages: List[Dict],
    req: ChatCompletionRequest,
    completion_id: str,
    created: int,
    model_id: str,
    include_thinking: bool = False,
) -> Dict[str, Any]:
    """Non-streaming chat completion."""
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        partial(
            llm.create_chat_completion,
            messages=messages,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        ),
    )

    # llama-cpp-python returns OpenAI-format already, just patch ids
    response["id"] = completion_id
    response["created"] = created
    response["model"] = model_id
    response["object"] = "chat.completion"

    # Strip <think> tags from the response content
    for choice in response.get("choices", []):
        msg = choice.get("message", {})
        raw_content = msg.get("content", "")
        if raw_content and "<think>" in raw_content:
            parsed = parse_think_tags(raw_content)
            msg["content"] = parsed.content
            if include_thinking and parsed.reasoning:
                msg["reasoning"] = parsed.reasoning

    return response


async def _stream_chat(
    llm,
    messages: List[Dict],
    req: ChatCompletionRequest,
    completion_id: str,
    created: int,
    model_id: str,
    include_thinking: bool = False,
):
    """Streaming chat completion as SSE."""
    loop = asyncio.get_event_loop()

    stream_iter = await loop.run_in_executor(
        None,
        partial(
            llm.create_chat_completion,
            messages=messages,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            stream=True,
        ),
    )

    think_parser = StreamingThinkParser()

    def _next(it):
        try:
            return next(it)
        except StopIteration:
            return None

    def _make_chunk(content: str = "", finish_reason=None):
        return {
            "id": completion_id,
            "created": created,
            "model": model_id,
            "object": "chat.completion.chunk",
            "choices": [{
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }],
        }

    while True:
        chunk = await loop.run_in_executor(None, _next, stream_iter)
        if chunk is None:
            # Flush remaining buffer
            for kind, seg in think_parser.finish():
                if kind == "content" and seg:
                    yield f"data: {json.dumps(_make_chunk(seg))}\n\n"
                elif kind == "thinking" and seg and include_thinking:
                    yield f"data: {json.dumps(_make_chunk(seg))}\n\n"
            break

        delta = chunk.get("choices", [{}])[0].get("delta", {})
        text = delta.get("content") or ""
        finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")

        if text:
            for kind, seg in think_parser.feed(text):
                if kind == "content" and seg:
                    yield f"data: {json.dumps(_make_chunk(seg))}\n\n"
                elif kind == "thinking" and seg and include_thinking:
                    yield f"data: {json.dumps(_make_chunk(seg))}\n\n"

        if finish_reason:
            for kind, seg in think_parser.finish():
                if kind == "content" and seg:
                    yield f"data: {json.dumps(_make_chunk(seg))}\n\n"
                elif kind == "thinking" and seg and include_thinking:
                    yield f"data: {json.dumps(_make_chunk(seg))}\n\n"
            yield f"data: {json.dumps(_make_chunk(finish_reason=finish_reason))}\n\n"
            break

    yield "data: [DONE]\n\n"


# ── POST /v1/completions ────────────────────────────────────────────────────
# Text / FIM completions for inline autocomplete (Copilot-style plugins)

@router.post("/v1/completions")
async def completions(request: CompletionRequest):
    """OpenAI-compatible text completions endpoint with FIM support.

    Used by IDE extensions for inline code autocomplete:
    - ``prompt``: Code before the cursor
    - ``suffix``: Code after the cursor (triggers FIM mode)
    - Response contains the generated text to insert at the cursor position

    Compatible with: Continue.dev, Tabby, Cody, llama.cpp server clients.
    """
    llm, catalog_entry = _resolve_model_and_load(request.model)

    # Build the effective prompt (FIM or plain)
    if request.suffix:
        effective_prompt = _build_fim_prompt(
            request.prompt, request.suffix, catalog_entry.get("family", "")
        )
        # Add FIM middle token as a stop sequence so the model stops filling
        family_lower = (catalog_entry.get("family", "") or "").lower()
        fim_stop = None
        for key, tokens in _FIM_TOKENS.items():
            if key in family_lower:
                # Stop at end-of-text or common terminators
                fim_stop = [tokens.get("suffix", ""), "\n\n\n"]
                break
    else:
        effective_prompt = request.prompt
        fim_stop = None

    # Merge stop sequences
    stop = request.stop or []
    if isinstance(stop, str):
        stop = [stop]
    if fim_stop:
        stop = list(set(stop + fim_stop))
    stop = stop or None

    completion_id = _generate_id("cmpl")
    created = int(time.time())
    model_id = catalog_entry["id"]

    if request.stream:
        return StreamingResponse(
            _stream_completion(
                llm, effective_prompt, request, completion_id, created, model_id, stop
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        return await _sync_completion(
            llm, effective_prompt, request, completion_id, created, model_id, stop
        )


async def _sync_completion(
    llm,
    prompt: str,
    req: CompletionRequest,
    completion_id: str,
    created: int,
    model_id: str,
    stop: Optional[List[str]],
) -> Dict[str, Any]:
    """Non-streaming text completion."""
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        partial(
            llm.create_completion,
            prompt=prompt,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            stop=stop,
            echo=req.echo,
        ),
    )

    # Normalize response to OpenAI format
    text = ""
    if "choices" in response and response["choices"]:
        text = response["choices"][0].get("text", "")

    return {
        "id": completion_id,
        "object": "text_completion",
        "created": created,
        "model": model_id,
        "choices": [
            {
                "text": text,
                "index": 0,
                "logprobs": None,
                "finish_reason": response.get("choices", [{}])[0].get("finish_reason", "stop"),
            }
        ],
        "usage": response.get("usage", {}),
    }


async def _stream_completion(
    llm,
    prompt: str,
    req: CompletionRequest,
    completion_id: str,
    created: int,
    model_id: str,
    stop: Optional[List[str]],
):
    """Streaming text completion as SSE."""
    loop = asyncio.get_event_loop()

    stream_iter = await loop.run_in_executor(
        None,
        partial(
            llm.create_completion,
            prompt=prompt,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            stop=stop,
            stream=True,
        ),
    )

    def _next(it):
        try:
            return next(it)
        except StopIteration:
            return None

    while True:
        chunk = await loop.run_in_executor(None, _next, stream_iter)
        if chunk is None:
            break

        text = chunk.get("choices", [{}])[0].get("text", "")
        finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")

        data = {
            "id": completion_id,
            "object": "text_completion",
            "created": created,
            "model": model_id,
            "choices": [
                {
                    "text": text,
                    "index": 0,
                    "finish_reason": finish_reason,
                }
            ],
        }
        yield f"data: {json.dumps(data)}\n\n"

        if finish_reason:
            break

    yield "data: [DONE]\n\n"
