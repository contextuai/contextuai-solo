"""Coder mode REST + SSE API (Phase 4 PR 6).

Endpoints
---------
- GET    /api/v1/coder/templates
- GET    /api/v1/coder/projects
- POST   /api/v1/coder/projects
- GET    /api/v1/coder/projects/{project_id}
- PUT    /api/v1/coder/projects/{project_id}
- DELETE /api/v1/coder/projects/{project_id}
- POST   /api/v1/coder/projects/{project_id}/start
- POST   /api/v1/coder/projects/{project_id}/stop
- GET    /api/v1/coder/projects/{project_id}/output  (SSE)
- GET    /api/v1/coder/running
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import settings
from database import get_database
from models.coder_models import (
    CoderProjectCreate,
    CoderProjectListResponse,
    CoderProjectResponse,
    CoderProjectStatus,
    CoderProjectUpdate,
    CoderRunRequest,
    CoderRunResponse,
    CoderTemplateListResponse,
)
from models.personal_docs_models import DEFAULT_EXCLUDE_GLOBS
from repositories.chunk_repository import ChunkRepository
from repositories.coder_project_repository import CoderProjectRepository
from repositories.document_repository import DocumentRepository
from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services.coder_project_service import CoderProjectService
from services.coder_run_service import get_run_service
from services.coder_template_service import CoderTemplateService
from services.personal_docs_service import PersonalDocsService
from services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/coder", tags=["coder"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def _template_service() -> CoderTemplateService:
    return CoderTemplateService()


def _project_repo(db=Depends(get_database)) -> CoderProjectRepository:
    return CoderProjectRepository(db)


def _project_service(
    repo: CoderProjectRepository = Depends(_project_repo),
    templates: CoderTemplateService = Depends(_template_service),
) -> CoderProjectService:
    return CoderProjectService(repo, templates, get_run_service())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_response(row: Dict[str, Any]) -> CoderProjectResponse:
    runs = get_run_service()
    pid = runs.get_pid(row.get("project_id") or "")

    raw_status = row.get("status") or "created"
    try:
        status = CoderProjectStatus(raw_status)
    except ValueError:
        status = CoderProjectStatus.CREATED

    return CoderProjectResponse(
        project_id=row.get("project_id") or "",
        name=row.get("name") or "",
        folder_path=row.get("folder_path") or "",
        template_id=row.get("template_id"),
        runtime=row.get("runtime") or "auto",
        trusted=bool(row.get("trusted", False)),
        network_policy=row.get("network_policy") or "block",
        chat_thread_id=row.get("chat_thread_id"),
        last_run_at=row.get("last_run_at"),
        status=status,
        created_at=row.get("created_at") or "",
        updated_at=row.get("updated_at") or "",
        process_pid=pid,
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=CoderTemplateListResponse)
async def list_templates(
    templates: CoderTemplateService = Depends(_template_service),
) -> CoderTemplateListResponse:
    return CoderTemplateListResponse(templates=templates.list_templates())


# ---------------------------------------------------------------------------
# Projects — CRUD
# ---------------------------------------------------------------------------

@router.get("/projects", response_model=CoderProjectListResponse)
async def list_projects(
    repo: CoderProjectRepository = Depends(_project_repo),
) -> CoderProjectListResponse:
    rows = await repo.list_all()
    total = await repo.count()
    return CoderProjectListResponse(
        success=True,
        projects=[_to_response(r) for r in rows],
        total_count=total,
    )


@router.post("/projects", response_model=CoderProjectResponse, status_code=201)
async def create_project(
    payload: CoderProjectCreate,
    service: CoderProjectService = Depends(_project_service),
) -> CoderProjectResponse:
    try:
        row = await service.create_project(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _to_response(row)


@router.get("/projects/{project_id}", response_model=CoderProjectResponse)
async def get_project(
    project_id: str,
    service: CoderProjectService = Depends(_project_service),
) -> CoderProjectResponse:
    row = await service.get_project(project_id)
    if not row:
        raise HTTPException(404, f"Project '{project_id}' not found")
    return _to_response(row)


@router.put("/projects/{project_id}", response_model=CoderProjectResponse)
async def update_project(
    project_id: str,
    payload: CoderProjectUpdate,
    service: CoderProjectService = Depends(_project_service),
) -> CoderProjectResponse:
    update = payload.model_dump(exclude_none=True)
    if not update:
        raise HTTPException(400, "Nothing to update")
    row = await service.update_project(project_id, update)
    if not row:
        raise HTTPException(404, f"Project '{project_id}' not found")
    return _to_response(row)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    service: CoderProjectService = Depends(_project_service),
) -> Dict[str, Any]:
    deleted = await service.delete_project(project_id)
    if not deleted:
        raise HTTPException(404, f"Project '{project_id}' not found")
    return {"deleted": True, "project_id": project_id}


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/start", response_model=CoderRunResponse
)
async def start_project(
    project_id: str,
    payload: Optional[CoderRunRequest] = Body(default=None),
    service: CoderProjectService = Depends(_project_service),
) -> CoderRunResponse:
    override = payload.command if payload else None
    try:
        result = await service.start_project(project_id, command_override=override)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        return CoderRunResponse(
            project_id=project_id, status="failed", error=str(exc)
        )
    return CoderRunResponse(project_id=project_id, status=result["status"])


@router.post(
    "/projects/{project_id}/stop", response_model=CoderRunResponse
)
async def stop_project(
    project_id: str,
    service: CoderProjectService = Depends(_project_service),
) -> CoderRunResponse:
    """Stop a running project.

    Reuses ``CoderRunResponse`` for symmetry with ``/start``: ``started``
    here means "stop request handled — process is no longer running".
    """
    await service.stop_project(project_id)
    return CoderRunResponse(project_id=project_id, status="started")


# ---------------------------------------------------------------------------
# Output streaming + running list
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/output")
async def stream_output(project_id: str) -> StreamingResponse:
    """SSE stream of run output. Closes when the process exits."""
    runs = get_run_service()

    async def gen():
        async for line in runs.tail_output(project_id):
            yield f"data: {json.dumps({'line': line})}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/running")
async def list_running() -> Dict[str, Any]:
    runs = get_run_service()
    return {"running": runs.running_projects()}


# ---------------------------------------------------------------------------
# Cross-mode handoff: register a Coder project folder as a KB folder source
# ---------------------------------------------------------------------------

class IndexAsKBRequest(BaseModel):
    kb_id: str = Field(..., description="Existing knowledge base id")
    label: Optional[str] = None
    schedule: Literal["manual", "1h", "6h", "24h"] = "manual"


@router.post("/projects/{project_id}/index-as-kb")
async def index_project_as_kb(
    project_id: str,
    payload: IndexAsKBRequest,
    repo: CoderProjectRepository = Depends(_project_repo),
    db=Depends(get_database),
) -> Dict[str, Any]:
    """Register a Coder project folder as a Personal-Docs folder source.

    Creates a row in ``kb_folder_sources`` and kicks off an initial
    ``full_sync`` job — same pipeline as
    ``POST /personal-docs/kbs/{kb_id}/folders``.
    """
    project = await repo.get_by_id(project_id)
    if not project:
        raise HTTPException(404, f"Project '{project_id}' not found")

    folder_path = project.get("folder_path")
    if not folder_path or not os.path.isdir(folder_path):
        raise HTTPException(
            400, f"Project folder is missing or invalid: {folder_path!r}"
        )

    kb_repo = KnowledgeBaseRepository(db)
    if not await kb_repo.exists_by_id(payload.kb_id):
        raise HTTPException(404, f"Knowledge base '{payload.kb_id}' not found")

    src_repo = FolderSourceRepository(db)
    label = (
        payload.label
        or f"{project.get('name') or 'Coder project'} (Coder project)"
    )
    source = await src_repo.create_source(
        kb_id=payload.kb_id,
        path=folder_path,
        label=label,
        include_globs=["**/*"],
        exclude_globs=list(DEFAULT_EXCLUDE_GLOBS),
        schedule=payload.schedule,
        max_file_bytes=settings.PERSONAL_DOCS_MAX_FILE_BYTES,
        max_files=settings.PERSONAL_DOCS_MAX_FILES,
        max_depth=settings.PERSONAL_DOCS_MAX_DEPTH,
    )

    # Kick an initial full sync — mirrors personal_docs.create_folder.
    job_repo = IndexJobRepository(db)
    doc_repo = DocumentRepository(db)
    chunk_repo = ChunkRepository(db)
    rag = RAGService(kb_repo, doc_repo, chunk_repo)
    svc = PersonalDocsService(
        src_repo,
        job_repo,
        doc_repo,
        rag,
        friction_threshold=settings.PERSONAL_DOCS_FRICTION_THRESHOLD,
    )
    job = await svc.start_sync(source=source, kind="full_sync")

    return {
        "success": True,
        "source_id": source["_id"],
        "kb_id": payload.kb_id,
        "job_id": job["_id"],
    }
