"""Tests for Phase 4 PR 8 — saved cloud-provider API keys driving inference.

Covers:
- ``CloudProviderService.get_credentials`` returns the unmasked config or None.
- The credentials cache is invalidated on save.
- ``automation_executor._call_model`` raises a clear error when no key is
  saved, and dispatches to ``AnthropicDirectService`` (mocked) when one is.
- ``cloud_model_seeder.sync_cloud_models_to_db`` seeds rows for a connected
  Anthropic provider and skips when none exists.
- ``UniversalModelAdapter.from_saved_credentials`` constructs with explicit
  AWS creds when a bedrock row is present.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from services.cloud_provider_service import CloudProviderService


# ---------------------------------------------------------------------------
# Helper to ensure database.get_database returns the test db_proxy
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def patched_db(db_proxy):
    """Patch the global ``database.get_database`` to return ``db_proxy``."""
    import database as _database

    async def _fake_get_database():
        return db_proxy

    original_get_database = _database.get_database
    original_async_db = _database._async_db
    _database.get_database = _fake_get_database
    _database._async_db = db_proxy
    try:
        yield db_proxy
    finally:
        _database.get_database = original_get_database
        _database._async_db = original_async_db


# ---------------------------------------------------------------------------
# Reset the module-level credentials cache between tests
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_cache():
    from services import cloud_provider_service as cps_module

    cps_module._creds_cache.clear()
    yield
    cps_module._creds_cache.clear()


# ---------------------------------------------------------------------------
# get_credentials — basic lookup
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_credentials_returns_unmasked_after_save(db_proxy):
    svc = CloudProviderService(db_proxy)

    from models.cloud_provider_models import CloudProviderCreate, CloudProviderType

    await svc.create_or_update(
        CloudProviderCreate(
            provider_type=CloudProviderType.ANTHROPIC,
            display_name="My Anthropic",
            config={"api_key": "sk-ant-real-secret"},
        )
    )

    creds = await svc.get_credentials("anthropic")
    assert creds is not None
    # Unmasked!
    assert creds["api_key"] == "sk-ant-real-secret"


@pytest.mark.asyncio
async def test_get_credentials_returns_none_when_missing(db_proxy):
    svc = CloudProviderService(db_proxy)
    creds = await svc.get_credentials("nonexistent")
    assert creds is None


@pytest.mark.asyncio
async def test_cache_invalidated_on_create_or_update(db_proxy):
    svc = CloudProviderService(db_proxy)
    from models.cloud_provider_models import CloudProviderCreate, CloudProviderType

    await svc.create_or_update(
        CloudProviderCreate(
            provider_type=CloudProviderType.OPENAI,
            config={"api_key": "key-v1"},
        )
    )
    creds1 = await svc.get_credentials("openai")
    assert creds1 == {"api_key": "key-v1"}

    # Save a new value — the old cache entry must be invalidated.
    await svc.create_or_update(
        CloudProviderCreate(
            provider_type=CloudProviderType.OPENAI,
            config={"api_key": "key-v2"},
        )
    )
    creds2 = await svc.get_credentials("openai")
    assert creds2 == {"api_key": "key-v2"}


# ---------------------------------------------------------------------------
# automation_executor._call_model — Anthropic dispatch
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_call_model_anthropic_without_key_raises(patched_db):
    from services.automation_executor import AutomationExecutor

    exec_ = AutomationExecutor()
    with pytest.raises(RuntimeError) as excinfo:
        await exec_._call_model(
            "anthropic:claude-sonnet-4-6",
            "test prompt",
            system_prompt="",
        )
    assert "Anthropic API key not configured" in str(excinfo.value)


@pytest.mark.asyncio
async def test_call_model_anthropic_with_key_dispatches(patched_db):
    db_proxy = patched_db
    """With a saved key, _call_model invokes AnthropicDirectService.

    We mock httpx.AsyncClient.post inline and assert the URL + headers + body.
    """
    # Save a key
    svc = CloudProviderService(db_proxy)
    from models.cloud_provider_models import CloudProviderCreate, CloudProviderType

    await svc.create_or_update(
        CloudProviderCreate(
            provider_type=CloudProviderType.ANTHROPIC,
            config={"api_key": "sk-ant-test-key"},
        )
    )

    # Mock httpx response
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "id": "msg_x",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello from Claude"}],
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 5, "output_tokens": 4},
    }

    captured = {}

    async def fake_post(self, url, *args, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return fake_response

    with patch("httpx.AsyncClient.post", new=fake_post):
        from services.automation_executor import AutomationExecutor

        result = await AutomationExecutor()._call_model(
            "anthropic:claude-sonnet-4-6",
            "say hi",
            system_prompt="You are helpful.",
        )

    assert result == "Hello from Claude"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-test-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    body = captured["json"]
    # The "anthropic:" prefix is stripped before sending.
    assert body["model"] == "claude-sonnet-4-6"
    assert body["max_tokens"] == 2048
    assert body["messages"] == [{"role": "user", "content": "say hi"}]
    assert body["system"] == "You are helpful."


# ---------------------------------------------------------------------------
# Cloud model seeder
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_cloud_models_seeds_anthropic_when_connected(db_proxy):
    from services.cloud_model_seeder import (
        ANTHROPIC_MODELS,
        sync_cloud_models_to_db,
    )

    # Insert a connected anthropic provider row directly.
    await db_proxy["cloud_providers"].insert_one(
        {
            "provider_id": "p1",
            "provider_type": "anthropic",
            "display_name": "Anthropic",
            "connected": True,
            "config": {"api_key": "sk-ant-x"},
        }
    )

    seeded = await sync_cloud_models_to_db(db_proxy)
    assert seeded == len(ANTHROPIC_MODELS) == 3

    # Each catalog entry produced a row.
    for short_id, _name, _desc in ANTHROPIC_MODELS:
        doc = await db_proxy["models"].find_one({"_id": f"anthropic:{short_id}"})
        assert doc is not None
        assert doc["provider"] == "Anthropic"
        assert doc["model_metadata"]["provider_type"] == "anthropic"


@pytest.mark.asyncio
async def test_sync_cloud_models_skips_when_no_provider(db_proxy):
    from services.cloud_model_seeder import sync_cloud_models_to_db

    seeded = await sync_cloud_models_to_db(db_proxy)
    assert seeded == 0

    # Nothing seeded.
    count = await db_proxy["models"].count_documents({})
    assert count == 0


@pytest.mark.asyncio
async def test_sync_cloud_models_skips_when_provider_disconnected(db_proxy):
    from services.cloud_model_seeder import sync_cloud_models_to_db

    await db_proxy["cloud_providers"].insert_one(
        {
            "provider_id": "p1",
            "provider_type": "anthropic",
            "display_name": "Anthropic",
            "connected": False,
            "config": {"api_key": "sk-ant-x"},
        }
    )

    seeded = await sync_cloud_models_to_db(db_proxy)
    assert seeded == 0


# ---------------------------------------------------------------------------
# UniversalModelAdapter.from_saved_credentials
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_universal_adapter_from_saved_credentials_uses_explicit_creds(db_proxy):
    """When a bedrock row exists, the adapter is built with explicit creds."""
    await db_proxy["cloud_providers"].insert_one(
        {
            "provider_id": "p1",
            "provider_type": "bedrock",
            "display_name": "AWS Bedrock",
            "connected": True,
            "config": {
                "aws_access_key_id": "AKIATEST",
                "aws_secret_access_key": "secrettest",
                "aws_region": "us-west-2",
            },
        }
    )

    captured = {}

    def fake_boto_client(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with patch("services.universal_model_adapter.boto3.client", side_effect=fake_boto_client):
        from services.universal_model_adapter import UniversalModelAdapter

        adapter = await UniversalModelAdapter.from_saved_credentials(db_proxy)

    assert captured.get("region_name") == "us-west-2"
    assert captured.get("aws_access_key_id") == "AKIATEST"
    assert captured.get("aws_secret_access_key") == "secrettest"
    assert adapter.region == "us-west-2"


@pytest.mark.asyncio
async def test_universal_adapter_from_saved_credentials_falls_back_when_missing(db_proxy):
    """No bedrock row → adapter constructed with no explicit creds (env path)."""
    captured = {}

    def fake_boto_client(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with patch("services.universal_model_adapter.boto3.client", side_effect=fake_boto_client):
        from services.universal_model_adapter import UniversalModelAdapter

        adapter = await UniversalModelAdapter.from_saved_credentials(db_proxy)

    # No explicit creds were passed.
    assert "aws_access_key_id" not in captured
    assert "aws_secret_access_key" not in captured
    # Region falls back to the default chain.
    assert adapter.region  # some region was resolved (env or default)
