"""
OpenAI-Compatible API Router

Exposes ``/v1/chat/completions``, ``/v1/completions``, and ``/v1/models``
so external tools (Aider, Continue.dev, Cursor, Cody, Tabby, any OpenAI SDK
client) can use Solo's local GGUF models as a drop-in replacement.

Chat completions:
    curl http://localhost:18741/v1/chat/completions \
      -d '{"model":"qwen2.5-7b","messages":[{"role":"user","content":"hello"}]}'

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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.local_model_service import local_model_service, LLAMA_CPP_AVAILABLE
from services.model_catalog import LOCAL_MODEL_CATALOG
from services.think_tag_parser import parse_think_tags, StreamingThinkParser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["openai-compat"])


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
async def list_models():
    """List installed local models in OpenAI format.

    Includes both catalog models and manually-added GGUF files so IDE
    extensions can discover everything available.
    """
    from services.model_manager import model_manager

    models = []
    seen_ids = set()

    # Catalog models
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

    return {"object": "list", "data": models}


# ── POST /v1/chat/completions ────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, http_request: Request):
    """OpenAI-compatible chat completions endpoint."""
    include_thinking = http_request.query_params.get("include_thinking", "").lower() in ("true", "1", "yes")

    llm, catalog_entry = _resolve_model_and_load(request.model)

    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    completion_id = _generate_id()
    created = int(time.time())

    if request.stream:
        return StreamingResponse(
            _stream_chat(llm, messages, request, completion_id, created, catalog_entry["id"], include_thinking),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        return await _sync_chat(llm, messages, request, completion_id, created, catalog_entry["id"], include_thinking)


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
