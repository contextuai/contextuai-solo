"""
Think-Tag Parser for Local Models (Qwen 3/3.5, Gemma 4)

Models that support chain-of-thought reasoning emit thinking blocks
using model-specific delimiters:

- **Qwen 3 / 3.5**: ``<think>...</think>``
- **Gemma 4**: ``<|channel>thought\\n...<channel|>``

This module provides utilities to:

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
_GEMMA4_THINK_RE = re.compile(r"<\|channel>thought\n(.*?)<channel\|>", re.DOTALL)


@dataclass
class ParsedResponse:
    """Result of parsing a complete response."""
    content: str
    reasoning: str  # concatenated thinking blocks (empty string if none)


def parse_think_tags(text: str) -> ParsedResponse:
    """Strip thinking blocks from *text* (supports Qwen and Gemma 4 formats).

    Returns a ``ParsedResponse`` with the cleaned content and the
    extracted reasoning (all think blocks concatenated with newlines).
    """
    blocks: List[str] = []

    # Qwen format: <think>...</think>
    for m in _THINK_RE.finditer(text):
        block = m.group(1).strip()
        if block:
            blocks.append(block)
    text = _THINK_RE.sub("", text)

    # Gemma 4 format: <|channel>thought\n...<channel|>
    for m in _GEMMA4_THINK_RE.finditer(text):
        block = m.group(1).strip()
        if block:
            blocks.append(block)
    text = _GEMMA4_THINK_RE.sub("", text)

    return ParsedResponse(content=text.strip(), reasoning="\n\n".join(blocks))


# ── Streaming (chunk-by-chunk) ─────────────────────────────────────────────

# Tag pairs: (open_tag, close_tag)
_QWEN_OPEN = "<think>"
_QWEN_CLOSE = "</think>"
_GEMMA4_OPEN = "<|channel>thought\n"
_GEMMA4_CLOSE = "<channel|>"


@dataclass
class StreamingThinkParser:
    """Stateful parser for streaming chunks.

    Feed chunks via :meth:`feed` which returns a list of classified
    segments: ``("thinking", text)`` or ``("content", text)``.

    Handles partial tag boundaries across chunk boundaries by buffering
    potential tag prefixes.  Supports both Qwen (``<think>``/``</think>``)
    and Gemma 4 (``<|channel>thought\\n``/``<channel|>``) formats.
    """

    _inside_think: bool = field(default=False, repr=False)
    _buffer: str = field(default="", repr=False)
    _close_tag: str = field(default="", repr=False)  # which close tag to look for

    def feed(self, text: str) -> List[Tuple[str, str]]:
        """Process *text* and return classified segments."""
        self._buffer += text
        return self._flush()

    def finish(self) -> List[Tuple[str, str]]:
        """Flush any remaining buffered text at end-of-stream."""
        if not self._buffer:
            return []
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
                close_tag = self._close_tag
                end_idx = self._buffer.find(close_tag)
                if end_idx != -1:
                    thinking_text = self._buffer[:end_idx]
                    if thinking_text:
                        segments.append(("thinking", thinking_text))
                    self._buffer = self._buffer[end_idx + len(close_tag):]
                    self._inside_think = False
                    self._close_tag = ""
                else:
                    partial = self._partial_tag_suffix(self._buffer, close_tag)
                    if partial > 0:
                        safe = self._buffer[:-partial]
                        if safe:
                            segments.append(("thinking", safe))
                        self._buffer = self._buffer[-partial:]
                    else:
                        segments.append(("thinking", self._buffer))
                        self._buffer = ""
                    break
            else:
                # Look for whichever open tag appears first
                qwen_idx = self._buffer.find(_QWEN_OPEN)
                gemma_idx = self._buffer.find(_GEMMA4_OPEN)

                # Pick the earliest match
                open_tag = None
                start_idx = -1
                if qwen_idx != -1 and (gemma_idx == -1 or qwen_idx <= gemma_idx):
                    open_tag = _QWEN_OPEN
                    start_idx = qwen_idx
                elif gemma_idx != -1:
                    open_tag = _GEMMA4_OPEN
                    start_idx = gemma_idx

                if open_tag is not None:
                    content_text = self._buffer[:start_idx]
                    if content_text:
                        segments.append(("content", content_text))
                    self._buffer = self._buffer[start_idx + len(open_tag):]
                    self._inside_think = True
                    self._close_tag = _QWEN_CLOSE if open_tag == _QWEN_OPEN else _GEMMA4_CLOSE
                else:
                    # Check for partial prefixes of either open tag
                    partial = max(
                        self._partial_tag_suffix(self._buffer, _QWEN_OPEN),
                        self._partial_tag_suffix(self._buffer, _GEMMA4_OPEN),
                    )
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
