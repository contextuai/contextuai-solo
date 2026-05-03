"""Smoke tests for the Knowledge Base / RAG scaffold.

Exercises CRUD on KBs, document upload + retrieval. The full ingest path
requires the bundled all-MiniLM-L6-v2 ONNX embedding model on disk; tests
that need embeddings are skipped if the model is unavailable.
"""
import io
import os
from pathlib import Path

import pytest


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
    reason="all-MiniLM-L6-v2 ONNX model not present (skipping ingest/query tests)",
)


# ---------------------------------------------------------------------------
# CRUD (no embeddings required)
# ---------------------------------------------------------------------------

def test_list_kbs_empty(test_app):
    r = test_app.get("/api/v1/knowledge-bases")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_create_kb(test_app):
    r = test_app.post(
        "/api/v1/knowledge-bases",
        json={"name": "Personal Docs", "description": "My personal stuff"},
    )
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["name"] == "Personal Docs"
    assert item["embedding_model"] == "all-MiniLM-L6-v2"
    assert item["embedding_dim"] == 384
    assert item["doc_count"] == 0
    assert item["chunk_count"] == 0
    assert item["_id"]


def test_create_kb_validation(test_app):
    # Missing name
    r = test_app.post("/api/v1/knowledge-bases", json={})
    assert r.status_code == 422
    # Empty name
    r = test_app.post("/api/v1/knowledge-bases", json={"name": ""})
    assert r.status_code == 422


def test_get_kb_404(test_app):
    r = test_app.get("/api/v1/knowledge-bases/does-not-exist")
    assert r.status_code == 404


def test_update_kb(test_app):
    created = test_app.post(
        "/api/v1/knowledge-bases", json={"name": "A"}
    ).json()["item"]
    kb_id = created["_id"]
    r = test_app.put(
        f"/api/v1/knowledge-bases/{kb_id}",
        json={"name": "Renamed", "description": "Now with desc"},
    )
    assert r.status_code == 200
    assert r.json()["item"]["name"] == "Renamed"
    assert r.json()["item"]["description"] == "Now with desc"


def test_update_kb_404(test_app):
    r = test_app.put(
        "/api/v1/knowledge-bases/missing", json={"name": "x"}
    )
    assert r.status_code == 404


def test_delete_kb(test_app):
    created = test_app.post(
        "/api/v1/knowledge-bases", json={"name": "DeleteMe"}
    ).json()["item"]
    kb_id = created["_id"]
    r = test_app.delete(f"/api/v1/knowledge-bases/{kb_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["deleted"] is True
    # And it's gone
    r = test_app.get(f"/api/v1/knowledge-bases/{kb_id}")
    assert r.status_code == 404


def test_list_documents_404_for_missing_kb(test_app):
    r = test_app.get("/api/v1/knowledge-bases/missing/documents")
    assert r.status_code == 404


def test_query_404_for_missing_kb(test_app):
    r = test_app.post(
        "/api/v1/knowledge-bases/missing/query", json={"query": "anything"}
    )
    assert r.status_code == 404


def test_upload_unsupported_extension(test_app):
    kb = test_app.post(
        "/api/v1/knowledge-bases", json={"name": "TypeCheck"}
    ).json()["item"]
    kb_id = kb["_id"]

    files = [("files", ("notes.exe", io.BytesIO(b"binary"), "application/octet-stream"))]
    r = test_app.post(f"/api/v1/knowledge-bases/{kb_id}/documents", files=files)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["status"] == "error"
    assert "Unsupported" in items[0]["error"]


# ---------------------------------------------------------------------------
# Ingest + Query (require embedding model)
# ---------------------------------------------------------------------------

@needs_embeddings
def test_upload_txt_and_query(test_app):
    kb = test_app.post(
        "/api/v1/knowledge-bases", json={"name": "IRS"}
    ).json()["item"]
    kb_id = kb["_id"]

    body = (
        "The standard deduction for single filers in tax year 2024 is "
        "$14,600. For married filing jointly it is $29,200. The earned "
        "income tax credit applies to qualifying low-income workers."
    ).encode("utf-8")

    files = [("files", ("irs-deductions.txt", io.BytesIO(body), "text/plain"))]
    r = test_app.post(f"/api/v1/knowledge-bases/{kb_id}/documents", files=files)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["status"] == "ready"
    assert items[0]["chunks"] >= 1

    # Listing reflects the upload
    r = test_app.get(f"/api/v1/knowledge-bases/{kb_id}/documents")
    docs = r.json()["items"]
    assert len(docs) == 1
    assert docs[0]["status"] == "ready"
    assert docs[0]["chunk_count"] >= 1

    # Query returns at least one citation
    r = test_app.post(
        f"/api/v1/knowledge-bases/{kb_id}/query",
        json={"query": "What is the standard deduction?"},
    )
    assert r.status_code == 200
    citations = r.json()["citations"]
    assert len(citations) >= 1
    top = citations[0]
    assert top["filename"] == "irs-deductions.txt"
    assert "deduction" in top["excerpt"].lower()
    # Cosine similarity in [-1, 1]; semantically close text should score well
    assert top["score"] > 0.2


@needs_embeddings
def test_delete_document_clears_chunks(test_app):
    kb = test_app.post(
        "/api/v1/knowledge-bases", json={"name": "Cleanup"}
    ).json()["item"]
    kb_id = kb["_id"]

    body = b"alpha bravo charlie delta echo foxtrot golf hotel"
    files = [("files", ("notes.txt", io.BytesIO(body), "text/plain"))]
    upload = test_app.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents", files=files
    ).json()["items"][0]
    doc_id = upload["id"]

    r = test_app.delete(f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    # Document gone, KB rollups updated
    docs = test_app.get(f"/api/v1/knowledge-bases/{kb_id}/documents").json()["items"]
    assert docs == []
    kb_after = test_app.get(f"/api/v1/knowledge-bases/{kb_id}").json()["item"]
    assert kb_after["doc_count"] == 0
    assert kb_after["chunk_count"] == 0
