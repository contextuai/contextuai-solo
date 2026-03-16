"""
Tests for the models router — mode filtering and preference endpoints.
"""

import pytest


@pytest.fixture(autouse=True)
def seed_models(db_proxy):
    """Seed both local and cloud models into the test DB."""
    import asyncio

    async def _seed():
        coll = db_proxy["models"]
        await coll.insert_one({
            "_id": "local-gemma-3-1b",
            "name": "Gemma 3 1B",
            "provider": "local",
            "model": "gemma-3-1b",
            "enabled": True,
            "description": "Local GGUF model",
            "capabilities": [],
        })
        await coll.insert_one({
            "_id": "bedrock-claude-sonnet",
            "name": "Claude Sonnet",
            "provider": "bedrock",
            "model": "anthropic.claude-3-sonnet",
            "enabled": True,
            "description": "Cloud model",
            "capabilities": ["vision"],
        })

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_seed())


def test_list_models_no_filter(test_app):
    resp = test_app.get("/api/v1/models/")
    assert resp.status_code == 200
    data = resp.json()
    models = data.get("models", [])
    assert len(models) >= 2


def test_list_models_local_filter(test_app):
    resp = test_app.get("/api/v1/models/?mode=local")
    assert resp.status_code == 200
    models = resp.json().get("models", [])
    assert all(
        m.get("provider") == "local" or m.get("_id", m.get("id", "")).startswith("local-")
        for m in models
    )
    assert len(models) >= 1


def test_list_models_cloud_filter(test_app):
    resp = test_app.get("/api/v1/models/?mode=cloud")
    assert resp.status_code == 200
    models = resp.json().get("models", [])
    for m in models:
        mid = m.get("_id", m.get("id", ""))
        assert not mid.startswith("local-")
        assert m.get("provider") != "local"
    assert len(models) >= 1


def test_preference_get_default(test_app):
    resp = test_app.get("/api/v1/models/preference")
    assert resp.status_code == 200
    assert resp.json()["ai_mode"] == "cloud"


def test_preference_set_and_get(test_app):
    resp = test_app.put("/api/v1/models/preference", json={"ai_mode": "local"})
    assert resp.status_code == 200
    assert resp.json()["ai_mode"] == "local"

    resp = test_app.get("/api/v1/models/preference")
    assert resp.status_code == 200
    assert resp.json()["ai_mode"] == "local"


def test_preference_invalid_mode(test_app):
    resp = test_app.put("/api/v1/models/preference", json={"ai_mode": "invalid"})
    assert resp.status_code == 400
