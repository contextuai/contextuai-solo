"""Tests for best-effort cloud cost estimation."""

from services.model_pricing import estimate_cost


def test_gpt_4o_cost():
    # 2.50/1M input + 10/1M output → 1000 in + 1000 out = 0.0025 + 0.01
    assert estimate_cost("openai:gpt-4o", 1000, 1000) == 0.0125


def test_longest_prefix_wins():
    # gpt-4o-mini must not be priced as gpt-4o
    assert estimate_cost("openai:gpt-4o-mini", 1000, 1000) == round(
        0.15 / 1000 + 0.60 / 1000, 6
    )


def test_anthropic_and_google_priced():
    assert estimate_cost("anthropic:claude-sonnet-4-6", 1000, 1000) == round(
        3.0 / 1000 + 15.0 / 1000, 6
    )
    assert estimate_cost("google:gemini-2.0-flash", 1000, 1000) > 0


def test_unknown_and_local_are_zero():
    # gpt-5.x has no published pricing yet → unknown → 0
    assert estimate_cost("openai:gpt-5.5", 1000, 1000) == 0.0
    # local / self-hosted → free
    assert estimate_cost("local:gemma4-e4b", 1000, 1000) == 0.0
    assert estimate_cost("ollama:qwen3-coder:480b-cloud", 1000, 1000) == 0.0


def test_zero_tokens_zero_cost():
    assert estimate_cost("openai:gpt-4o", 0, 0) == 0.0
