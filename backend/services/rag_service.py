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
import os
import re
import uuid
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
        self, kb_id: str, query: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Return top-k matching chunks, ranked by cosine similarity."""
        if not query.strip():
            return []

        q_vec = await asyncio.to_thread(embedding_service.embed, query)
        q = np.asarray(q_vec, dtype=np.float32)

        chunks = await self.chunk_repo.list_for_kb(kb_id)
        if not chunks:
            return []

        embeddings = np.asarray(
            [c["embedding"] for c in chunks], dtype=np.float32
        )
        scores = embeddings @ q  # cosine for unit vectors
        order = np.argsort(-scores)[:top_k]

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
                    "score": float(scores[i]),
                    "excerpt": c["text"],
                }
            )
        return results

    @staticmethod
    def format_context(citations: List[Dict[str, Any]]) -> str:
        """Format retrieved chunks for injection into a chat prompt."""
        if not citations:
            return ""
        lines = ["[Knowledge Base Context]"]
        for i, c in enumerate(citations, start=1):
            page_str = f" p.{c['page']}" if c.get("page") else ""
            lines.append(f"\n[{i}] {c['filename']}{page_str}")
            lines.append(c["excerpt"])
        lines.append("\n[End Knowledge Base Context]")
        lines.append(
            "\nWhen answering, cite sources inline using [1], [2], ... matching the "
            "numbered sources above. If the answer is not in the context, say so."
        )
        return "\n".join(lines)

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
