# Models package for ContextuAI Backend
# Contains Pydantic models for data validation

from .automation_models import (
    AutomationCreate,
    AutomationUpdate,
    AutomationResponse,
    AutomationValidation,
    AutomationListResponse,
    ExecutionMode,
    ExecutionStatus,
    ExecutionStep,
    AutomationExecutionRequest,
    AutomationExecutionResponse,
    ExecutionHistoryResponse
)

from .workspace_enums import (
    ProjectStatus,
    AgentStatus,
    ComplexityLevel,
    AgentCategory,
    CheckpointAction
)

from .workspace_models import (
    # Agent Models
    AgentBlueprint,
    AgentSummary,
    AgentListResponse,
    # Project Models
    ProjectConfig,
    CreateProjectRequest,
    UpdateProjectRequest,
    ProjectResponse,
    ProjectListItem,
    ProjectListResponse,
    # Execution Models
    AgentExecutionStep,
    ExecutionResponse,
    SSEProgressEvent,
    # Checkpoint Models
    CheckpointRequest,
    CheckpointResponse,
    # Template Models
    TeamTemplate,
    CreateTemplateRequest,
    TemplateResponse,
    TemplateListResponse,
    # Usage/Cost Models
    CostEstimateRequest,
    CostBreakdown,
    CostEstimateResponse,
    UsageResponse
)

__all__ = [
    # Automation Models
    "AutomationCreate",
    "AutomationUpdate",
    "AutomationResponse",
    "AutomationValidation",
    "AutomationListResponse",
    "ExecutionMode",
    "ExecutionStatus",
    "ExecutionStep",
    "AutomationExecutionRequest",
    "AutomationExecutionResponse",
    "ExecutionHistoryResponse",
    # Workspace Enums
    "ProjectStatus",
    "AgentStatus",
    "ComplexityLevel",
    "AgentCategory",
    "CheckpointAction",
    # Workspace Agent Models
    "AgentBlueprint",
    "AgentSummary",
    "AgentListResponse",
    # Workspace Project Models
    "ProjectConfig",
    "CreateProjectRequest",
    "UpdateProjectRequest",
    "ProjectResponse",
    "ProjectListItem",
    "ProjectListResponse",
    # Workspace Execution Models
    "AgentExecutionStep",
    "ExecutionResponse",
    "SSEProgressEvent",
    # Workspace Checkpoint Models
    "CheckpointRequest",
    "CheckpointResponse",
    # Workspace Template Models
    "TeamTemplate",
    "CreateTemplateRequest",
    "TemplateResponse",
    "TemplateListResponse",
    # Workspace Usage/Cost Models
    "CostEstimateRequest",
    "CostBreakdown",
    "CostEstimateResponse",
    "UsageResponse"
]
