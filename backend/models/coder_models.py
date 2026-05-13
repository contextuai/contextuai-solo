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
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


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
CoderWorkflowMode = Literal["solo", "sequential", "parallel", "custom"]


class RoleKind(str, Enum):
    CODER = "coder"
    REVIEWER = "reviewer"
    SECURITY = "security"
    UI_UX = "ui_ux"
    DOCS = "docs"
    TESTER = "tester"
    PLANNER = "planner"
    CUSTOM = "custom"


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
    workflow_mode: CoderWorkflowMode = "solo"
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
    workflow_mode: CoderWorkflowMode = "solo"
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


# =============================================================================
# Agent role models
# =============================================================================

def _validate_model_id(v: str) -> str:
    """Validate model_id values.

    Allowed values:
    - Empty string ``""`` — sentinel meaning "not yet configured; the workflow
      will fail fast with a clear error until the user picks a model in the
      Team panel."
    - ``"__DEFAULT__"`` — sentinel meaning "use whatever default model is
      configured."  Only the Custom preset uses this intentionally.
    - Any non-empty, non-whitespace string of length >= 2 — a concrete model ID
      (local catalog ID, or ``provider:model`` prefixed cloud ID).

    Whitespace-only strings are rejected because they are almost certainly
    accidental and would produce confusing "model not found" errors at runtime.
    """
    # Empty string is the "not yet configured" sentinel — always allowed.
    if v == "":
        return v
    if not v.strip():
        raise ValueError("model_id must not be whitespace-only")
    stripped = v.strip()
    if len(stripped) < 2:
        raise ValueError("model_id is too short")
    return stripped


class CoderAgentRole(BaseModel):
    """Persisted shape of a single agent role in the ``coder_agent_roles`` collection."""

    role_id: str
    project_id: str
    role_kind: RoleKind
    display_name: str
    system_prompt: str
    model_id: str
    temperature: float = 0.7
    max_tokens: int = 4096
    enabled: bool = True
    order: int
    created_at: str
    updated_at: str


class CoderAgentRoleCreate(BaseModel):
    role_kind: RoleKind
    display_name: str = Field(..., min_length=1, max_length=200)
    system_prompt: str = Field(..., min_length=1)
    model_id: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0, le=131072)
    enabled: bool = True
    order: Optional[int] = None

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v: str) -> str:
        return _validate_model_id(v)


class CoderAgentRoleUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    system_prompt: Optional[str] = Field(None, min_length=1)
    model_id: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0, le=131072)
    enabled: Optional[bool] = None
    order: Optional[int] = None

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_model_id(v)


class CoderAgentRoleResponse(BaseModel):
    role_id: str
    project_id: str
    role_kind: RoleKind
    display_name: str
    system_prompt: str
    model_id: str
    temperature: float
    max_tokens: int
    enabled: bool
    order: int
    created_at: str
    updated_at: str


# =============================================================================
# Preset models
# =============================================================================

class RolePresetRole(BaseModel):
    role_kind: RoleKind
    display_name: str
    system_prompt: str
    model_id: str
    temperature: float = 0.7
    max_tokens: int = 4096
    enabled: bool = True
    order: int


class RolePresetSummary(BaseModel):
    preset_id: str
    name: str
    description: str
    workflow_mode: CoderWorkflowMode


class RolePresetDetail(BaseModel):
    preset_id: str
    name: str
    description: str
    workflow_mode: CoderWorkflowMode
    roles: List[RolePresetRole]


# =============================================================================
# Workflow request/response
# =============================================================================

class WorkflowModeResponse(BaseModel):
    project_id: str
    workflow_mode: CoderWorkflowMode


class WorkflowModeUpdate(BaseModel):
    workflow_mode: CoderWorkflowMode


class ApplyPresetRequest(BaseModel):
    preset_id: str


class ReorderRolesRequest(BaseModel):
    role_ids: List[str]
