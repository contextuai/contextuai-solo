"""
Tests for DefaultModelService — AI mode preference and default model resolution.
"""

import pytest
import pytest_asyncio

from services.default_model_service import DefaultModelService, DEFAULT_CLOUD_MODEL


@pytest_asyncio.fixture
async def default_svc(db_proxy):
    """DefaultModelService backed by test DB."""
    return DefaultModelService(db_proxy)


@pytest.mark.asyncio
async def test_cloud_mode_returns_default_cloud_model(default_svc):
    model_id = await default_svc.get_default_model_id("cloud")
    assert model_id == DEFAULT_CLOUD_MODEL


@pytest.mark.asyncio
async def test_local_mode_returns_empty_when_no_local_models(default_svc):
    model_id = await default_svc.get_default_model_id("local")
    assert model_id == ""


@pytest.mark.asyncio
async def test_local_mode_returns_local_model_when_available(db_proxy, default_svc):
    # Seed a local model into the models collection
    coll = db_proxy["models"]
    await coll.insert_one({
        "_id": "local-gemma-3-1b",
        "name": "Gemma 3 1B",
        "provider": "local",
        "model": "gemma-3-1b",
        "enabled": True,
    })

    model_id = await default_svc.get_default_model_id("local")
    assert model_id == "local-gemma-3-1b"


@pytest.mark.asyncio
async def test_preference_roundtrip(default_svc):
    # Default is "cloud"
    mode = await default_svc.get_ai_mode_preference()
    assert mode == "cloud"

    # Set to local
    await default_svc.set_ai_mode_preference("local")
    mode = await default_svc.get_ai_mode_preference()
    assert mode == "local"

    # Set back to cloud
    await default_svc.set_ai_mode_preference("cloud")
    mode = await default_svc.get_ai_mode_preference()
    assert mode == "cloud"
