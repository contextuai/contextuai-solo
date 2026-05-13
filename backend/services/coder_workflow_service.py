"""
Coder Workflow Service — static multi-agent execution for a Coder project.

Given a project with N roles and a ``workflow_mode``, runs those roles against
a user message and yields normalized SSE events. No LLM-as-router — same
input always fires the same agents in the same order.

SSE event vocabulary
--------------------
workflow_start  — First event. Fields: workflow_mode, roles (summary list).
role_start      — A role is about to run. Fields: role_id, role_kind,
                  display_name, model_id.
role_token      — Streamed token from that role. Fields: role_id, content.
role_done       — Role finished. Fields: role_id, output, usage.
workflow_done   — All roles complete. Fields: total_usage.
error           — Recoverable or fatal error. Fields: error, role_id (opt).

Always ends with ``data: [DONE]\\n\\n``.

Workflow modes
--------------
solo        — Find the enabled role with role_kind == "coder" (or first
              enabled role). Stream its output. One model call.
sequential  — Enabled roles sorted by ``order``. Each role receives chat
              history + user message + all previous roles' outputs prefixed
              with "## DisplayName\\n{output}\\n\\n".  Final answer is a
              markdown document with "## DisplayName" headers per section.
parallel    — Coder role runs first (identified by role_kind == "coder" or
              position 0). After the Coder's output is collected, all other
              enabled roles run concurrently via asyncio.gather. Each receives
              chat_history + user_message + coder output. Outputs streamed
              with role-tagged events as they arrive.
custom      — Treated identically to sequential (user arranged order).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from repositories.coder_agent_role_repository import CoderAgentRoleRepository
from repositories.coder_project_repository import CoderProjectRepository
from services.model_dispatcher import (
    DEFAULT_SENTINEL,
    ProviderUnavailable,
    resolve_default_model,
    stream_chat,
)

logger = logging.getLogger(__name__)

# One asyncio.Lock per project_id prevents two concurrent /run calls on the
# same project from clobbering each other (mirrors LocalModelService pattern).
_project_locks: Dict[str, asyncio.Lock] = {}


def _get_project_lock(project_id: str) -> asyncio.Lock:
    if project_id not in _project_locks:
        _project_locks[project_id] = asyncio.Lock()
    return _project_locks[project_id]


def _fmt_sse(event: Dict[str, Any]) -> str:
    """Serialise an event dict to a single SSE data line."""
    return f"data: {json.dumps(event)}\n\n"


def _sum_usage(acc: Dict[str, int], usage: Dict[str, int]) -> Dict[str, int]:
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        acc[key] = acc.get(key, 0) + usage.get(key, 0)
    return acc


def _role_summary(role: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "role_id": role.get("role_id", ""),
        "role_kind": role.get("role_kind", ""),
        "display_name": role.get("display_name", ""),
        "model_id": role.get("model_id", ""),
    }


class CoderWorkflowService:
    """Static multi-agent execution for a Coder project."""

    def __init__(self, db) -> None:
        self.db = db
        self.project_repo = CoderProjectRepository(db)
        self.role_repo = CoderAgentRoleRepository(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        project_id: str,
        user_message: str,
        chat_history: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        """Execute the project's workflow.  Yields raw SSE lines (strings)."""
        lock = _get_project_lock(project_id)
        async with lock:
            async for chunk in self._run_unlocked(
                project_id, user_message, chat_history or []
            ):
                yield chunk

    async def preview(
        self,
        project_id: str,
    ) -> Dict[str, Any]:
        """Return the execution plan as JSON without making any model calls."""
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            return {"error": f"Project not found: {project_id}"}

        all_roles = await self.role_repo.list_for_project(project_id)
        enabled = [r for r in all_roles if r.get("enabled", True)]

        workflow_mode = project.get("workflow_mode", "solo")
        ordered = self._order_roles(workflow_mode, enabled)

        # Resolve __DEFAULT__ model IDs without making a model call.
        plan_roles = []
        for role in ordered:
            mid = role.get("model_id", DEFAULT_SENTINEL)
            if mid == DEFAULT_SENTINEL:
                try:
                    mid = await resolve_default_model(self.db)
                except ProviderUnavailable:
                    mid = "__DEFAULT__ (unresolved)"
            plan_roles.append({**_role_summary(role), "model_id": mid})

        return {
            "project_id": project_id,
            "workflow_mode": workflow_mode,
            "roles": plan_roles,
            "role_count": len(plan_roles),
        }

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    async def _run_unlocked(
        self,
        project_id: str,
        user_message: str,
        chat_history: List[Dict[str, Any]],
    ) -> AsyncIterator[str]:
        """Core execution — called with the project lock held."""
        # ── Load project + roles ────────────────────────────────────────
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            yield _fmt_sse({"type": "error", "error": f"Project not found: {project_id}"})
            yield "data: [DONE]\n\n"
            return

        all_roles = await self.role_repo.list_for_project(project_id)
        enabled = [r for r in all_roles if r.get("enabled", True)]
        workflow_mode = project.get("workflow_mode", "solo")

        # ── Empty roster fallback ───────────────────────────────────────
        if not enabled:
            enabled = await self._synthesize_fallback_role(project_id, project)
            workflow_mode = "solo"

        ordered = self._order_roles(workflow_mode, enabled)

        # ── Fail-fast: every enabled role must have a model selected ────
        for role in ordered:
            mid = role.get("model_id", "")
            if mid == "":
                display = role.get("display_name") or role.get("role_kind") or "Unknown"
                yield _fmt_sse({
                    "type": "error",
                    "error": (
                        f"Role '{display}' has no model selected. "
                        "Open the Team panel and pick one."
                    ),
                })
                yield "data: [DONE]\n\n"
                return

        # ── workflow_start ──────────────────────────────────────────────
        yield _fmt_sse({
            "type": "workflow_start",
            "workflow_mode": workflow_mode,
            "roles": [_role_summary(r) for r in ordered],
        })

        # ── Dispatch to the correct executor ────────────────────────────
        total_usage: Dict[str, int] = {}
        def _is_usage_sentinel(chunk) -> bool:
            return isinstance(chunk, dict) and chunk.get("_usage") is True

        def _consume(chunk) -> None:
            # Extract usage keys (everything except the _usage flag itself).
            usage = {k: v for k, v in chunk.items() if k != "_usage"}
            _sum_usage(total_usage, usage)

        try:
            if workflow_mode == "solo":
                async for chunk in self._run_solo(ordered, chat_history, user_message):
                    if _is_usage_sentinel(chunk):
                        _consume(chunk)
                    else:
                        yield chunk
            elif workflow_mode in ("sequential", "custom"):
                async for chunk in self._run_sequential(ordered, chat_history, user_message):
                    if _is_usage_sentinel(chunk):
                        _consume(chunk)
                    else:
                        yield chunk
            elif workflow_mode == "parallel":
                async for chunk in self._run_parallel(ordered, chat_history, user_message):
                    if _is_usage_sentinel(chunk):
                        _consume(chunk)
                    else:
                        yield chunk
            else:
                # Unknown mode — fall back to sequential
                logger.warning("Unknown workflow_mode %r — falling back to sequential", workflow_mode)
                async for chunk in self._run_sequential(ordered, chat_history, user_message):
                    if _is_usage_sentinel(chunk):
                        _consume(chunk)
                    else:
                        yield chunk
        except asyncio.CancelledError:
            yield _fmt_sse({"type": "error", "error": "Workflow cancelled by client disconnect"})
            raise

        yield _fmt_sse({"type": "workflow_done", "total_usage": total_usage})
        yield "data: [DONE]\n\n"

    # ------------------------------------------------------------------
    # Solo mode
    # ------------------------------------------------------------------

    async def _run_solo(
        self,
        roles: List[Dict[str, Any]],
        chat_history: List[Dict[str, Any]],
        user_message: str,
    ) -> AsyncIterator[Any]:
        """One role (the Coder or the first enabled)."""
        role = self._find_coder_role(roles) or roles[0]
        async for item in self._stream_role(role, chat_history, user_message, prior_context=""):
            yield item

    # ------------------------------------------------------------------
    # Sequential / custom mode
    # ------------------------------------------------------------------

    async def _run_sequential(
        self,
        roles: List[Dict[str, Any]],
        chat_history: List[Dict[str, Any]],
        user_message: str,
    ) -> AsyncIterator[Any]:
        """Chain roles; each sees all previous outputs in context."""
        prior_context = ""
        for role in roles:
            full_output = ""
            async for item in self._stream_role(role, chat_history, user_message, prior_context):
                if isinstance(item, dict) and item.get("_usage"):
                    yield item
                elif isinstance(item, str):
                    # Check if it's a role_token event to capture text
                    try:
                        evt = json.loads(item[6:])  # strip "data: "
                        if evt.get("type") == "role_token":
                            full_output += evt.get("content", "")
                        elif evt.get("type") == "role_done":
                            full_output = evt.get("output", full_output)
                    except (json.JSONDecodeError, ValueError):
                        pass
                    yield item

            # Append this role's output to the prior context for the next role.
            display_name = role.get("display_name", role.get("role_kind", ""))
            if full_output:
                prior_context += f"## {display_name}\n{full_output}\n\n"

    # ------------------------------------------------------------------
    # Parallel mode
    # ------------------------------------------------------------------

    async def _run_parallel(
        self,
        roles: List[Dict[str, Any]],
        chat_history: List[Dict[str, Any]],
        user_message: str,
    ) -> AsyncIterator[Any]:
        """Coder first, then all others concurrently."""
        coder = self._find_coder_role(roles)
        if coder is None:
            coder = roles[0]
        others = [r for r in roles if r.get("role_id") != coder.get("role_id")]

        # ── Coder runs first ────────────────────────────────────────────
        coder_output = ""
        async for item in self._stream_role(coder, chat_history, user_message, prior_context=""):
            if isinstance(item, dict) and item.get("_usage"):
                yield item
            elif isinstance(item, str):
                try:
                    evt = json.loads(item[6:])
                    if evt.get("type") == "role_token":
                        coder_output += evt.get("content", "")
                    elif evt.get("type") == "role_done":
                        coder_output = evt.get("output", coder_output)
                except (json.JSONDecodeError, ValueError):
                    pass
                yield item

        if not others:
            return

        # ── Others run concurrently ────────────────────────────────────
        # Collect all events in memory per role then interleave.
        # This ensures Coder's role_done strictly precedes the others.
        async def _collect_role(role: Dict[str, Any]) -> List[Any]:
            items: List[Any] = []
            async for item in self._stream_role(
                role, chat_history, user_message, prior_context=coder_output
            ):
                items.append(item)
            return items

        results = await asyncio.gather(
            *[_collect_role(r) for r in others],
            return_exceptions=True,
        )

        for role, role_items in zip(others, results):
            if isinstance(role_items, Exception):
                yield _fmt_sse({
                    "type": "error",
                    "role_id": role.get("role_id", ""),
                    "error": str(role_items),
                })
                continue
            for item in role_items:
                yield item

    # ------------------------------------------------------------------
    # Role streaming primitive
    # ------------------------------------------------------------------

    async def _stream_role(
        self,
        role: Dict[str, Any],
        chat_history: List[Dict[str, Any]],
        user_message: str,
        prior_context: str,
    ) -> AsyncIterator[Any]:
        """Stream a single role's inference. Yields SSE strings + usage sentinel dicts."""
        role_id = role.get("role_id", "")
        role_kind = role.get("role_kind", "")
        display_name = role.get("display_name", role_kind)
        model_id = role.get("model_id", DEFAULT_SENTINEL)
        temperature = float(role.get("temperature", 0.7))
        max_tokens = int(role.get("max_tokens", 4096))
        system_prompt = role.get("system_prompt", "")

        yield _fmt_sse({
            "type": "role_start",
            "role_id": role_id,
            "role_kind": role_kind,
            "display_name": display_name,
            "model_id": model_id,
        })

        # Build the message list for this role.
        messages = self._build_messages(
            system_prompt=system_prompt,
            chat_history=chat_history,
            user_message=user_message,
            prior_context=prior_context,
        )

        full_output: List[str] = []
        usage: Dict[str, int] = {}

        try:
            async for event in stream_chat(
                model_id,
                messages,
                db=self.db,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                if event["type"] == "delta":
                    content = event.get("content", "")
                    full_output.append(content)
                    yield _fmt_sse({
                        "type": "role_token",
                        "role_id": role_id,
                        "role_kind": role_kind,
                        "content": content,
                    })
                elif event["type"] == "done":
                    usage = event.get("usage", {})

        except asyncio.CancelledError:
            raise
        except ProviderUnavailable as exc:
            yield _fmt_sse({
                "type": "error",
                "role_id": role_id,
                "error": str(exc),
            })
            return
        except Exception as exc:
            logger.exception("Role %r failed: %s", role_id, exc)
            yield _fmt_sse({
                "type": "error",
                "role_id": role_id,
                "error": f"Role execution failed: {exc}",
            })
            return

        output_text = "".join(full_output)
        yield _fmt_sse({
            "type": "role_done",
            "role_id": role_id,
            "output": output_text,
            "usage": usage,
        })
        # Sentinel for usage accumulation in the parent generator
        yield {"_usage": True, **usage}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _order_roles(workflow_mode: str, roles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return roles sorted by their ``order`` field."""
        return sorted(roles, key=lambda r: r.get("order", 0))

    @staticmethod
    def _find_coder_role(roles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Return the first role with role_kind == 'coder', or None."""
        for r in roles:
            if r.get("role_kind") == "coder":
                return r
        return None

    @staticmethod
    def _build_messages(
        system_prompt: str,
        chat_history: List[Dict[str, Any]],
        user_message: str,
        prior_context: str,
    ) -> List[Dict[str, Any]]:
        """Build the OpenAI-format messages list for a role."""
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        # Include chat history (skip system messages — already prepended above).
        for msg in chat_history:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg.get("content", "")})

        # Build the user turn: prepend prior roles' context if any.
        user_content = user_message
        if prior_context:
            user_content = f"{prior_context}\n---\n\n{user_message}"

        messages.append({"role": "user", "content": user_content})
        return messages

    async def _synthesize_fallback_role(
        self,
        project_id: str,
        project: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Return an inline Coder role when the project has zero enabled roles.

        If the project document has no model_id set, the returned role will
        have model_id == "" so the fail-fast validator in ``_run_unlocked``
        catches it and emits a clear error instead of silently falling back
        to a default model.
        """
        model_id = project.get("model_id") or ""
        return [{
            "role_id": f"{project_id}-fallback",
            "project_id": project_id,
            "role_kind": "coder",
            "display_name": "Coder",
            "system_prompt": (
                "You are an expert software engineer who writes clean, "
                "well-documented, production-quality code."
            ),
            "model_id": model_id,
            "temperature": 0.7,
            "max_tokens": 4096,
            "enabled": True,
            "order": 0,
        }]
