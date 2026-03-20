"""
Think-Tag Parser for Qwen 3 / 3.5 Models

Qwen 3 and 3.5 models emit ``<think>...</think>`` tags containing
chain-of-thought reasoning.  This module provides utilities to:

1. **Non-streaming**: strip think blocks from completed text and return
   the reasoning separately.
2. **Streaming**: a stateful parser that classifies each incoming text
   chunk as either *thinking* or *content*, handling partial tag
   boundaries across chunk boundaries.
"""

import re
from dataclasses import dataclass, field
from typing import List, Tuple


# ── Non-streaming (complete text) ──────────────────────────────────────────

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


@dataclass
class ParsedResponse:
    """Result of parsing a complete response."""
    content: str
    reasoning: str  # concatenated thinking blocks (empty string if none)


def parse_think_tags(text: str) -> ParsedResponse:
    """Strip ``<think>…</think>`` blocks from *text*.

    Returns a ``ParsedResponse`` with the cleaned content and the
    extracted reasoning (all think blocks concatenated with newlines).
    """
    blocks: List[str] = []
    for m in _THINK_RE.finditer(text):
        block = m.group(1).strip()
        if block:
            blocks.append(block)

    content = _THINK_RE.sub("", text).strip()
    return ParsedResponse(content=content, reasoning="\n\n".join(blocks))


# ── Streaming (chunk-by-chunk) ─────────────────────────────────────────────

@dataclass
class StreamingThinkParser:
    """Stateful parser for streaming chunks.

    Feed chunks via :meth:`feed` which returns a list of classified
    segments: ``("thinking", text)`` or ``("content", text)``.

    Handles partial ``<think>`` / ``</think>`` tags that straddle chunk
    boundaries by buffering potential tag prefixes.
    """

    _inside_think: bool = field(default=False, repr=False)
    _buffer: str = field(default="", repr=False)

    def feed(self, text: str) -> List[Tuple[str, str]]:
        """Process *text* and return classified segments."""
        self._buffer += text
        return self._flush()

    def finish(self) -> List[Tuple[str, str]]:
        """Flush any remaining buffered text at end-of-stream."""
        if not self._buffer:
            return []
        # Whatever's left is emitted as-is in the current mode
        remaining = self._buffer
        self._buffer = ""
        if remaining:
            kind = "thinking" if self._inside_think else "content"
            return [(kind, remaining)]
        return []

    # ── internals ──────────────────────────────────────────────────

    def _flush(self) -> List[Tuple[str, str]]:
        segments: List[Tuple[str, str]] = []

        while self._buffer:
            if self._inside_think:
                # Look for </think>
                end_idx = self._buffer.find("</think>")
                if end_idx != -1:
                    # Emit thinking up to the tag
                    thinking_text = self._buffer[:end_idx]
                    if thinking_text:
                        segments.append(("thinking", thinking_text))
                    self._buffer = self._buffer[end_idx + len("</think>"):]
                    self._inside_think = False
                else:
                    # Check if buffer ends with a partial </think> prefix
                    partial = self._partial_tag_suffix(self._buffer, "</think>")
                    if partial > 0:
                        # Emit everything except the potential partial tag
                        safe = self._buffer[:-partial]
                        if safe:
                            segments.append(("thinking", safe))
                        self._buffer = self._buffer[-partial:]
                    else:
                        # No tag boundary — emit all as thinking
                        segments.append(("thinking", self._buffer))
                        self._buffer = ""
                    break
            else:
                # Look for <think>
                start_idx = self._buffer.find("<think>")
                if start_idx != -1:
                    # Emit content before the tag
                    content_text = self._buffer[:start_idx]
                    if content_text:
                        segments.append(("content", content_text))
                    self._buffer = self._buffer[start_idx + len("<think>"):]
                    self._inside_think = True
                else:
                    # Check for partial <think> prefix
                    partial = self._partial_tag_suffix(self._buffer, "<think>")
                    if partial > 0:
                        safe = self._buffer[:-partial]
                        if safe:
                            segments.append(("content", safe))
                        self._buffer = self._buffer[-partial:]
                    else:
                        segments.append(("content", self._buffer))
                        self._buffer = ""
                    break

        return segments

    @staticmethod
    def _partial_tag_suffix(text: str, tag: str) -> int:
        """Return the length of the longest suffix of *text* that is a
        prefix of *tag*, or 0 if none match.

        E.g. text="abc<thi", tag="<think>" → returns 4 (for "<thi").
        """
        max_check = min(len(text), len(tag) - 1)
        for length in range(max_check, 0, -1):
            if text.endswith(tag[:length]):
                return length
        return 0
