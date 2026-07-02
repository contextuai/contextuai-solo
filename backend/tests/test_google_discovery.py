"""Google (Gemini) live model discovery in the cloud model seeder."""

import pytest

from services.cloud_model_seeder import sync_cloud_models_to_db, _discover_google_models


async def _ids(db):
    out = []
    async for m in db["models"].find({}):
        out.append(m.get("_id") or m.get("id"))
    return out


@pytest.mark.asyncio
async def test_google_discovery_seeds_live_models(db_proxy, monkeypatch):
    await db_proxy["cloud_providers"].insert_one({
        "provider_id": "g1",
        "provider_type": "google",
        "config": {"api_key": "AIza-x"},
    })

    async def fake_disc(api_key):
        assert api_key == "AIza-x"
        return [("gemini-2.5-pro", "Gemini 2.5 Pro"), ("gemini-2.5-flash", "Gemini 2.5 Flash")]

    monkeypatch.setattr(
        "services.cloud_model_seeder._discover_google_models", fake_disc
    )

    await sync_cloud_models_to_db(db_proxy)
    ids = await _ids(db_proxy)
    assert "google:gemini-2.5-pro" in ids
    assert "google:gemini-2.5-flash" in ids
    # the static-catalog id must NOT be seeded when discovery succeeds
    assert "google:gemini-2.0-pro" not in ids


@pytest.mark.asyncio
async def test_google_discovery_falls_back_to_static(db_proxy, monkeypatch):
    await db_proxy["cloud_providers"].insert_one({
        "provider_id": "g1",
        "provider_type": "google",
        "config": {"api_key": "AIza-x"},
    })

    async def boom(api_key):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "services.cloud_model_seeder._discover_google_models", boom
    )

    await sync_cloud_models_to_db(db_proxy)
    ids = await _ids(db_proxy)
    # static catalog is used on discovery failure
    assert any(str(i).startswith("google:gemini-") for i in ids)


@pytest.mark.asyncio
async def test_discover_google_filters_non_chat_models(monkeypatch):
    """Only Gemini models supporting generateContent survive the filter."""

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "models": [
                    {
                        "name": "models/gemini-2.5-pro",
                        "displayName": "Gemini 2.5 Pro",
                        "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
                    },
                    {
                        # embedding model — no generateContent, must be dropped
                        "name": "models/text-embedding-004",
                        "displayName": "Text Embedding 004",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                    {
                        # aqa — generateAnswer only, must be dropped
                        "name": "models/aqa",
                        "displayName": "Model that performs Attributed QA",
                        "supportedGenerationMethods": ["generateAnswer"],
                    },
                    {
                        # non-gemini generateContent model — dropped by prefix
                        "name": "models/imagen-3.0",
                        "displayName": "Imagen 3",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        # gemini image-gen (Nano Banana) — generateContent but
                        # not text chat, dropped by substring filter
                        "name": "models/gemini-2.5-flash-image",
                        "displayName": "Nano Banana",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        # gemini TTS — dropped by substring filter
                        "name": "models/gemini-2.5-flash-preview-tts",
                        "displayName": "Gemini 2.5 Flash Preview TTS",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        # gemini robotics — dropped by substring filter
                        "name": "models/gemini-robotics-er-1.6-preview",
                        "displayName": "Gemini Robotics-ER 1.6 Preview",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                ]
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            assert params and params.get("key") == "AIza-x"
            return FakeResp()

    monkeypatch.setattr("services.cloud_model_seeder.httpx.AsyncClient", FakeClient)

    pairs = await _discover_google_models("AIza-x")
    assert pairs == [("gemini-2.5-pro", "Gemini 2.5 Pro")]
