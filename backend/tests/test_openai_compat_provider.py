"""Unit tests for the openai_compat provider plumbing.

Covers the pure-function pieces: provider-prefix parsing, endpoint resolution,
config validation, and sensitive-key masking. End-to-end inference is exercised
manually against a live OpenAI-compatible server (e.g. Ollama's /v1).
"""

import pytest
from pydantic import ValidationError

from services.model_dispatcher import _parse_provider
from services.openai_direct_service import (
    _chat_url,
    _strip_provider_prefix,
    DEFAULT_BASE_URL,
)
from models.cloud_provider_models import (
    CloudProviderCreate,
    CloudProviderType,
    SENSITIVE_KEYS,
)


def test_parse_provider_recognizes_openai_compat():
    provider, clean = _parse_provider("openai_compat:qwen3-coder:480b-cloud")
    assert provider == "openai_compat"
    # only the leading "openai_compat:" is stripped; model ids may contain ":"
    assert clean == "qwen3-coder:480b-cloud"


def test_parse_provider_openai_not_shadowed_by_compat():
    assert _parse_provider("openai:gpt-4o") == ("openai", "gpt-4o")


def test_chat_url_defaults_to_openai():
    assert _chat_url(None) == f"{DEFAULT_BASE_URL}/chat/completions"


def test_chat_url_uses_custom_base_and_trims_slash():
    assert _chat_url("http://localhost:8000/v1/") == "http://localhost:8000/v1/chat/completions"


def test_strip_provider_prefix_handles_both_prefixes():
    assert _strip_provider_prefix("openai_compat:foo") == "foo"
    assert _strip_provider_prefix("openai:gpt-4o") == "gpt-4o"
    assert _strip_provider_prefix("gpt-4o") == "gpt-4o"


def test_openai_compat_requires_base_url():
    with pytest.raises(ValidationError):
        CloudProviderCreate(provider_type="openai_compat", config={})


def test_openai_compat_api_key_optional():
    # base_url present, no api_key → valid (keyless servers are allowed)
    req = CloudProviderCreate(
        provider_type="openai_compat",
        config={"base_url": "http://localhost:8000/v1"},
    )
    assert req.provider_type == CloudProviderType.OPENAI_COMPAT


def test_openai_compat_api_key_is_sensitive():
    assert "api_key" in SENSITIVE_KEYS[CloudProviderType.OPENAI_COMPAT.value]


# ---------------------------------------------------------------------------
# OpenAI dynamic-discovery chat-model filter
# ---------------------------------------------------------------------------

def test_chat_model_filter_keeps_current_chat_models():
    from services.cloud_model_seeder import _is_current_chat_model

    for keep in ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "o1", "o3-mini", "gpt-5.1", "chatgpt-4o-latest"):
        assert _is_current_chat_model(keep), keep


def test_token_field_openai_vs_compat():
    from services.openai_direct_service import _token_limit_field
    # OpenAI host → newer models need max_completion_tokens
    assert _token_limit_field(None) == "max_completion_tokens"
    assert _token_limit_field("https://api.openai.com/v1") == "max_completion_tokens"
    # Compat servers still use classic max_tokens
    assert _token_limit_field("http://localhost:11434/v1") == "max_tokens"
    assert _token_limit_field("http://localhost:8000/v1") == "max_tokens"


def test_reasoning_models_detected():
    from services.openai_direct_service import _is_reasoning_model
    for m in ("gpt-5.5", "gpt-5", "o1", "o1-pro", "o3-mini", "o4-mini"):
        assert _is_reasoning_model(m), m
    for m in ("gpt-4o", "gpt-4.1", "gpt-3.5-turbo"):
        assert not _is_reasoning_model(m), m


def test_sampling_params_omitted_for_openai_reasoning_models():
    from services.openai_direct_service import _sampling_params
    # OpenAI reasoning model → no temperature/top_p (API rejects non-defaults)
    assert _sampling_params(None, "gpt-5.5", 0.7, 1.0) == {}
    # OpenAI non-reasoning → params kept
    assert _sampling_params(None, "gpt-4o", 0.7, 1.0) == {"temperature": 0.7, "top_p": 1.0}
    # Compat server with a gpt-5-ish name → still send params (not OpenAI host)
    assert _sampling_params("http://localhost:8000/v1", "gpt-5.5", 0.7, 1.0) == {
        "temperature": 0.7, "top_p": 1.0,
    }


def test_chat_model_filter_drops_noise_and_snapshots():
    from services.cloud_model_seeder import _is_current_chat_model

    for drop in (
        "gpt-4o-mini-tts",
        "gpt-4o-mini-transcribe",
        "gpt-3.5-turbo-instruct",
        "gpt-4o-mini-search-preview",
        "text-embedding-3-large",
        "chatgpt-image-latest",
        "gpt-4o-2024-05-13",   # dated snapshot collapses to gpt-4o
        "gpt-3.5-turbo-0125",  # dated snapshot
        "whisper-1",
        "dall-e-3",
    ):
        assert not _is_current_chat_model(drop), drop
