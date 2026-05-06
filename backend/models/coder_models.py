"""Pydantic models for the Coder mode (Phase 4 PR 6).

The Coder mode is a second product mode for chat-driven software building
inside a scoped folder. This module defines the project + run schema used by
``backend/routers/coder_projects.py`` and ``backend/services/coder_*.py``.

Scope notes:
- File edits are NOT modelled here — the chat happens via ``/api/v1/ai-chat``.
  The Coder backend just stores chat-thread metadata; conversational-edit
  flow is a follow-up PR.
- Trust is a single per-project boolean. The run endpoint refuses to spawn
  until ``trusted=True``. No tool/binary allowlist yet.
"""

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class CoderProjectStatus(str, Enum):
    CREATED = "created"
    TRUSTED = "trusted"
    RUNNING = "running"
    STOPPED = "stopped"


CoderRuntime = Literal["node", "python", "static", "auto"]
CoderNetworkPolicy = Literal["allow", "block"]


# =============================================================================
# Document shape
# =============================================================================

class CoderProject(BaseModel):
    """Persisted shape of a Coder project row in the ``coder_projects`` collection."""

    project_id: str
    name: str
    folder_path: str
    template_id: Optional[str] = None
    runtime: CoderRuntime = "auto"
    trusted: bool = False
    network_policy: CoderNetworkPolicy = "block"
    chat_thread_id: Optional[str] = None
    last_run_at: Optional[str] = None
    status: CoderProjectStatus = CoderProjectStatus.CREATED
    created_at: str
    updated_at: str


# =============================================================================
# Request models
# =============================================================================

class CoderProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    folder_path: str = Field(..., min_length=1)
    template_id: Optional[str] = None
    runtime: CoderRuntime = "auto"


class CoderProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    trusted: Optional[bool] = None
    network_policy: Optional[CoderNetworkPolicy] = None


class CoderRunRequest(BaseModel):
    """Optional override for the run command. When omitted the service infers
    the run command from the project's template or the folder contents."""
    command: Optional[str] = None


# =============================================================================
# Response models
# =============================================================================

class CoderProjectResponse(BaseModel):
    """Public view of a project — same as the document shape plus the live
    ``process_pid`` derived from in-memory run state."""

    project_id: str
    name: str
    folder_path: str
    template_id: Optional[str] = None
    runtime: CoderRuntime = "auto"
    trusted: bool = False
    network_policy: CoderNetworkPolicy = "block"
    chat_thread_id: Optional[str] = None
    last_run_at: Optional[str] = None
    status: CoderProjectStatus = CoderProjectStatus.CREATED
    created_at: str
    updated_at: str
    process_pid: Optional[int] = None


class CoderProjectListResponse(BaseModel):
    success: bool = True
    projects: List[CoderProjectResponse]
    total_count: int


# =============================================================================
# Templates
# =============================================================================

class CoderTemplateInfo(BaseModel):
    id: str
    name: str
    description: str
    runtime: CoderRuntime
    init_commands: List[str] = Field(default_factory=list)
    starter_prompt: str = ""


class CoderTemplateListResponse(BaseModel):
    templates: List[CoderTemplateInfo]


# =============================================================================
# Run responses
# =============================================================================

CoderRunStatus = Literal["started", "already_running", "failed"]


class CoderRunResponse(BaseModel):
    project_id: str
    status: CoderRunStatus
    error: Optional[str] = None
