"""Tests for RAGService.ingest_from_path + delete_for_source.

These exercise the full embedding pipeline so they need the bundled
all-MiniLM-L6-v2 ONNX model on disk. They are skipped if absent —
matching the guard in test_knowledge_base.py.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from repositories.chunk_repository import ChunkRepository
from repositories.document_repository import DocumentRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services.rag_service import RAGService


def _embedding_model_available() -> bool:
    base = os.environ.get(
        "MODELS_DIR",
        os.path.join(Path.home(), ".contextuai-solo", "models"),
    )
    return (Path(base) / "embedding" / "all-MiniLM-L6-v2" / "model.onnx").exists()


needs_embeddings = pytest.mark.skipif(
    not _embedding_model_available(),
    reason="all-MiniLM-L6-v2 ONNX model not present",
)


async def _seed_kb(db, kb_id="kb1") -> None:
    await db["knowledge_bases"].insert_one(
        {
            "_id": kb_id,
            "name": "kb",
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dim": 384,
            "doc_count": 0,
            "chunk_count": 0,
            "created_at": "2026-04-30T00:00:00",
            "updated_at": "2026-04-30T00:00:00",
        }
    )


@needs_embeddings
@pytest.mark.asyncio
async def test_ingest_from_path_stores_source_metadata(tmp_path, db_proxy):
    await _seed_kb(db_proxy)
    rag = RAGService(
        KnowledgeBaseRepository(db_proxy),
        DocumentRepository(db_proxy),
        ChunkRepository(db_proxy),
    )
    file_path = tmp_path / "note.md"
    file_path.write_text("# Hello\nworld " * 50, encoding="utf-8")
    stats = await rag.ingest_from_path(
        kb_id="kb1",
        source_id="src1",
        abs_path=str(file_path),
        label_of_source="My Notes",
    )
    assert stats["chunks"] >= 1

    docs = await db_proxy["kb_documents"].find({"kb_id": "kb1"}).to_list(length=10)
    assert len(docs) == 1
    d = docs[0]
    assert d["source_type"] == "folder"
    assert d["source_id"] == "src1"
    assert d["source_label"] == "My Notes"
    assert d["abs_path"] == str(file_path)
    assert d["mtime"] is not None
    assert d["content_hash"].startswith("sha256:")


@needs_embeddings
@pytest.mark.asyncio
async def test_ingest_replaces_existing_when_id_passed(tmp_path, db_proxy):
    await _seed_kb(db_proxy)
    rag = RAGService(
        KnowledgeBaseRepository(db_proxy),
        DocumentRepository(db_proxy),
        ChunkRepository(db_proxy),
    )
    f = tmp_path / "n.md"
    f.write_text("first version", encoding="utf-8")
    await rag.ingest_from_path(
        kb_id="kb1", source_id="src1",
        abs_path=str(f), label_of_source="X",
    )
    first = await db_proxy["kb_documents"].find_one({"abs_path": str(f)})

    f.write_text("second version with much more content " * 10, encoding="utf-8")
    await rag.ingest_from_path(
        kb_id="kb1", source_id="src1",
        abs_path=str(f), label_of_source="X",
        existing_doc_id=first["_id"],
    )
    docs = await db_proxy["kb_documents"].find({"abs_path": str(f)}).to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["_id"] != first["_id"]


@needs_embeddings
@pytest.mark.asyncio
async def test_delete_for_source_removes_docs_and_chunks(tmp_path, db_proxy):
    await _seed_kb(db_proxy)
    rag = RAGService(
        KnowledgeBaseRepository(db_proxy),
        DocumentRepository(db_proxy),
        ChunkRepository(db_proxy),
    )
    f = tmp_path / "n.md"
    f.write_text("hi there from a folder doc", encoding="utf-8")
    await rag.ingest_from_path(
        kb_id="kb1", source_id="src1",
        abs_path=str(f), label_of_source="X",
    )
    deleted_chunks = await rag.delete_for_source("kb1", "src1")
    assert deleted_chunks >= 1
    remaining = await db_proxy["kb_documents"].find(
        {"source_id": "src1"}
    ).to_list(length=10)
    assert remaining == []
