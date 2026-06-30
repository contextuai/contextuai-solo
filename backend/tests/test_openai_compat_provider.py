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
