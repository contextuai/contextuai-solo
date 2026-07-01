"""
Best-effort cost estimation for cloud LLM calls.

Providers don't return a per-call price and there's no pricing API, so this is
a maintained table of approximate USD rates per 1,000,000 tokens (input,
output). Matched by longest model-id prefix. Unknown models (and local /
self-hosted ones) return 0.0 — the caller shows tokens but no dollar figure.

⚠️ Rates approximate (2026) and WILL drift — update when providers change
pricing or when a new family ships (e.g. gpt-5.x below is a placeholder until
official pricing is known).
"""

from __future__ import annotations

from typing import Dict, Tuple

# model-id prefix -> (input $/1M, output $/1M)
_PRICES: Dict[str, Tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1-mini": (1.10, 4.40),
    "o1": (15.00, 60.00),
    "o3-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    # gpt-5.x: placeholder — official pricing unknown; update when published.
    # Left out deliberately so it reads as "unknown" ($0) rather than wrong.

    # Anthropic
    "claude-opus": (15.00, 75.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-haiku": (0.80, 4.00),

    # Google
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-2.0-pro": (1.25, 5.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
}


def _strip_prefix(model_id: str) -> str:
    for p in ("openai_compat:", "openai:", "anthropic:", "google:", "bedrock:"):
        if model_id.startswith(p):
            return model_id[len(p):]
    return model_id


def estimate_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Approximate USD cost for a call. Returns 0.0 when the model is unknown
    (or local / self-hosted), in which case the UI shows tokens only."""
    name = _strip_prefix(model_id or "").lower()
    # Longest matching prefix wins (so gpt-4o-mini beats gpt-4o).
    match = max(
        (p for p in _PRICES if name.startswith(p)),
        key=len,
        default=None,
    )
    if not match:
        return 0.0
    in_rate, out_rate = _PRICES[match]
    return round(
        (prompt_tokens / 1_000_000) * in_rate
        + (completion_tokens / 1_000_000) * out_rate,
        6,
    )
