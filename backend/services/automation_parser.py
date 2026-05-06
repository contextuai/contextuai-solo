"""
Automation Prompt Parser — regex-based @mention + execution-mode extraction.

Solo-only variant: dropped the optional Claude SDK pass since Solo runs
local models. Sticks to deterministic regex parsing, which is what the
enterprise version falls back to anyway.
"""

import re
from typing import Any, Dict, List, Tuple

from models.automation_models import ExecutionMode

# Match @agent-slug — letters / digits / underscores / hyphens, but no
# trailing hyphen so trailing punctuation doesn't get swallowed.
_PERSONA_RE = re.compile(r"(?<![a-zA-Z0-9.])@([A-Za-z][A-Za-z0-9_-]*[A-Za-z0-9_]|[A-Za-z])")


SEQUENTIAL_KEYWORDS = (
    "then", "after", "afterwards", "next", "followed by",
    "subsequently", "once", "first", "second", "finally",
)

PARALLEL_KEYWORDS = (
    "simultaneously", "at the same time", "concurrently",
    "in parallel", "together", "along with",
)

CONDITIONAL_KEYWORDS = (
    "if", "when", "unless", "in case", "provided that",
    "depending on", "based on", "should",
)


class PromptParser:
    """Parse natural-language automation prompts."""

    def parse(self, prompt: str) -> Dict[str, Any]:
        personas = self._detect_personas(prompt)
        mode = self._detect_execution_mode(prompt)
        return {
            "personas": personas,
            "execution_mode": mode,
            "is_valid": len(personas) > 0,
            "warnings": self._warnings(prompt, personas, mode),
            "suggestions": self._suggestions(prompt, personas, mode),
            "has_conditionals": self._has_conditionals(prompt),
        }

    def _detect_personas(self, prompt: str) -> List[str]:
        seen, ordered = set(), []
        for name in _PERSONA_RE.findall(prompt):
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    def _detect_execution_mode(self, prompt: str) -> str:
        lower = prompt.lower()
        has_seq = any(kw in lower for kw in SEQUENTIAL_KEYWORDS)
        has_par = any(kw in lower for kw in PARALLEL_KEYWORDS)
        if has_seq and not has_par:
            return ExecutionMode.SEQUENTIAL.value
        if has_par and not has_seq:
            return ExecutionMode.PARALLEL.value
        if has_seq and has_par:
            return ExecutionMode.SEQUENTIAL.value
        return ExecutionMode.SMART.value

    def _has_conditionals(self, prompt: str) -> bool:
        lower = prompt.lower()
        return any(kw in lower for kw in CONDITIONAL_KEYWORDS)

    def _warnings(self, prompt: str, personas: List[str], mode: str) -> List[str]:
        out: List[str] = []
        if not personas:
            out.append(
                "No @agents detected. Use @agent_name to reference an agent (e.g. @market-researcher)."
            )
        if len(personas) == 1:
            out.append(
                "Only one agent — consider using direct chat instead of an automation."
            )
        if self._has_conditionals(prompt):
            out.append(
                "Conditional logic detected, but Solo Automations do not branch yet — every step will run."
            )
        if len(prompt) > 1000:
            out.append("Prompt is long. Consider splitting into multiple smaller automations.")
        return out

    def _suggestions(self, prompt: str, personas: List[str], mode: str) -> List[str]:
        out: List[str] = []
        if mode == ExecutionMode.SMART.value and len(personas) > 1:
            out.append(
                "Make execution order explicit using 'then' (sequential) or 'in parallel'."
            )
        if (
            mode == ExecutionMode.SEQUENTIAL.value
            and len(personas) > 1
            and not any(kw in prompt.lower() for kw in ("use ", "pass ", "send "))
        ):
            out.append(
                "Tell Solo how data should flow between steps (e.g. 'use the result from @researcher in @writer')."
            )
        return out

    def split_into_steps(
        self, prompt: str, personas: List[str]
    ) -> List[Dict[str, Any]]:
        """Split a prompt into ordered (persona, instruction) steps via regex.

        Mirrors the enterprise regex fallback. Each ``@mention`` becomes one
        step; everything between this mention and the next is its instruction.
        """
        if not personas:
            return []

        # Find every @mention with its character index, in order.
        matches = list(_PERSONA_RE.finditer(prompt))
        if not matches:
            return []

        steps: List[Dict[str, Any]] = []
        for i, m in enumerate(matches):
            persona = m.group(1)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(prompt)
            chunk = prompt[start:end].strip()
            # Strip leading sequential connectors so the instruction reads cleanly.
            chunk = re.sub(
                r"^(then|next|after(?:wards)?|followed by|and|,|\.)\s+",
                "",
                chunk,
                flags=re.IGNORECASE,
            )
            if chunk:
                steps.append(
                    {
                        "step_number": i + 1,
                        "persona": persona,
                        "instruction": chunk,
                    }
                )
        return steps

    def validate_persona_exists(
        self, persona_name: str, available: List[str]
    ) -> Tuple[bool, str]:
        if persona_name in available:
            return True, f"Agent '@{persona_name}' found"
        # Solo skips Levenshtein lookups for now — the agent library is small
        # enough that exact-match feedback is fine.
        return False, f"Agent '@{persona_name}' not found"


prompt_parser = PromptParser()
