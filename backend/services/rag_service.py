"""
RAG service: ingest, chunk, embed, retrieve.

Uses the bundled all-MiniLM-L6-v2 ONNX embedding service (384-dim, unit-normalised).
Vectors are stored as JSON float arrays in SQLite via the motor_compat layer.
Retrieval uses numpy dot-product (= cosine similarity for unit vectors).
"""
import asyncio
import hashlib
import io
import logging
import math
import os
import re
import uuid
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from repositories.chunk_repository import ChunkRepository
from repositories.document_repository import DocumentRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

# ~500 tokens per chunk, ~50 token overlap (rough char/token ratio)
CHUNK_SIZE_CHARS = 2000
CHUNK_OVERLAP_CHARS = 200
EMBED_BATCH_SIZE = 32

SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md"}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def estimate_tokens(text: str) -> int:
    """Rough ~4 chars/token estimator for context-budget routing."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _bm25_scores(
    query: str,
    texts: List[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> np.ndarray:
    """Zero-dependency Okapi BM25 scorer over lowercase alphanumeric tokens."""
    n_docs = len(texts)
    if n_docs == 0:
        return np.zeros(0, dtype=np.float32)

    q_tokens = _TOKEN_RE.findall((query or "").lower())
    if not q_tokens:
        return np.zeros(n_docs, dtype=np.float32)

    doc_counters: List[Counter[str]] = []
    doc_lens = np.zeros(n_docs, dtype=np.float64)
    df: Counter[str] = Counter()

    for idx, text in enumerate(texts):
        tokens = _TOKEN_RE.findall((text or "").lower())
        doc_lens[idx] = len(tokens)
        counts = Counter(tokens)
        doc_counters.append(counts)
        for term in counts:
            df[term] += 1

    avgdl = float(doc_lens.mean())
    if avgdl <= 0.0:
        return np.zeros(n_docs, dtype=np.float32)

    scores = np.zeros(n_docs, dtype=np.float64)
    for term in q_tokens:
        term_df = df.get(term, 0)
        if term_df == 0:
            continue
        # Non-negative Lucene/Okapi IDF so single-doc & small-corpus matches stay > 0
        idf = math.log((n_docs - term_df + 0.5) / (term_df + 0.5) + 1.0)
        for idx, counts in enumerate(doc_counters):
            tf = counts.get(term, 0)
            if tf == 0:
                continue
            denom = tf + k1 * (1.0 - b + b * (doc_lens[idx] / avgdl))
            scores[idx] += idf * (tf * (k1 + 1.0)) / denom

    return scores.astype(np.float32)


def _normalize_scores(arr: np.ndarray, *, binary_if_flat: bool = False) -> np.ndarray:
    """Normalize dense cosine ([0, 1] clamp) or BM25 (max-scale to [0, 1])."""
    if arr.size == 0:
        return arr
    if not binary_if_flat:
        return np.clip(arr, 0.0, 1.0).astype(np.float32)
    hi = float(np.max(arr))
    if hi <= 0.0:
        return np.zeros_like(arr, dtype=np.float32)
    return (np.maximum(0.0, arr) / hi).astype(np.float32)


def _format_numbered_sections(
    sections: List[Tuple[str, str]],
    *,
    label: str = "Knowledge Base Context",
) -> str:
    """Format numbered context sections with inline citation instructions."""
    if not sections:
        return ""
    lines = [f"[{label}]"]
    for idx, (header, body) in enumerate(sections, start=1):
        lines.append(f"\n[{idx}] {header}")
        lines.append(body)
    lines.append(f"\n[End {label}]")
    lines.append(
        "\nWhen answering, cite sources inline using [1], [2], ... matching the "
        "numbered sources above. If the answer is not in the context, say so."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parsing + chunking (synchronous, run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _chunk_text(text: str, page: Optional[int] = None) -> List[Dict[str, Any]]:
    text = _clean(text)
    if not text:
        return []

    if len(text) <= CHUNK_SIZE_CHARS:
        return [{"text": text, "page": page}]

    chunks: List[Dict[str, Any]] = []
    step = CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
    for start in range(0, len(text), step):
        piece = text[start : start + CHUNK_SIZE_CHARS]
        if not piece.strip():
            continue
        chunks.append({"text": piece, "page": page})
        if start + CHUNK_SIZE_CHARS >= len(text):
            break
    return chunks


def _parse_pdf(content: bytes) -> List[Dict[str, Any]]:
    import fitz  # PyMuPDF

    out: List[Dict[str, Any]] = []
    doc = fitz.open(stream=content, filetype="pdf")
    try:
        for page_num, page in enumerate(doc, start=1):
            page_text = page.get_text() or ""
            if page_text.strip():
                out.extend(_chunk_text(page_text, page=page_num))
    finally:
        doc.close()
    return out


def _parse_docx(content: bytes) -> List[Dict[str, Any]]:
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(content))
    text = "\n".join(p.text for p in doc.paragraphs if p.text)
    return _chunk_text(text, page=None)


def _parse_text(content: bytes) -> List[Dict[str, Any]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="replace")
    return _chunk_text(text, page=None)


def _parse_html(content: bytes) -> List[Dict[str, Any]]:
    """Strip HTML tags before chunking. Falls back to raw text if bs4 missing."""
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:  # pragma: no cover — bs4 is a transitive dep
        return _parse_text(content)
    try:
        soup = BeautifulSoup(content, "html.parser")
    except Exception:
        return _parse_text(content)
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return _chunk_text(text, page=None)


def _parse_file(filename: str, content: bytes) -> Tuple[List[Dict[str, Any]], int]:
    name = filename.lower()
    if name.endswith(".pdf"):
        chunks = _parse_pdf(content)
        pages = max((c.get("page") or 0 for c in chunks), default=0)
        return chunks, pages
    if name.endswith(".docx"):
        return _parse_docx(content), 0
    if name.endswith(".txt") or name.endswith(".md"):
        return _parse_text(content), 0
    if name.endswith(".html") or name.endswith(".htm"):
        return _parse_html(content), 0
    if name.endswith(".rtf") or name.endswith(".csv") or name.endswith(".json"):
        # Treat as raw text — adequate for embeddings and avoids extra deps.
        return _parse_text(content), 0
    raise ValueError(f"Unsupported file type: {filename}")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RAGService:
    def __init__(
        self,
        kb_repo: KnowledgeBaseRepository,
        doc_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
    ):
        self.kb_repo = kb_repo
        self.doc_repo = doc_repo
        self.chunk_repo = chunk_repo

    async def ingest_document(
        self,
        kb_id: str,
        doc_id: str,
        filename: str,
        content: bytes,
    ) -> Dict[str, Any]:
        """Parse → chunk → embed → persist. Updates document + KB rollups."""
        await self.doc_repo.set_status(doc_id, "indexing")

        try:
            chunks, page_count = await asyncio.to_thread(_parse_file, filename, content)

            if not chunks:
                await self.doc_repo.set_status(
                    doc_id, "ready", page_count=page_count, chunk_count=0
                )
                await self._refresh_kb_counts(kb_id)
                return {"chunks": 0, "pages": page_count}

            texts = [c["text"] for c in chunks]
            embeddings: List[List[float]] = []
            for i in range(0, len(texts), EMBED_BATCH_SIZE):
                batch = texts[i : i + EMBED_BATCH_SIZE]
                vecs = await asyncio.to_thread(embedding_service.embed_batch, batch)
                embeddings.extend(vecs)

            now = datetime.utcnow().isoformat()
            for idx, (chunk, vec) in enumerate(zip(chunks, embeddings)):
                chunk_doc = {
                    "_id": str(uuid.uuid4()),
                    "kb_id": kb_id,
                    "doc_id": doc_id,
                    "doc_filename": filename,
                    "chunk_index": idx,
                    "page": chunk.get("page"),
                    "text": chunk["text"],
                    "embedding": vec,
                    "created_at": now,
                    "updated_at": now,
                }
                await self.chunk_repo.collection.insert_one(chunk_doc)

            await self.doc_repo.set_status(
                doc_id,
                "ready",
                page_count=page_count,
                chunk_count=len(chunks),
            )
            await self._refresh_kb_counts(kb_id)

            return {"chunks": len(chunks), "pages": page_count}
        except Exception as e:
            logger.exception("Ingest failed for doc %s", doc_id)
            await self.doc_repo.set_status(doc_id, "error", error=str(e))
            raise

    async def _refresh_kb_counts(self, kb_id: str) -> None:
        docs = await self.doc_repo.list_for_kb(kb_id)
        chunk_count = await self.chunk_repo.count_for_kb(kb_id)
        await self.kb_repo.update_counts(kb_id, len(docs), chunk_count)

    async def query(
        self,
        kb_id: str,
        query: str,
        top_k: int = 5,
        mode: str = "hybrid",
        alpha: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """Return top-k matching chunks using hybrid (dense + BM25), vector, or bm25."""
        if not query or not query.strip() or top_k <= 0:
            return []

        mode_norm = (mode or "hybrid").strip().lower()
        if mode_norm not in {"hybrid", "vector", "bm25"}:
            raise ValueError(f"Unsupported retrieval mode: {mode}")

        chunks = await self.chunk_repo.list_for_kb(kb_id)
        if not chunks:
            return []

        texts = [c.get("text", "") for c in chunks]
        dense: Optional[np.ndarray] = None
        bm25: Optional[np.ndarray] = None

        if mode_norm in {"hybrid", "vector"}:
            q_vec = await asyncio.to_thread(embedding_service.embed, query)
            q = np.asarray(q_vec, dtype=np.float32)
            embeddings = np.asarray(
                [c["embedding"] for c in chunks], dtype=np.float32
            )
            dense = embeddings @ q

        if mode_norm in {"hybrid", "bm25"}:
            bm25 = _bm25_scores(query, texts)

        if mode_norm == "vector":
            assert dense is not None
            final_scores = dense
        elif mode_norm == "bm25":
            assert bm25 is not None
            final_scores = _normalize_scores(bm25, binary_if_flat=True)
        else:
            assert dense is not None and bm25 is not None
            dense_norm = _normalize_scores(dense, binary_if_flat=False)
            bm25_norm = _normalize_scores(bm25, binary_if_flat=True)
            final_scores = alpha * dense_norm + (1.0 - alpha) * bm25_norm

        order = np.argsort(-final_scores, kind="stable")[:top_k]

        results: List[Dict[str, Any]] = []
        for idx in order:
            i = int(idx)
            c = chunks[i]
            results.append(
                {
                    "doc_id": c["doc_id"],
                    "filename": c["doc_filename"],
                    "page": c.get("page"),
                    "chunk_index": int(c.get("chunk_index", 0)),
                    "score": float(final_scores[i]),
                    "vector_score": float(dense[i]) if dense is not None else 0.0,
                    "bm25_score": float(bm25[i]) if bm25 is not None else 0.0,
                    "excerpt": c["text"],
                    "mode": mode_norm,
                }
            )
        return results

    async def smart_retrieve(
        self,
        kb_id: str,
        query: str,
        n_ctx: int = 8192,
        top_k: int = 5,
        budget_ratio: float = 0.5,
        alpha: float = 0.6,
    ) -> Dict[str, Any]:
        """Inject entire KB when within token budget; otherwise fall back to hybrid RAG."""
        budget = max(0, int(n_ctx * budget_ratio))
        chunks = await self.chunk_repo.list_for_kb(kb_id)
        chunks_sorted = sorted(
            chunks,
            key=lambda c: (str(c.get("doc_id", "")), int(c.get("chunk_index", 0))),
        )
        total_tokens = sum(estimate_tokens(c.get("text", "")) for c in chunks_sorted)

        if chunks_sorted and total_tokens <= budget:
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for c in chunks_sorted:
                did = str(c.get("doc_id", ""))
                grouped.setdefault(did, []).append(c)

            citations: List[Dict[str, Any]] = []
            sections: List[Tuple[str, str]] = []
            for idx, (doc_id, doc_chunks) in enumerate(grouped.items(), start=1):
                filename = (
                    doc_chunks[0].get("doc_filename")
                    or doc_chunks[0].get("filename")
                    or "document"
                )
                parts: List[str] = []
                last_page: Any = object()
                first_page: Optional[int] = None
                for c in doc_chunks:
                    txt = (c.get("text") or "").strip()
                    if not txt:
                        continue
                    pg = c.get("page")
                    if first_page is None and pg is not None:
                        first_page = pg
                    if pg is not None and pg != last_page:
                        parts.append(f"[Page {pg}]\n{txt}")
                    else:
                        parts.append(txt)
                    last_page = pg

                full_text = "\n\n".join(parts)
                excerpt = (
                    full_text
                    if len(full_text) <= 500
                    else full_text[:497] + "..."
                )
                sections.append((filename, full_text))
                citations.append(
                    {
                        "index": idx,
                        "doc_id": doc_id,
                        "filename": filename,
                        "page": first_page,
                        "chunk_index": int(doc_chunks[0].get("chunk_index", 0)),
                        "score": 1.0,
                        "vector_score": 0.0,
                        "bm25_score": 0.0,
                        "excerpt": excerpt,
                        "mode": "full_context",
                    }
                )

            return {
                "mode": "full_context",
                "total_tokens": total_tokens,
                "n_ctx_budget": budget,
                "citations": citations,
                "context_block": _format_numbered_sections(
                    sections, label="Knowledge Base Context"
                ),
            }

        raw_citations = await self.query(
            kb_id,
            query,
            top_k=top_k,
            mode="hybrid",
            alpha=alpha,
        )
        citations = [
            {"index": i, **c} for i, c in enumerate(raw_citations, start=1)
        ]
        return {
            "mode": "hybrid_rag",
            "total_tokens": total_tokens,
            "n_ctx_budget": budget,
            "citations": citations,
            "context_block": self.format_context(citations),
        }

    @staticmethod
    def format_context(citations: List[Dict[str, Any]]) -> str:
        """Format retrieved chunks for injection into a chat prompt."""
        if not citations:
            return ""
        sections: List[Tuple[str, str]] = []
        for c in citations:
            page_str = f" p.{c['page']}" if c.get("page") else ""
            sections.append((f"{c['filename']}{page_str}", c["excerpt"]))
        return _format_numbered_sections(sections, label="Knowledge Base Context")

    # ------------------------------------------------------------------
    # Folder-source ingest paths
    # ------------------------------------------------------------------

    async def ingest_from_path(
        self,
        *,
        kb_id: str,
        source_id: str,
        abs_path: str,
        label_of_source: str,
        existing_doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Read a file from disk and ingest as a folder-source document.

        If `existing_doc_id` is provided, the previous document + its
        chunks are removed first so the file is treated as updated.
        """
        with open(abs_path, "rb") as fh:
            content = fh.read()
        st = os.stat(abs_path)
        content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        filename = os.path.basename(abs_path)

        if existing_doc_id:
            await self.chunk_repo.delete_for_document(existing_doc_id)
            await self.doc_repo.delete(existing_doc_id)

        now = datetime.utcnow().isoformat()
        doc_id = str(uuid.uuid4())
        doc = {
            "_id": doc_id,
            "kb_id": kb_id,
            "filename": filename,
            "mime_type": "application/octet-stream",
            "size_bytes": st.st_size,
            "page_count": 0,
            "chunk_count": 0,
            "status": "pending",
            "error": None,
            "source_type": "folder",
            "source_id": source_id,
            "source_label": label_of_source,
            "abs_path": abs_path,
            "mtime": st.st_mtime,
            "content_hash": content_hash,
            "created_at": now,
            "updated_at": now,
        }
        await self.doc_repo.collection.insert_one(doc)
        return await self.ingest_document(kb_id, doc_id, filename, content)

    async def delete_for_source(self, kb_id: str, source_id: str) -> int:
        """Drop every document + every chunk owned by a folder source."""
        docs = await self.doc_repo.list_for_source(source_id)
        chunks_deleted = 0
        for d in docs:
            chunks_deleted += await self.chunk_repo.delete_for_document(d["_id"])
        await self.doc_repo.delete_for_source(source_id)
        await self._refresh_kb_counts(kb_id)
        return chunks_deleted


def build_attached_files_context(
    file_items: List[Dict[str, Any]],
    query: str,
    n_ctx: int = 8192,
    budget_ratio: float = 0.5,
    top_k: int = 6,
) -> Dict[str, Any]:
    """Smart-inject ad-hoc attached files whole or via chunked BM25 within budget."""
    budget = max(0, int(n_ctx * budget_ratio))
    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(file_items or []):
        text = (item.get("text") or "").strip()
        if not text:
            continue
        normalized.append(
            {
                "file_id": str(
                    item.get("file_id")
                    or item.get("doc_id")
                    or item.get("id")
                    or f"file-{idx}"
                ),
                "filename": str(item.get("filename") or f"attachment-{idx + 1}.txt"),
                "text": text,
                "page": item.get("page"),
            }
        )

    total_tokens = sum(estimate_tokens(item["text"]) for item in normalized)
    if not normalized:
        return {
            "mode": "full_context",
            "total_tokens": 0,
            "n_ctx_budget": budget,
            "citations": [],
            "context_block": "",
        }

    if total_tokens <= budget:
        citations: List[Dict[str, Any]] = []
        sections: List[Tuple[str, str]] = []
        for idx, item in enumerate(normalized, start=1):
            page = item.get("page")
            page_str = f" p.{page}" if page else ""
            header = f"{item['filename']}{page_str}"
            sections.append((header, item["text"]))
            excerpt = (
                item["text"]
                if len(item["text"]) <= 500
                else item["text"][:497] + "..."
            )
            citations.append(
                {
                    "index": idx,
                    "doc_id": item["file_id"],
                    "filename": item["filename"],
                    "page": page,
                    "chunk_index": 0,
                    "score": 1.0,
                    "excerpt": excerpt,
                    "mode": "full_context",
                }
            )
        return {
            "mode": "full_context",
            "total_tokens": total_tokens,
            "n_ctx_budget": budget,
            "citations": citations,
            "context_block": _format_numbered_sections(
                sections, label="Attached Files Context"
            ),
        }

    # Over token budget: chunk and rank with Okapi BM25
    all_chunks: List[Dict[str, Any]] = []
    for item in normalized:
        chunks = _chunk_text(item["text"], page=item.get("page"))
        for c_idx, ch in enumerate(chunks):
            all_chunks.append(
                {
                    "file_id": item["file_id"],
                    "filename": item["filename"],
                    "page": ch.get("page"),
                    "chunk_index": c_idx,
                    "text": ch["text"],
                }
            )

    if not all_chunks or top_k <= 0:
        return {
            "mode": "hybrid_rag",
            "total_tokens": total_tokens,
            "n_ctx_budget": budget,
            "citations": [],
            "context_block": "",
        }

    raw_scores = _bm25_scores(query, [c["text"] for c in all_chunks])
    norm_scores = _normalize_scores(raw_scores, binary_if_flat=True)
    order = np.argsort(-raw_scores, kind="stable")

    picked: List[Tuple[int, Dict[str, Any], str]] = []
    used_tokens = 0
    for idx_val in order:
        orig_idx = int(idx_val)
        ch = all_chunks[orig_idx]
        ch_text = ch["text"]
        toks = estimate_tokens(ch_text)

        if picked and used_tokens + toks > budget:
            continue
        if not picked and budget > 0 and toks > budget:
            max_chars = max(1, budget * 4)
            ch_text = ch_text[:max_chars]
            toks = estimate_tokens(ch_text)

        picked.append((orig_idx, ch, ch_text))
        used_tokens += toks
        if len(picked) >= top_k or used_tokens >= budget:
            break

    citations = []
    sections = []
    for rank_idx, (orig_idx, ch, ch_text) in enumerate(picked, start=1):
        page = ch.get("page")
        page_str = f" p.{page}" if page else ""
        sections.append((f"{ch['filename']}{page_str}", ch_text))
        citations.append(
            {
                "index": rank_idx,
                "doc_id": ch["file_id"],
                "filename": ch["filename"],
                "page": page,
                "chunk_index": ch["chunk_index"],
                "score": float(norm_scores[orig_idx]),
                "bm25_score": float(raw_scores[orig_idx]),
                "excerpt": ch_text,
                "mode": "hybrid_rag",
            }
        )

    return {
        "mode": "hybrid_rag",
        "total_tokens": total_tokens,
        "n_ctx_budget": budget,
        "citations": citations,
        "context_block": _format_numbered_sections(
            sections, label="Attached Files Context"
        ),
    }
