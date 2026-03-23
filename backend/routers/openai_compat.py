"""
OpenAI-Compatible API Router

Exposes ``/v1/chat/completions`` and ``/v1/models`` so external tools
(Aider, Continue.dev, Cursor, OpenCode, any OpenAI SDK client) can use
Solo's local GGUF models as a drop-in replacement for the OpenAI API.

Usage:
    aider --openai-api-base http://localhost:18741/v1 --model qwen3.5-9b
    curl http://localhost:18741/v1/chat/completions \
      -H "Content-Type: application/json" \
      -d '{"model":"qwen3.5-9b","messages":[{"role":"user","content":"hello"}]}'
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


def _generate_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


# ── GET /v1/models ───────────────────────────────────────────────────────────

@router.get("/v1/models")
async def list_models():
    """List installed local models in OpenAI format."""
    from services.model_manager import model_manager

    models = []
    for entry in LOCAL_MODEL_CATALOG:
        if model_manager.is_installed(entry["id"]):
            models.append({
                "id": entry["id"],
                "object": "model",
                "created": 0,
                "owned_by": entry.get("provider", "local"),
                "permission": [],
                "root": entry["id"],
                "parent": None,
            })

    return {"object": "list", "data": models}


# ── POST /v1/chat/completions ────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, http_request: Request):
    """OpenAI-compatible chat completions endpoint."""
    if not LLAMA_CPP_AVAILABLE:
        raise HTTPException(503, "llama-cpp-python is not installed")

    include_thinking = http_request.query_params.get("include_thinking", "").lower() in ("true", "1", "yes")

    # Resolve model
    catalog_entry = _resolve_model(request.model)
    if not catalog_entry:
        raise HTTPException(404, f"Model '{request.model}' not found in catalog")

    # Resolve model path
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
