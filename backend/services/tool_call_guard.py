"""
Grammar-Locked Local Tool Calling & Loop Circuit Breaker (SPEC-29).

Provides:
1. ``schema_to_gbnf(tools)``: Compiles a list of tool schemas into a GBNF grammar
   that constrains local GGUF generation to valid JSON tool calls.
2. ``parse_and_repair_tool_call(raw_text, allowed_tools=None)``: Extracts and
   repairs malformed tool call JSON (markdown fences, ``<tool_call>`` tags,
   trailing commas, single quotes) and normalizes to ``{"tool": ..., "arguments": {...}}``.
3. ``ToolLoopCircuitBreaker``: Detects repeated identical ``(tool_name, canonical_args)``
   invocations or runaway tool turns and trips cleanly before infinite loops occur.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _extract_tool_name(tool_def: Dict[str, Any]) -> str:
    if "function" in tool_def and isinstance(tool_def["function"], dict):
        return str(tool_def["function"].get("name") or "").strip()
    return str(tool_def.get("name") or tool_def.get("tool") or "").strip()


def schema_to_gbnf(tools: List[Dict[str, Any]]) -> str:
    """Generate a GBNF grammar constraining output to ``{"tool": "<name>", "arguments": {...}}``."""
    names = [_extract_tool_name(t) for t in (tools or [])]
    names = [n for n in names if n]

    if names:
        escaped_names = " | ".join(f'"\\"{n}\\""' for n in names)
        tool_name_rule = f"tool-name ::= {escaped_names}"
    else:
        tool_name_rule = "tool-name ::= string"

    grammar = f"""root ::= ws "{{" ws "\\"tool\\"" ws ":" ws tool-name ws "," ws "\\"arguments\\"" ws ":" ws object ws "}}" ws
{tool_name_rule}
object ::= "{{" ws ( pair ( ws "," ws pair )* )? ws "}}"
pair ::= string ws ":" ws value
array ::= "[" ws ( value ( ws "," ws value )* )? ws "]"
value ::= string | number | object | array | "true" | "false" | "null"
string ::= "\\"" ( [^"\\\\\\x7F\\x00-\\x1F] | "\\\\" ( ["\\\\/bfnrt] | "u" [0-9a-fA-F]{{4}} ) )* "\\""
number ::= ("-"? ([0-9] | [1-9] [0-9]*)) ("." [0-9]+)? ([eE] [-+]? [0-9]+)?
ws ::= ([ \\t\\n\\r])*
"""
    return grammar.strip()


_TOOL_CALL_TAG_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _extract_candidate_json(raw_text: str) -> str:
    text = (raw_text or "").strip()
    m_tag = _TOOL_CALL_TAG_RE.search(text)
    if m_tag:
        return m_tag.group(1).strip()

    m_fence = _CODE_FENCE_RE.search(text)
    if m_fence:
        return m_fence.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _try_parse_dict(candidate: str) -> Optional[Dict[str, Any]]:
    if not candidate:
        return None

    # 1. Direct JSON parse
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 2. Repair trailing commas
    repaired = _TRAILING_COMMA_RE.sub(r"\1", candidate)
    try:
        parsed = json.loads(repaired)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 3. Python literal eval for single-quoted dicts
    try:
        parsed = ast.literal_eval(repaired)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    return None


def parse_and_repair_tool_call(
    raw_text: str,
    allowed_tools: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Extract, repair, and validate a structured tool call from local model output (SPEC-29).

    Returns ``{"tool": "<name>", "arguments": {...}}`` or ``None`` if no valid
    tool call is present or if the tool is not in ``allowed_tools``.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    candidate = _extract_candidate_json(raw_text)
    obj = _try_parse_dict(candidate)
    if not isinstance(obj, dict):
        return None

    # Support both {"tool": "...", "arguments": {...}} and {"name": "...", "arguments": {...}}
    tool_name = obj.get("tool") or obj.get("name")
    if not tool_name or not isinstance(tool_name, str):
        return None
    tool_name = tool_name.strip()

    if allowed_tools is not None and tool_name not in allowed_tools:
        logger.warning(
            "Rejected tool call %r (not in allowed_tools=%s)", tool_name, allowed_tools
        )
        return None

    args = obj.get("arguments")
    if args is None:
        args = obj.get("parameters") or {}
    if isinstance(args, str):
        parsed_args = _try_parse_dict(args)
        args = parsed_args if isinstance(parsed_args, dict) else {}
    elif not isinstance(args, dict):
        args = {}

    return {
        "tool": tool_name,
        "arguments": args,
    }


class ToolLoopCircuitBreaker:
    """Prevents infinite tool-calling loops on small local models (SPEC-29)."""

    def __init__(self, max_identical: int = 3, max_total: int = 8):
        self.max_identical = max(1, int(max_identical))
        self.max_total = max(1, int(max_total))
        self._counts: Counter = Counter()
        self.total_calls: int = 0
        self.is_tripped: bool = False
        self.trip_reason: Optional[str] = None

    @staticmethod
    def _canonical_key(tool_name: str, arguments: Any) -> str:
        try:
            canonical_args = json.dumps(arguments or {}, sort_keys=True, default=str)
        except Exception:
            canonical_args = str(arguments)
        return f"{tool_name.strip()}::{canonical_args}"

    def record_call(self, tool_name: str, arguments: Any = None) -> Dict[str, Any]:
        """Record a tool call and return whether execution is allowed or tripped."""
        key = self._canonical_key(tool_name, arguments)
        self._counts[key] += 1
        self.total_calls += 1
        identical_count = self._counts[key]

        if identical_count >= self.max_identical:
            self.is_tripped = True
            self.trip_reason = (
                f"Tool '{tool_name}' called {identical_count} times with identical arguments"
            )
            result = {
                "allowed": False,
                "tripped": True,
                "reason": self.trip_reason,
                "identical_count": identical_count,
                "total_count": self.total_calls,
            }
        elif self.total_calls >= self.max_total:
            self.is_tripped = True
            self.trip_reason = (
                f"Exceeded maximum tool calls per turn ({self.max_total})"
            )
            result = {
                "allowed": False,
                "tripped": True,
                "reason": self.trip_reason,
                "identical_count": identical_count,
                "total_count": self.total_calls,
            }
        else:
            result = {
                "allowed": True,
                "tripped": False,
                "reason": None,
                "identical_count": identical_count,
                "total_count": self.total_calls,
            }

        try:
            from models.audit_models import AuditAction, AuditSeverity
            from services.audit_service import audit_log_sync

            audit_log_sync(
                AuditAction.TOOL_EXECUTED,
                resource_type="tool",
                resource_id=tool_name,
                severity=AuditSeverity.WARNING if result["tripped"] else AuditSeverity.INFO,
                details={
                    "allowed": result["allowed"],
                    "tripped": result["tripped"],
                    "reason": result["reason"],
                    "identical_count": result["identical_count"],
                    "total_count": result["total_count"],
                },
            )
        except Exception:
            pass

        return result

    def check(self, tool_name: str, arguments: Any = None) -> bool:
        """Record call and return True if allowed, False if circuit breaker tripped."""
        return bool(self.record_call(tool_name, arguments)["allowed"])

    def reset(self) -> None:
        """Reset all recorded call counts and trip state."""
        self._counts.clear()
        self.total_calls = 0
        self.is_tripped = False
        self.trip_reason = None
