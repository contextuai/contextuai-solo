"""
Coder Workflow Router

Endpoints for running a Coder project's multi-agent workflow.

Routes
------
POST /api/v1/coder/projects/{project_id}/run
    Body: {"message": "...", "history": [...]}
    Returns: text/event-stream (SSE). Calls CoderWorkflowService.run().

POST /api/v1/coder/projects/{project_id}/run/preview
    Body: {"message": "...", "history": [...]}
    Returns: JSON plan — which roles will run, in what order, with what model.
    No model calls are made.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import get_database
from services.coder_workflow_service import CoderWorkflowService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/coder/projects",
    tags=["coder-workflow"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class HistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class RunRequest(BaseModel):
    message: str
    history: Optional[List[HistoryMessage]] = None


# ---------------------------------------------------------------------------
# POST /run — streaming SSE
# ---------------------------------------------------------------------------

@router.post("/{project_id}/run")
async def run_workflow(
    project_id: str,
    body: RunRequest,
    db=Depends(get_database),
):
    """Execute the project's workflow and stream the combined output as SSE.

    The SSE stream emits events in the order described in
    ``coder_workflow_service.py``. Always ends with ``data: [DONE]``.
    """
    history: List[Dict[str, Any]] = []
    if body.history:
        history = [{"role": m.role, "content": m.content} for m in body.history]

    svc = CoderWorkflowService(db)

    async def _event_stream():
        try:
            async for chunk in svc.run(project_id, body.message, history):
                yield chunk
        except Exception as exc:
            import json as _json
            logger.exception("Workflow run failed for project %s", project_id)
            yield f"data: {_json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /run/preview — plan as JSON, no model calls
# ---------------------------------------------------------------------------

@router.post("/{project_id}/run/preview")
async def preview_workflow(
    project_id: str,
    body: RunRequest,
    db=Depends(get_database),
) -> Dict[str, Any]:
    """Return the execution plan as JSON without making any model calls.

    Useful for the UI to render the workflow card before the user hits Send.
    """
    svc = CoderWorkflowService(db)
    plan = await svc.preview(project_id)
    if "error" in plan:
        raise HTTPException(status_code=404, detail=plan["error"])
    return plan
