"""Anthropic live model discovery in the cloud model seeder."""

import pytest

from services.cloud_model_seeder import sync_cloud_models_to_db


async def _ids(db):
    out = []
    async for m in db["models"].find({}):
        out.append(m.get("_id") or m.get("id"))
    return out


@pytest.mark.asyncio
async def test_anthropic_discovery_seeds_live_models(db_proxy, monkeypatch):
    await db_proxy["cloud_providers"].insert_one({
        "provider_id": "a1",
        "provider_type": "anthropic",
        "config": {"api_key": "sk-ant-x"},
    })

    async def fake_disc(api_key):
        assert api_key == "sk-ant-x"
        return [("claude-opus-4-9", "Claude Opus 4.9"), ("claude-sonnet-4-7", "Claude Sonnet 4.7")]

    monkeypatch.setattr(
        "services.cloud_model_seeder._discover_anthropic_models", fake_disc
    )

    await sync_cloud_models_to_db(db_proxy)
    ids = await _ids(db_proxy)
    assert "anthropic:claude-opus-4-9" in ids
    assert "anthropic:claude-sonnet-4-7" in ids
    # the static-catalog id must NOT be seeded when discovery succeeds
    assert "anthropic:claude-opus-4-7" not in ids


@pytest.mark.asyncio
async def test_anthropic_discovery_falls_back_to_static(db_proxy, monkeypatch):
    await db_proxy["cloud_providers"].insert_one({
        "provider_id": "a1",
        "provider_type": "anthropic",
        "config": {"api_key": "sk-ant-x"},
    })

    async def boom(api_key):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "services.cloud_model_seeder._discover_anthropic_models", boom
    )

    await sync_cloud_models_to_db(db_proxy)
    ids = await _ids(db_proxy)
    # static catalog is used on discovery failure
    assert any(str(i).startswith("anthropic:claude-") for i in ids)
