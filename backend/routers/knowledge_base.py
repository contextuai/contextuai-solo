"""Knowledge Base REST API.

Endpoints
---------
- GET    /api/v1/knowledge-bases                              — list KBs
- POST   /api/v1/knowledge-bases                              — create a KB
- GET    /api/v1/knowledge-bases/{kb_id}                      — read a KB
- PUT    /api/v1/knowledge-bases/{kb_id}                      — rename / describe
- DELETE /api/v1/knowledge-bases/{kb_id}                      — delete KB + docs + chunks
- GET    /api/v1/knowledge-bases/{kb_id}/documents            — list documents in a KB
- POST   /api/v1/knowledge-bases/{kb_id}/documents            — upload doc(s) (multipart)
- DELETE /api/v1/knowledge-bases/{kb_id}/documents/{doc_id}   — delete a single doc
- POST   /api/v1/knowledge-bases/{kb_id}/query                — semantic search → citations
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from database import get_database
from models.knowledge_base_models import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    QueryRequest,
)
from repositories.chunk_repository import ChunkRepository
from repositories.document_repository import DocumentRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services.rag_service import SUPPORTED_EXTS, RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])


def _kb_repo(db=Depends(get_database)) -> KnowledgeBaseRepository:
    return KnowledgeBaseRepository(db)


def _doc_repo(db=Depends(get_database)) -> DocumentRepository:
    return DocumentRepository(db)


def _chunk_repo(db=Depends(get_database)) -> ChunkRepository:
    return ChunkRepository(db)


def _rag(
    kb=Depends(_kb_repo),
    doc=Depends(_doc_repo),
    chunk=Depends(_chunk_repo),
) -> RAGService:
    return RAGService(kb, doc, chunk)


# ---------------------------------------------------------------------------
# Knowledge Base CRUD
# ---------------------------------------------------------------------------

@router.get("")
async def list_kbs(repo: KnowledgeBaseRepository = Depends(_kb_repo)) -> Dict[str, Any]:
    items = await repo.list_all()
    return {"items": items}


@router.post("")
async def create_kb(
    payload: KnowledgeBaseCreate, repo: KnowledgeBaseRepository = Depends(_kb_repo)
) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    doc = {
        "_id": str(uuid.uuid4()),
        "name": payload.name,
        "description": payload.description,
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dim": 384,
        "doc_count": 0,
        "chunk_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    await repo.create(doc)
    return {"item": doc}


@router.get("/{kb_id}")
async def get_kb(
    kb_id: str, repo: KnowledgeBaseRepository = Depends(_kb_repo)
) -> Dict[str, Any]:
    item = await repo.get_by_id(kb_id)
    if not item:
        raise HTTPException(404, "Knowledge base not found")
    return {"item": item}


@router.put("/{kb_id}")
async def update_kb(
    kb_id: str,
    payload: KnowledgeBaseUpdate,
    repo: KnowledgeBaseRepository = Depends(_kb_repo),
) -> Dict[str, Any]:
    update = payload.model_dump(exclude_none=True)
    if not update:
        raise HTTPException(400, "Nothing to update")
    item = await repo.update(kb_id, update)
    if not item:
        raise HTTPException(404, "Knowledge base not found")
    return {"item": item}


@router.delete("/{kb_id}")
async def delete_kb(
    kb_id: str,
    kb_repo: KnowledgeBaseRepository = Depends(_kb_repo),
    doc_repo: DocumentRepository = Depends(_doc_repo),
    chunk_repo: ChunkRepository = Depends(_chunk_repo),
) -> Dict[str, Any]:
    if not await kb_repo.exists_by_id(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    chunks_deleted = await chunk_repo.delete_for_kb(kb_id)
    docs_deleted = await doc_repo.delete_for_kb(kb_id)
    await kb_repo.delete(kb_id)
    return {"deleted": True, "documents": docs_deleted, "chunks": chunks_deleted}


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.get("/{kb_id}/documents")
async def list_documents(
    kb_id: str,
    kb_repo: KnowledgeBaseRepository = Depends(_kb_repo),
    doc_repo: DocumentRepository = Depends(_doc_repo),
) -> Dict[str, Any]:
    if not await kb_repo.exists_by_id(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    docs = await doc_repo.list_for_kb(kb_id)
    return {"items": docs}


@router.post("/{kb_id}/documents")
async def upload_documents(
    kb_id: str,
    files: List[UploadFile] = File(...),
    kb_repo: KnowledgeBaseRepository = Depends(_kb_repo),
    doc_repo: DocumentRepository = Depends(_doc_repo),
    rag: RAGService = Depends(_rag),
) -> Dict[str, Any]:
    if not await kb_repo.exists_by_id(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    if not files:
        raise HTTPException(400, "No files provided")

    results: List[Dict[str, Any]] = []
    for upload in files:
        filename = upload.filename or "untitled"
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext not in SUPPORTED_EXTS:
            results.append(
                {
                    "filename": filename,
                    "status": "error",
                    "error": f"Unsupported type {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTS))}",
                }
            )
            continue

        content = await upload.read()
        now = datetime.utcnow().isoformat()
        doc_id = str(uuid.uuid4())
        doc = {
            "_id": doc_id,
            "kb_id": kb_id,
            "filename": filename,
            "mime_type": upload.content_type or "application/octet-stream",
            "size_bytes": len(content),
            "page_count": 0,
            "chunk_count": 0,
            "status": "pending",
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        await doc_repo.create(doc)

        try:
            stats = await rag.ingest_document(kb_id, doc_id, filename, content)
            results.append(
                {
                    "id": doc_id,
                    "filename": filename,
                    "status": "ready",
                    "chunks": stats["chunks"],
                    "pages": stats["pages"],
                }
            )
        except Exception as e:
            logger.exception("Failed to ingest %s", filename)
            results.append(
                {
                    "id": doc_id,
                    "filename": filename,
                    "status": "error",
                    "error": str(e),
                }
            )

    return {"items": results}


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: str,
    doc_id: str,
    rag: RAGService = Depends(_rag),
    doc_repo: DocumentRepository = Depends(_doc_repo),
    chunk_repo: ChunkRepository = Depends(_chunk_repo),
) -> Dict[str, Any]:
    doc = await doc_repo.get_by_id(doc_id)
    if not doc or doc.get("kb_id") != kb_id:
        raise HTTPException(404, "Document not found")
    chunks_deleted = await chunk_repo.delete_for_document(doc_id)
    await doc_repo.delete(doc_id)
    await rag._refresh_kb_counts(kb_id)
    return {"deleted": True, "chunks": chunks_deleted}


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

@router.post("/{kb_id}/query")
async def query_kb(
    kb_id: str,
    payload: QueryRequest,
    kb_repo: KnowledgeBaseRepository = Depends(_kb_repo),
    rag: RAGService = Depends(_rag),
) -> Dict[str, Any]:
    if not await kb_repo.exists_by_id(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    citations = await rag.query(kb_id, payload.query, payload.top_k)
    return {"query": payload.query, "citations": citations}
