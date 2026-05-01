"""REST + SSE for Personal Docs folder mappings.

Routes
------
- GET    /api/v1/personal-docs/kbs/{kb_id}/folders        — list mappings
- POST   /api/v1/personal-docs/kbs/{kb_id}/folders        — add mapping + start full sync
- GET    /api/v1/personal-docs/folders/{source_id}        — read one
- PUT    /api/v1/personal-docs/folders/{source_id}        — edit
- DELETE /api/v1/personal-docs/folders/{source_id}        — remove (cascade docs+chunks)
- POST   /api/v1/personal-docs/folders/{source_id}/sync   — trigger incremental sync
- GET    /api/v1/personal-docs/folders/{source_id}/jobs   — recent jobs
- GET    /api/v1/personal-docs/jobs/{job_id}              — job detail
- POST   /api/v1/personal-docs/jobs/{job_id}/confirm      — confirm friction-modal
- POST   /api/v1/personal-docs/jobs/{job_id}/cancel       — request cancellation
- GET    /api/v1/personal-docs/jobs/{job_id}/stream       — SSE progress stream
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import settings
from database import get_database
from models.personal_docs_models import (
    DEFAULT_EXCLUDE_GLOBS,
    FolderSourceCreate,
    FolderSourceUpdate,
)
from repositories.chunk_repository import ChunkRepository
from repositories.document_repository import DocumentRepository
from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services.personal_docs_service import PersonalDocsService
from services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/personal-docs", tags=["personal-docs"])


# ---------------------------------------------------------------------------
# Dependency wiring
# ---------------------------------------------------------------------------

def _src_repo(db=Depends(get_database)) -> FolderSourceRepository:
    return FolderSourceRepository(db)


def _job_repo(db=Depends(get_database)) -> IndexJobRepository:
    return IndexJobRepository(db)


def _kb_repo(db=Depends(get_database)) -> KnowledgeBaseRepository:
    return KnowledgeBaseRepository(db)


def _doc_repo(db=Depends(get_database)) -> DocumentRepository:
    return DocumentRepository(db)


def _chunk_repo(db=Depends(get_database)) -> ChunkRepository:
    return ChunkRepository(db)


def _service(
    src=Depends(_src_repo),
    jobs=Depends(_job_repo),
    docs=Depends(_doc_repo),
    kb=Depends(_kb_repo),
    chunks=Depends(_chunk_repo),
) -> PersonalDocsService:
    rag = RAGService(kb, docs, chunks)
    return PersonalDocsService(
        src, jobs, docs, rag,
        friction_threshold=settings.PERSONAL_DOCS_FRICTION_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# Folder source CRUD
# ---------------------------------------------------------------------------

@router.get("/kbs/{kb_id}/folders")
async def list_folders(
    kb_id: str,
    src: FolderSourceRepository = Depends(_src_repo),
    kb: KnowledgeBaseRepository = Depends(_kb_repo),
) -> Dict[str, Any]:
    if not await kb.exists_by_id(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    return {"items": await src.list_for_kb(kb_id)}


@router.post("/kbs/{kb_id}/folders")
async def create_folder(
    kb_id: str,
    payload: FolderSourceCreate,
    kb: KnowledgeBaseRepository = Depends(_kb_repo),
    src: FolderSourceRepository = Depends(_src_repo),
    svc: PersonalDocsService = Depends(_service),
) -> Dict[str, Any]:
    if not await kb.exists_by_id(kb_id):
        raise HTTPException(404, "Knowledge base not found")
    if not os.path.isdir(payload.path):
        raise HTTPException(400, f"Folder does not exist: {payload.path}")

    label = (
        payload.label
        or os.path.basename(payload.path.rstrip("/\\"))
        or payload.path
    )
    source = await src.create_source(
        kb_id=kb_id,
        path=payload.path,
        label=label,
        include_globs=payload.include_globs,
        exclude_globs=payload.exclude_globs or list(DEFAULT_EXCLUDE_GLOBS),
        schedule=payload.schedule,
        max_file_bytes=(
            payload.max_file_bytes or settings.PERSONAL_DOCS_MAX_FILE_BYTES
        ),
        max_files=payload.max_files or settings.PERSONAL_DOCS_MAX_FILES,
        max_depth=payload.max_depth or settings.PERSONAL_DOCS_MAX_DEPTH,
    )
    job = await svc.start_sync(source=source, kind="full_sync")
    return {"source": source, "job_id": job["_id"]}


@router.get("/folders/{source_id}")
async def get_folder(
    source_id: str, src: FolderSourceRepository = Depends(_src_repo),
) -> Dict[str, Any]:
    s = await src.get_source(source_id)
    if not s:
        raise HTTPException(404, "Folder source not found")
    return {"item": s}


@router.put("/folders/{source_id}")
async def update_folder(
    source_id: str,
    payload: FolderSourceUpdate,
    src: FolderSourceRepository = Depends(_src_repo),
) -> Dict[str, Any]:
    s = await src.get_source(source_id)
    if not s:
        raise HTTPException(404, "Folder source not found")
    update = payload.model_dump(exclude_none=True)
    if not update:
        raise HTTPException(400, "Nothing to update")
    await src.update_source(source_id, update)
    return {"item": await src.get_source(source_id)}


@router.delete("/folders/{source_id}")
async def delete_folder(
    source_id: str,
    src: FolderSourceRepository = Depends(_src_repo),
    svc: PersonalDocsService = Depends(_service),
) -> Dict[str, Any]:
    s = await src.get_source(source_id)
    if not s:
        raise HTTPException(404, "Folder source not found")
    await svc.delete_source(source=s)
    return {"deleted": True}


@router.post("/folders/{source_id}/sync")
async def sync_folder(
    source_id: str,
    src: FolderSourceRepository = Depends(_src_repo),
    svc: PersonalDocsService = Depends(_service),
) -> Dict[str, Any]:
    s = await src.get_source(source_id)
    if not s:
        raise HTTPException(404, "Folder source not found")
    job = await svc.start_sync(source=s, kind="incremental")
    return {"job_id": job["_id"], "status": job["status"]}


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@router.get("/folders/{source_id}/jobs")
async def list_jobs(
    source_id: str, jobs: IndexJobRepository = Depends(_job_repo),
) -> Dict[str, Any]:
    return {"items": await jobs.list_for_source(source_id)}


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str, jobs: IndexJobRepository = Depends(_job_repo),
) -> Dict[str, Any]:
    j = await jobs.get_job(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return {"item": j}


@router.post("/jobs/{job_id}/confirm")
async def confirm_job(
    job_id: str,
    jobs: IndexJobRepository = Depends(_job_repo),
    svc: PersonalDocsService = Depends(_service),
) -> Dict[str, Any]:
    j = await jobs.get_job(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    if j["status"] != "awaiting_confirmation":
        raise HTTPException(409, f"Job is in status {j['status']}")
    await svc.confirm(job_id=job_id)
    return {"ok": True}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    jobs: IndexJobRepository = Depends(_job_repo),
    svc: PersonalDocsService = Depends(_service),
) -> Dict[str, Any]:
    if not await jobs.get_job(job_id):
        raise HTTPException(404, "Job not found")
    await svc.cancel(job_id=job_id)
    return {"ok": True}


@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: str, jobs: IndexJobRepository = Depends(_job_repo),
) -> StreamingResponse:
    async def gen():
        last_payload = None
        # Cap stream at ~1 hour at 0.5s tick = 7200 iterations.
        for _ in range(7200):
            j = await jobs.get_job(job_id)
            if not j:
                yield (
                    "event: error\n"
                    f"data: {json.dumps({'error': 'not_found'})}\n\n"
                )
                return
            payload = json.dumps({
                "id": j["_id"],
                "status": j["status"],
                "files_total": j.get("files_total", 0),
                "files_done": j.get("files_done", 0),
                "files_added": j.get("files_added", 0),
                "files_updated": j.get("files_updated", 0),
                "files_removed": j.get("files_removed", 0),
                "bytes_total": j.get("bytes_total", 0),
                "bytes_done": j.get("bytes_done", 0),
                "error": j.get("error"),
            })
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            if j["status"] in ("done", "error", "cancelled"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")
