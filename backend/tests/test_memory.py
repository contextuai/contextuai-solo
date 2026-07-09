"""Smoke tests for the Unified Memory Layer scaffold (SPEC-14 PR-A).

Exercises CRUD, pinning, settings, and export on manual facts. Semantic
search additionally needs the bundled all-MiniLM-L6-v2 ONNX embedding model
on disk; tests that need it are skipped if the model is unavailable — mirrors
`test_knowledge_base.py`.
"""
import os
from pathlib import Path

import pytest

from services.memory_service import MemoryService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _embedding_model_available() -> bool:
    """Check whether the bundled MiniLM ONNX model is on disk."""
    base = os.environ.get(
        "MODELS_DIR",
        os.path.join(Path.home(), ".contextuai-solo", "models"),
    )
    onnx = Path(base) / "embedding" / "all-MiniLM-L6-v2" / "model.onnx"
    return onnx.exists()


needs_embeddings = pytest.mark.skipif(
    not _embedding_model_available(),
    reason="all-MiniLM-L6-v2 ONNX model not present (skipping semantic search tests)",
)


# ---------------------------------------------------------------------------
# Facts CRUD (no embeddings required — add_fact guards embedding failures)
# ---------------------------------------------------------------------------

def test_list_facts_empty(test_app):
    r = test_app.get("/api/v1/memory/facts")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_create_fact(test_app):
    r = test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "pricing", "predicate": "is", "value": "$49/mo"},
    )
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["subject"] == "pricing"
    assert item["predicate"] == "is"
    assert item["value"] == "$49/mo"
    assert item["text"] == "pricing is $49/mo"
    assert item["scope"] == "global"
    assert item["origin"] == "user"
    assert item["confidence"] == 1.0
    assert item["status"] == "active"
    assert item["pinned"] is False
    assert item["source_kind"] == "user"
    assert item["_id"]
    assert item["id"] == item["_id"]
    assert "embedding" not in item


def test_create_fact_custom_text_and_scope(test_app):
    r = test_app.post(
        "/api/v1/memory/facts",
        json={
            "subject": "client Acme",
            "predicate": "prefers",
            "value": "email over calls",
            "text": "Acme prefers to be contacted by email, not phone.",
            "scope": "crew:sales-crew",
        },
    )
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["text"] == "Acme prefers to be contacted by email, not phone."
    assert item["scope"] == "crew:sales-crew"


def test_create_fact_validation(test_app):
    # Missing required fields
    r = test_app.post("/api/v1/memory/facts", json={})
    assert r.status_code == 422
    # Empty subject
    r = test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "", "predicate": "is", "value": "x"},
    )
    assert r.status_code == 422
    # Invalid scope
    r = test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "a", "predicate": "is", "value": "b", "scope": "nonsense"},
    )
    assert r.status_code == 422


def test_get_fact(test_app):
    created = test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "the user", "predicate": "works at", "value": "ContextuAI"},
    ).json()["item"]
    fact_id = created["_id"]

    r = test_app.get(f"/api/v1/memory/facts/{fact_id}")
    assert r.status_code == 200
    assert r.json()["item"]["subject"] == "the user"


def test_get_fact_404(test_app):
    r = test_app.get("/api/v1/memory/facts/does-not-exist")
    assert r.status_code == 404


def test_list_facts_after_create(test_app):
    test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "a", "predicate": "is", "value": "1"},
    )
    test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "b", "predicate": "is", "value": "2"},
    )
    r = test_app.get("/api/v1/memory/facts")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2


def test_list_facts_filtered_by_scope(test_app):
    test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "a", "predicate": "is", "value": "1", "scope": "global"},
    )
    test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "b", "predicate": "is", "value": "2", "scope": "crew:x"},
    )
    r = test_app.get("/api/v1/memory/facts", params={"scope": "crew:x"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["scope"] == "crew:x"


def test_update_fact(test_app):
    created = test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "pricing", "predicate": "is", "value": "$49/mo"},
    ).json()["item"]
    fact_id = created["_id"]

    r = test_app.put(
        f"/api/v1/memory/facts/{fact_id}",
        json={"value": "$59/mo"},
    )
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["value"] == "$59/mo"
    # Text-affecting field changed -> text re-composed
    assert item["text"] == "pricing is $59/mo"


def test_update_fact_pinned_only_does_not_touch_text(test_app):
    created = test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "pricing", "predicate": "is", "value": "$49/mo"},
    ).json()["item"]
    fact_id = created["_id"]

    r = test_app.put(f"/api/v1/memory/facts/{fact_id}", json={"pinned": True})
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["pinned"] is True
    assert item["text"] == "pricing is $49/mo"


def test_update_fact_404(test_app):
    r = test_app.put("/api/v1/memory/facts/missing", json={"value": "x"})
    assert r.status_code == 404


def test_delete_fact(test_app):
    created = test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "temp", "predicate": "is", "value": "gone soon"},
    ).json()["item"]
    fact_id = created["_id"]

    r = test_app.delete(f"/api/v1/memory/facts/{fact_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    r = test_app.get(f"/api/v1/memory/facts/{fact_id}")
    assert r.status_code == 404


def test_delete_fact_404(test_app):
    r = test_app.delete("/api/v1/memory/facts/missing")
    assert r.status_code == 404


def test_pin_fact(test_app):
    created = test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "important", "predicate": "is", "value": "true"},
    ).json()["item"]
    fact_id = created["_id"]

    r = test_app.post(f"/api/v1/memory/facts/{fact_id}/pin", json={"pinned": True})
    assert r.status_code == 200
    assert r.json()["item"]["pinned"] is True

    r = test_app.post(f"/api/v1/memory/facts/{fact_id}/pin", json={"pinned": False})
    assert r.status_code == 200
    assert r.json()["item"]["pinned"] is False


def test_pin_fact_404(test_app):
    r = test_app.post("/api/v1/memory/facts/missing/pin", json={"pinned": True})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Settings / kill switch
# ---------------------------------------------------------------------------

def test_get_settings_defaults(test_app):
    r = test_app.get("/api/v1/memory/settings")
    assert r.status_code == 200
    settings = r.json()
    assert settings["enabled"] is True
    assert settings["chat_enabled"] is True
    assert settings["crews_enabled"] is True
    assert settings["channels_enabled"] is False
    assert settings["confidence_threshold"] == 0.6


def test_update_settings(test_app):
    r = test_app.put(
        "/api/v1/memory/settings",
        json={"enabled": False, "channels_enabled": True},
    )
    assert r.status_code == 200
    settings = r.json()
    assert settings["enabled"] is False
    assert settings["channels_enabled"] is True
    # Untouched fields keep their prior values
    assert settings["chat_enabled"] is True

    # Persisted across a fresh GET
    r = test_app.get("/api/v1/memory/settings")
    assert r.json()["enabled"] is False


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_export_empty(test_app):
    r = test_app.get("/api/v1/memory/export")
    assert r.status_code == 200
    body = r.json()
    assert body["facts"] == []
    assert "exported_at" in body


def test_export_includes_facts_without_embedding_key(test_app):
    test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "a", "predicate": "is", "value": "1"},
    )
    r = test_app.get("/api/v1/memory/export")
    assert r.status_code == 200
    facts = r.json()["facts"]
    assert len(facts) == 1
    assert "embedding" not in facts[0]
    assert "has_embedding" in facts[0]


# ---------------------------------------------------------------------------
# Search — requires the embedding model; degrades gracefully without it
# ---------------------------------------------------------------------------

def test_search_without_embeddings_returns_empty_gracefully(test_app):
    """Even if the ONNX model is unavailable, search must not 500."""
    test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "pricing", "predicate": "is", "value": "$49/mo"},
    )
    r = test_app.post("/api/v1/memory/search", json={"query": "how much does it cost"})
    assert r.status_code == 200
    assert "items" in r.json()


@needs_embeddings
def test_search_finds_semantically_close_fact(test_app):
    test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "pricing", "predicate": "is", "value": "$49 per month"},
    )
    test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "the user", "predicate": "likes", "value": "dark mode"},
    )

    r = test_app.post(
        "/api/v1/memory/search", json={"query": "what does the subscription cost"}
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert any("49" in it["text"] for it in items)
    assert all("score" in it for it in items)
    assert all("embedding" not in it for it in items)


@needs_embeddings
def test_search_bumps_last_used_at(test_app):
    created = test_app.post(
        "/api/v1/memory/facts",
        json={"subject": "pricing", "predicate": "is", "value": "$49/mo"},
    ).json()["item"]
    assert created["last_used_at"] is None

    test_app.post("/api/v1/memory/search", json={"query": "pricing"})

    r = test_app.get(f"/api/v1/memory/facts/{created['_id']}")
    assert r.json()["item"]["last_used_at"] is not None


# ---------------------------------------------------------------------------
# format_memory_block — pure unit test, no DB needed
# ---------------------------------------------------------------------------

def test_format_memory_block_empty():
    assert MemoryService.format_memory_block([]) == ""


def test_format_memory_block_renders_bullets():
    facts = [
        {"text": "pricing is $49/mo"},
        {"text": "client Acme prefers email"},
    ]
    block = MemoryService.format_memory_block(facts)
    assert block.startswith("## What I know")
    assert "- pricing is $49/mo" in block
    assert "- client Acme prefers email" in block


def test_format_memory_block_caps_at_twelve_lines():
    facts = [{"text": f"fact number {i}"} for i in range(20)]
    block = MemoryService.format_memory_block(facts)
    lines = block.split("\n")
    # 1 header + at most 12 bullets
    assert len(lines) <= 13


def test_format_memory_block_falls_back_to_subject_predicate_value():
    facts = [{"subject": "pricing", "predicate": "is", "value": "$49/mo", "text": ""}]
    block = MemoryService.format_memory_block(facts)
    assert "pricing is $49/mo" in block
