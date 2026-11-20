"""Tests for Issue #76: Smart Context Injection + Hybrid RAG with Citations."""
import math
import os
import sys
from typing import List

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from repositories.chunk_repository import ChunkRepository
from repositories.document_repository import DocumentRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services import rag_service as rag_mod
from services.rag_service import (
    RAGService,
    _bm25_scores,
    build_attached_files_context,
    estimate_tokens,
)


def _unit_vec(values: List[float], dim: int = 384) -> List[float]:
    vec = np.zeros(dim, dtype=np.float32)
    for i, v in enumerate(values):
        vec[i] = v
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


async def _seed_kb(db, kb_id: str = "kb-smart") -> None:
    await db["knowledge_bases"].insert_one(
        {
            "_id": kb_id,
            "name": "Smart RAG Test KB",
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dim": 384,
            "doc_count": 0,
            "chunk_count": 0,
            "created_at": "2026-11-19T00:00:00",
            "updated_at": "2026-11-19T00:00:00",
        }
    )


async def _seed_chunk(
    db,
    *,
    chunk_id: str,
    kb_id: str,
    doc_id: str,
    filename: str,
    chunk_index: int,
    text: str,
    embedding: List[float],
    page: int | None = None,
) -> None:
    await db["kb_chunks"].insert_one(
        {
            "_id": chunk_id,
            "kb_id": kb_id,
            "doc_id": doc_id,
            "doc_filename": filename,
            "chunk_index": chunk_index,
            "page": page,
            "text": text,
            "embedding": embedding,
            "created_at": "2026-11-19T00:00:00",
            "updated_at": "2026-11-19T00:00:00",
        }
    )


def _make_rag(db) -> RAGService:
    return RAGService(
        KnowledgeBaseRepository(db),
        DocumentRepository(db),
        ChunkRepository(db),
    )


# ---------------------------------------------------------------------------
# Token estimator + Okapi BM25 unit tests
# ---------------------------------------------------------------------------


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hi") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_bm25_scores_exact_term_and_single_doc():
    # Empty inputs
    assert len(_bm25_scores("hello", [])) == 0
    zeros = _bm25_scores("", ["alpha beta", "gamma delta"])
    assert np.all(zeros == 0.0)

    # Single-doc positive score must stay > 0 (Lucene non-negative IDF)
    single = _bm25_scores("fips", ["Compliant with FIPS-140-3 module rules."])
    assert single.shape == (1,)
    assert float(single[0]) > 0.0

    # Exact acronym/identifier ranks matching document #1
    corpus = [
        "General system architecture and overview of distributed consensus.",
        "Failover protocol triggers automatically on error ERR_QUORUM_42 during election.",
        "Another overview discussing network failover and quorum behavior.",
    ]
    scores = _bm25_scores("ERR_QUORUM_42", corpus)
    assert int(np.argmax(scores)) == 1
    assert float(scores[1]) > float(scores[0])
    assert float(scores[1]) > float(scores[2])


# ---------------------------------------------------------------------------
# RAGService.query (hybrid, vector, bm25, single-doc preservation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_doc_cosine_score_preserved(db_proxy, monkeypatch):
    await _seed_kb(db_proxy, "kb-single")
    # Chunk vector has cosine 0.6 with query vector [0.6, 0.8, 0, ...]
    q_vec = _unit_vec([1.0, 0.0])
    c_vec = _unit_vec([0.6, 0.8])
    monkeypatch.setattr(rag_mod.embedding_service, "embed", lambda _q: q_vec)

    await _seed_chunk(
        db_proxy,
        chunk_id="c1",
        kb_id="kb-single",
        doc_id="d1",
        filename="irs-deductions.txt",
        chunk_index=0,
        text="The standard deduction for single filers in 2024 is $14,600.",
        embedding=c_vec,
        page=1,
    )

    rag = _make_rag(db_proxy)

    hybrid_res = await rag.query("kb-single", "standard deduction", mode="hybrid")
    assert len(hybrid_res) == 1
    top = hybrid_res[0]
    assert top["doc_id"] == "d1"
    assert top["filename"] == "irs-deductions.txt"
    assert top["page"] == 1
    assert top["chunk_index"] == 0
    assert top["mode"] == "hybrid"
    assert top["score"] > 0.2
    assert math.isclose(top["vector_score"], 0.6, rel_tol=1e-4)
    assert top["bm25_score"] > 0.0

    # Vector-only mode
    vec_res = await rag.query("kb-single", "standard deduction", mode="vector")
    assert vec_res[0]["score"] > 0.2
    assert vec_res[0]["mode"] == "vector"
    assert vec_res[0]["bm25_score"] == 0.0

    # BM25-only mode must not call embedding_service.embed
    monkeypatch.setattr(
        rag_mod.embedding_service,
        "embed",
        lambda _q: (_ for _ in ()).throw(AssertionError("embed should not be called in bm25 mode")),
    )
    bm25_res = await rag.query("kb-single", "standard deduction", mode="bm25")
    assert len(bm25_res) == 1
    assert bm25_res[0]["score"] == pytest.approx(1.0)
    assert bm25_res[0]["vector_score"] == 0.0
    assert bm25_res[0]["bm25_score"] > 0.0
    assert bm25_res[0]["mode"] == "bm25"


@pytest.mark.asyncio
async def test_hybrid_bm25_boosts_exact_acronym_above_dense_neighbor(db_proxy, monkeypatch):
    await _seed_kb(db_proxy, "kb-hybrid")
    q_vec = _unit_vec([1.0, 0.0])
    monkeypatch.setattr(rag_mod.embedding_service, "embed", lambda _q: q_vec)

    # Chunk A has higher cosine similarity (0.90) but lacks exact code XKCD-9042
    await _seed_chunk(
        db_proxy,
        chunk_id="c-dense",
        kb_id="kb-hybrid",
        doc_id="doc-dense",
        filename="overview.md",
        chunk_index=0,
        text="High-level diagnostic procedures for cluster telemetry alerts.",
        embedding=_unit_vec([0.9, math.sqrt(1 - 0.81)]),
    )
    # Chunk B has lower cosine similarity (0.60) but contains exact acronym XKCD-9042
    await _seed_chunk(
        db_proxy,
        chunk_id="c-kw",
        kb_id="kb-hybrid",
        doc_id="doc-kw",
        filename="runbook.md",
        chunk_index=2,
        text="When alert XKCD-9042 fires, drain node and inspect journalctl logs.",
        embedding=_unit_vec([0.6, 0.8]),
        page=4,
    )

    rag = _make_rag(db_proxy)

    # Pure vector picks overview.md first
    vec_hits = await rag.query("kb-hybrid", "XKCD-9042", top_k=2, mode="vector")
    assert vec_hits[0]["doc_id"] == "doc-dense"

    # Hybrid boosts runbook.md to #1 due to BM25 exact match
    hyb_hits = await rag.query("kb-hybrid", "XKCD-9042", top_k=2, mode="hybrid", alpha=0.6)
    assert hyb_hits[0]["doc_id"] == "doc-kw"
    assert hyb_hits[0]["bm25_score"] > 0.0
    assert hyb_hits[1]["bm25_score"] == 0.0
    assert hyb_hits[0]["score"] > hyb_hits[1]["score"]

    # Invalid mode rejected cleanly
    with pytest.raises(ValueError):
        await rag.query("kb-hybrid", "XKCD-9042", mode="invalid_mode")


# ---------------------------------------------------------------------------
# RAGService.smart_retrieve (full-context bypass vs hybrid fallback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_retrieve_full_context_and_hybrid_fallback(db_proxy, monkeypatch):
    await _seed_kb(db_proxy, "kb-smart-ctx")
    q_vec = _unit_vec([1.0, 0.0])
    monkeypatch.setattr(rag_mod.embedding_service, "embed", lambda _q: q_vec)

    # Seed chunks intentionally out of order to verify (doc_id, chunk_index) sorting
    await _seed_chunk(
        db_proxy,
        chunk_id="c2",
        kb_id="kb-smart-ctx",
        doc_id="doc-a",
        filename="manual.pdf",
        chunk_index=2,
        text="Page two troubleshooting checklist for ZETA-77.",
        embedding=_unit_vec([0.9, 0.1]),
        page=2,
    )
    await _seed_chunk(
        db_proxy,
        chunk_id="c0",
        kb_id="kb-smart-ctx",
        doc_id="doc-a",
        filename="manual.pdf",
        chunk_index=0,
        text="Page one introduction paragraph.",
        embedding=_unit_vec([0.4, 0.9]),
        page=1,
    )
    await _seed_chunk(
        db_proxy,
        chunk_id="c1",
        kb_id="kb-smart-ctx",
        doc_id="doc-a",
        filename="manual.pdf",
        chunk_index=1,
        text="Page one second paragraph.",
        embedding=_unit_vec([0.3, 0.9]),
        page=1,
    )
    await _seed_chunk(
        db_proxy,
        chunk_id="c3",
        kb_id="kb-smart-ctx",
        doc_id="doc-b",
        filename="notes.txt",
        chunk_index=0,
        text="Plain text release notes without page numbers.",
        embedding=_unit_vec([0.2, 0.9]),
        page=None,
    )

    rag = _make_rag(db_proxy)

    # 1. Within budget (budget = 4096) -> full_context bypass
    full = await rag.smart_retrieve(
        "kb-smart-ctx",
        "Where is ZETA-77?",
        n_ctx=8192,
        budget_ratio=0.5,
        top_k=2,
    )
    assert full["mode"] == "full_context"
    assert full["n_ctx_budget"] == 4096
    assert 0 < full["total_tokens"] <= 4096
    assert len(full["citations"]) == 2
    assert full["citations"][0]["index"] == 1
    assert full["citations"][0]["doc_id"] == "doc-a"
    assert full["citations"][0]["mode"] == "full_context"
    assert full["citations"][1]["index"] == 2
    assert full["citations"][1]["doc_id"] == "doc-b"

    ctx = full["context_block"]
    assert "[1] manual.pdf" in ctx
    assert "[2] notes.txt" in ctx
    assert "[Page 1]" in ctx
    assert "[Page 2]" in ctx
    # Page 1 marker should only appear once for chunks 0 and 1 on page 1
    assert ctx.count("[Page 1]") == 1
    # Ordering preserved
    assert ctx.index("Page one introduction") < ctx.index("Page one second") < ctx.index("Page two troubleshooting")

    # 2. Over budget (n_ctx=40, budget=20 < total_tokens) -> hybrid_rag fallback
    fallback = await rag.smart_retrieve(
        "kb-smart-ctx",
        "ZETA-77 troubleshooting",
        n_ctx=40,
        budget_ratio=0.5,
        top_k=2,
    )
    assert fallback["mode"] == "hybrid_rag"
    assert fallback["n_ctx_budget"] == 20
    assert fallback["total_tokens"] > 20
    assert len(fallback["citations"]) == 2
    assert fallback["citations"][0]["doc_id"] == "doc-a"
    assert fallback["citations"][0]["chunk_index"] == 2
    assert "[Knowledge Base Context]" in fallback["context_block"]


@pytest.mark.asyncio
async def test_smart_retrieve_empty_kb(db_proxy):
    await _seed_kb(db_proxy, "kb-empty")
    rag = _make_rag(db_proxy)
    res = await rag.smart_retrieve("kb-empty", "anything")
    assert res["mode"] == "hybrid_rag"
    assert res["total_tokens"] == 0
    assert res["citations"] == []
    assert res["context_block"] == ""


# ---------------------------------------------------------------------------
# build_attached_files_context (full injection vs chunked BM25 fallback)
# ---------------------------------------------------------------------------


def test_build_attached_files_context_full_and_chunked():
    # Empty list
    empty = build_attached_files_context([], "hello")
    assert empty["citations"] == []
    assert empty["context_block"] == ""

    # Small files -> full_context
    small_files = [
        {"file_id": "f1", "filename": "spec.md", "text": "Service SLA is 99.99%.", "page": None},
        {"file_id": "f2", "filename": "appendix.pdf", "text": "Encryption uses AES-256-GCM.", "page": 3},
    ]
    full = build_attached_files_context(small_files, "What is the SLA?", n_ctx=8192, budget_ratio=0.5)
    assert full["mode"] == "full_context"
    assert len(full["citations"]) == 2
    assert full["citations"][0]["doc_id"] == "f1"
    assert full["citations"][0]["score"] == 1.0
    assert full["citations"][0]["mode"] == "full_context"
    assert full["citations"][1]["page"] == 3
    assert "[1] spec.md" in full["context_block"]
    assert "[2] appendix.pdf p.3" in full["context_block"]
    assert "Service SLA is 99.99%." in full["context_block"]

    # Large file -> chunked BM25 fallback within budget
    filler_a = ("General networking latency and buffer configuration details. " * 60).strip()
    needle = ("Critical recovery key ZIRCON-7788 restores the vault quorum immediately. " * 15).strip()
    filler_b = ("Routine telemetry metric collection and rotation schedule notes. " * 60).strip()
    large_text = f"{filler_a}\n\n{needle}\n\n{filler_b}"

    large_files = [
        {"file_id": "big-1", "filename": "operations.txt", "text": large_text, "page": None}
    ]
    chunked = build_attached_files_context(
        large_files,
        "ZIRCON-7788 vault quorum",
        n_ctx=2400,
        budget_ratio=0.5,  # budget = 1200 tokens
        top_k=4,
    )
    assert chunked["mode"] == "hybrid_rag"
    assert chunked["total_tokens"] > chunked["n_ctx_budget"]
    assert len(chunked["citations"]) >= 1
    assert "ZIRCON-7788" in chunked["citations"][0]["excerpt"]
    assert chunked["citations"][0]["mode"] == "hybrid_rag"
    assert chunked["citations"][0]["bm25_score"] > 0.0
    injected_tokens = sum(estimate_tokens(c["excerpt"]) for c in chunked["citations"])
    assert injected_tokens <= chunked["n_ctx_budget"]

    # Very small budget still yields 1 truncated grounded citation
    tiny = build_attached_files_context(
        large_files,
        "ZIRCON-7788",
        n_ctx=200,
        budget_ratio=0.5,  # budget = 100 tokens
        top_k=4,
    )
    assert tiny["mode"] == "hybrid_rag"
    assert len(tiny["citations"]) == 1
    assert estimate_tokens(tiny["citations"][0]["excerpt"]) <= 100


# ---------------------------------------------------------------------------
# Router integration: POST /api/v1/knowledge-bases/{kb_id}/query
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kb_query_router_modes(test_app, db_proxy, monkeypatch):
    kb = test_app.post(
        "/api/v1/knowledge-bases",
        json={"name": "Router Hybrid Test"},
    ).json()["item"]
    kb_id = kb["_id"]

    q_vec = _unit_vec([1.0, 0.0])
    monkeypatch.setattr(rag_mod.embedding_service, "embed", lambda _q: q_vec)

    await _seed_chunk(
        db_proxy,
        chunk_id="rc1",
        kb_id=kb_id,
        doc_id="rd1",
        filename="policy.md",
        chunk_index=0,
        text="Section 4: FIPS-140-3 cryptographic validation is mandatory.",
        embedding=_unit_vec([0.65, 0.75]),
        page=2,
    )
    await _seed_chunk(
        db_proxy,
        chunk_id="rc2",
        kb_id=kb_id,
        doc_id="rd2",
        filename="intro.md",
        chunk_index=0,
        text="Welcome to the engineering handbook.",
        embedding=_unit_vec([0.92, 0.39]),
        page=1,
    )

    # 1. Default backwards-compatible payload (no mode field) -> hybrid
    r_default = test_app.post(
        f"/api/v1/knowledge-bases/{kb_id}/query",
        json={"query": "FIPS-140-3"},
    )
    assert r_default.status_code == 200
    body_default = r_default.json()
    assert body_default["mode"] == "hybrid"
    assert body_default["citations"][0]["filename"] == "policy.md"
    assert body_default["citations"][0]["mode"] == "hybrid"
    assert "vector_score" in body_default["citations"][0]
    assert "bm25_score" in body_default["citations"][0]

    # 2. Explicit JSON mode="vector"
    r_vec = test_app.post(
        f"/api/v1/knowledge-bases/{kb_id}/query",
        json={"query": "FIPS-140-3", "mode": "vector", "top_k": 2},
    )
    assert r_vec.status_code == 200
    assert r_vec.json()["mode"] == "vector"
    assert r_vec.json()["citations"][0]["filename"] == "intro.md"

    # 3. Query param ?mode=bm25 with minimal JSON payload
    r_bm25 = test_app.post(
        f"/api/v1/knowledge-bases/{kb_id}/query?mode=bm25",
        json={"query": "FIPS-140-3"},
    )
    assert r_bm25.status_code == 200
    assert r_bm25.json()["mode"] == "bm25"
    assert r_bm25.json()["citations"][0]["filename"] == "policy.md"

    # 4. Invalid mode -> 422
    r_bad = test_app.post(
        f"/api/v1/knowledge-bases/{kb_id}/query",
        json={"query": "FIPS-140-3", "mode": "bogus"},
    )
    assert r_bad.status_code == 422
