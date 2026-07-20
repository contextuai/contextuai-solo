"""Tests for Ollama model seeding into the ``models`` collection.

Covers the fix for: Ollama-served models (e.g. ``gemma4``) never appeared in
the chat dropdown because ``cloud_model_seeder.sync_cloud_models_to_db`` had no
Ollama branch. These tests exercise discovery, stale cleanup, and the
preserve-on-failure path — all against a mocked ``/api/tags`` so no live Ollama
server is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.cloud_model_seeder import (
    _build_ollama_model_doc,
    sync_cloud_models_to_db,
)
from services.ollama_service import OllamaService


def _mock_list_models(names):
    """Return an AsyncMock standing in for ``OllamaDirectService.list_models``."""
    return AsyncMock(return_value=[{"name": n} for n in names])


async def _insert_ollama_provider(db_proxy, base_url="http://localhost:11434"):
    await db_proxy["cloud_providers"].insert_one(
        {
            "provider_id": "ollama-1",
            "provider_type": "ollama",
            "display_name": "Ollama (Local)",
            "connected": False,
            "config": {"base_url": base_url},
        }
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_seeds_ollama_models(db_proxy):
    await _insert_ollama_provider(db_proxy)

    with patch(
        "services.ollama_direct_service.OllamaDirectService.list_models",
        _mock_list_models(["gemma4", "deepseek-r1:32b"]),
    ):
        seeded = await sync_cloud_models_to_db(db_proxy)

    assert seeded == 2

    gemma = await db_proxy["models"].find_one({"_id": "ollama:gemma4"})
    assert gemma is not None
    assert gemma["provider"] == "ollama"
    assert gemma["enabled"] is True
    assert gemma["model_metadata"]["ollama_model"] == "gemma4"
    # The row must route to the Ollama chat path.
    assert OllamaService.is_ollama_model(gemma) is True

    # A tag with a colon round-trips: the full name stays in the _id and
    # ollama_model, so the dispatcher hands the exact tag back to Ollama.
    ds = await db_proxy["models"].find_one({"_id": "ollama:deepseek-r1:32b"})
    assert ds is not None
    assert ds["model_metadata"]["ollama_model"] == "deepseek-r1:32b"


@pytest.mark.asyncio
async def test_sync_skips_ollama_when_no_provider(db_proxy):
    """No saved Ollama provider row → no discovery, nothing seeded."""
    with patch(
        "services.ollama_direct_service.OllamaDirectService.list_models",
        _mock_list_models(["gemma4"]),
    ) as mocked:
        seeded = await sync_cloud_models_to_db(db_proxy)

    assert seeded == 0
    mocked.assert_not_awaited()
    assert await db_proxy["models"].count_documents({}) == 0


# ---------------------------------------------------------------------------
# Stale cleanup
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_removes_retired_ollama_model(db_proxy):
    """A previously-seeded model no longer served by Ollama (e.g. a retired
    cloud tag) is removed on the next sync."""
    await _insert_ollama_provider(db_proxy)
    await db_proxy["models"].insert_one(
        {
            "_id": "ollama:qwen3-coder:480b-cloud",
            "id": "ollama:qwen3-coder:480b-cloud",
            "name": "Qwen3 Coder (Ollama)",
            "provider": "ollama",
            "enabled": True,
            "model_metadata": {"runtime": "ollama", "ollama_model": "qwen3-coder:480b-cloud"},
        }
    )

    with patch(
        "services.ollama_direct_service.OllamaDirectService.list_models",
        _mock_list_models(["gemma4"]),
    ):
        await sync_cloud_models_to_db(db_proxy)

    assert await db_proxy["models"].find_one({"_id": "ollama:qwen3-coder:480b-cloud"}) is None
    assert await db_proxy["models"].find_one({"_id": "ollama:gemma4"}) is not None


# ---------------------------------------------------------------------------
# Preserve-on-failure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_preserves_ollama_rows_on_discovery_failure(db_proxy):
    """If the Ollama server is unreachable, existing rows must survive rather
    than being wiped by the stale-cleanup pass."""
    await _insert_ollama_provider(db_proxy)
    await db_proxy["models"].insert_one(
        {
            "_id": "ollama:deepseek-r1:32b",
            "id": "ollama:deepseek-r1:32b",
            "name": "Deepseek R1 (Ollama)",
            "provider": "ollama",
            "enabled": True,
            "model_metadata": {"runtime": "ollama", "ollama_model": "deepseek-r1:32b"},
        }
    )

    with patch(
        "services.ollama_direct_service.OllamaDirectService.list_models",
        AsyncMock(side_effect=RuntimeError("connection refused")),
    ):
        await sync_cloud_models_to_db(db_proxy)

    # Row preserved despite the outage.
    assert await db_proxy["models"].find_one({"_id": "ollama:deepseek-r1:32b"}) is not None


# ---------------------------------------------------------------------------
# Doc builder
# ---------------------------------------------------------------------------
def test_build_ollama_model_doc_shape():
    doc = _build_ollama_model_doc(doc_id="ollama:gemma4", name="gemma4")
    assert doc["provider"] == "ollama"
    assert doc["model"] == "gemma4"
    assert doc["model_metadata"]["runtime"] == "ollama"
    assert doc["model_metadata"]["ollama_model"] == "gemma4"
    assert OllamaService.is_ollama_model(doc) is True
