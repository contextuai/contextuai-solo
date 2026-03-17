"""
Pydantic models for AI Team Workspace feature
Defines request/response schemas for workspace projects, agents, templates, and execution
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from .workspace_enums import (
    ProjectStatus,
    AgentStatus,
    ComplexityLevel,
    AgentCategory,
    CheckpointAction,
    ProjectType,
)


# ============================================================================
# Agent Models
# ============================================================================

class AgentBlueprint(BaseModel):
    """Full agent definition with capabilities and configuration"""
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., min_length=1, max_length=100, description="Agent display name")
    description: str = Field("", max_length=500, description="Agent description")
    category: AgentCategory = Field(..., description="Agent category classification")
    icon: Optional[str] = Field(None, description="Icon identifier or URL")
    capabilities: List[str] = Field(
        default_factory=list,
        description="List of agent capabilities"
    )
    default_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Default configuration for agent execution"
    )
    estimated_tokens: int = Field(
        default=1000,
        description="Estimated token usage per execution"
    )
    estimated_cost_usd: float = Field(
        default=0.01,
        description="Estimated cost per execution in USD"
    )
    is_system: bool = Field(
        default=False,
        description="Whether this is a system-provided agent"
    )
    created_by: Optional[str] = Field(
        None,
        description="User ID of the creator (None for system agents)"
    )
    is_enabled: bool = Field(
        default=True,
        description="Whether the agent is currently enabled"
    )
    source: Optional[str] = Field(
        None,
        description="Agent source: system, library, custom, admin_edit"
    )
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent-code-gen-001",
                "name": "Code Generator",
                "description": "Generates production-ready code from specifications",
                "category": "code_generation",
                "icon": "code",
                "capabilities": ["typescript", "python", "react", "nextjs"],
                "default_config": {"language": "typescript", "style": "functional"},
                "estimated_tokens": 5000,
                "estimated_cost_usd": 0.05,
                "is_system": True,
                "is_enabled": True,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z"
            }
        }


class AgentSummary(BaseModel):
    """Lightweight agent representation for listings"""
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Agent display name")
    category: AgentCategory = Field(..., description="Agent category")
    icon: Optional[str] = Field(None, description="Icon identifier or URL")
    estimated_cost_usd: float = Field(
        default=0.01,
        description="Estimated cost per execution in USD"
    )
    is_enabled: bool = Field(default=True, description="Whether agent is enabled")

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent-code-gen-001",
                "name": "Code Generator",
                "category": "code_generation",
                "icon": "code",
                "estimated_cost_usd": 0.05,
                "is_enabled": True
            }
        }


# ============================================================================
# Workshop Models
# ============================================================================

class WorkshopConfig(BaseModel):
    """Configuration for workshop/brainstorming projects"""
    topic: str = Field(..., min_length=1, max_length=2000, description="Workshop topic/objective")
    workshop_type: str = Field(
        default="strategy",
        description="Workshop type: strategy, brainstorm, analysis, review, audit"
    )
    num_rounds: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Number of discussion rounds"
    )
    output_format: str = Field(
        default="report",
        description="Output format: report, slides, canvas, brief"
    )
    export_formats: List[str] = Field(
        default_factory=lambda: ["pdf"],
        description="Export formats: pdf, docx, pptx"
    )
    facilitation_style: str = Field(
        default="structured",
        description="Facilitation style: structured, freeform, debate"
    )


class AgentContribution(BaseModel):
    """A single agent's contribution in a workshop round"""
    agent_id: str
    agent_name: str
    round_number: int = 1
    content: str = ""
    sections: Dict[str, str] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class WorkshopResult(BaseModel):
    """Result of a workshop execution"""
    success: bool = True
    contributions: List[AgentContribution] = Field(default_factory=list)
    compiled_output: str = ""
    output_format: str = "report"
    total_tokens: int = 0
    total_cost: float = 0.0


# ============================================================================
# Library Catalog Models
# ============================================================================

class LibraryCatalogEntry(BaseModel):
    """Lightweight catalog entry for browsing the agent library"""
    slug: str = Field(..., description="Agent slug (e.g. 'ceo')")
    name: str = Field(..., description="Agent display name")
    category: str = Field(..., description="Category folder name")
    description: str = Field("", description="First paragraph of .md file")
    frameworks: List[str] = Field(default_factory=list, description="Extracted framework names")
    capabilities: List[str] = Field(default_factory=list, description="Key capabilities")
    file_path: str = Field("", description="Relative path to .md file")


class LibraryAgentDetail(LibraryCatalogEntry):
    """Full agent detail including .md content"""
    full_content: str = Field("", description="Complete .md file content")
    sections: Dict[str, str] = Field(default_factory=dict, description="Parsed sections")


class LibraryImportRequest(BaseModel):
    """Request to import agent(s) from library"""
    category: str = Field(..., description="Category folder name")
    slug: str = Field(..., description="Agent slug")


class LibraryBulkImportRequest(BaseModel):
    """Request to import multiple agents from library"""
    imports: List[LibraryImportRequest] = Field(..., min_length=1)


class LibraryCatalogResponse(BaseModel):
    """Response for library catalog browsing"""
    success: bool = True
    agents: List[LibraryCatalogEntry] = Field(default_factory=list)
    total_count: int = 0
    categories: Dict[str, int] = Field(default_factory=dict, description="Category counts")


class LibrarySyncResult(BaseModel):
    """Result of syncing library .md files to MongoDB"""
    success: bool = True
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = Field(default_factory=list)


# ============================================================================
# Admin Agent Models
# ============================================================================

class AdminAgentUpdate(BaseModel):
    """Admin update for any agent (including system agents)"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = None
    capabilities: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    icon: Optional[str] = None
    estimated_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    is_active: Optional[bool] = None


class AdminAgentCreate(BaseModel):
    """Admin creation of a new agent (no .md backing)"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=10, max_length=2000)
    category: str = Field(...)
    capabilities: List[str] = Field(default_factory=list)
    system_prompt: str = Field(default="")
    icon: Optional[str] = None
    estimated_tokens: int = Field(default=2000)
    estimated_cost_usd: float = Field(default=0.02)


# ============================================================================
# Document Export Models
# ============================================================================

class ExportRequest(BaseModel):
    """Request to export project output as a document"""
    format: str = Field(..., description="Export format: pdf, pptx, html")
    template: str = Field(default="report", description="Template: report, brief, slides")


# ============================================================================
# Project Models
# ============================================================================

class ProjectConfig(BaseModel):
    """Configuration options for project execution"""
    enable_checkpoints: bool = Field(
        default=True,
        description="Enable manual checkpoints for review"
    )
    auto_create_pr: bool = Field(
        default=False,
        description="Automatically create pull request on completion"
    )
    github_repo_url: Optional[str] = Field(
        None,
        description="GitHub repository URL for PR creation"
    )
    generate_docs: bool = Field(
        default=True,
        description="Generate documentation during execution"
    )
    generate_tests: bool = Field(
        default=True,
        description="Generate test cases during execution"
    )
    output_format: str = Field(
        default="markdown",
        description="Output format for generated artifacts"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "enable_checkpoints": True,
                "auto_create_pr": True,
                "github_repo_url": "https://github.com/company/project",
                "generate_docs": True,
                "generate_tests": True,
                "output_format": "markdown"
            }
        }


class CreateProjectRequest(BaseModel):
    """Request model for creating a new workspace project"""
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "name": "E-commerce API Migration",
                "description": "Migrate legacy REST API to GraphQL with TypeScript",
                "tech_stack": ["typescript", "graphql", "nodejs", "postgresql"],
                "complexity": "complex",
                "team_agent_ids": ["agent-code-gen-001", "agent-reviewer-001", "agent-docs-001"],
                "template_id": "template-api-migration",
                "config": {
                    "enable_checkpoints": True,
                    "auto_create_pr": True,
                    "github_repo_url": "https://github.com/company/ecommerce-api"
                }
            }
        }
    }
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Project name"
    )
    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Project title (frontend alias for name)"
    )
    description: str = Field(
        "",
        max_length=2000,
        description="Project description and requirements"
    )
    tech_stack: List[str] = Field(
        default_factory=list,
        description="Technology stack for the project"
    )
    complexity: ComplexityLevel = Field(
        ComplexityLevel.MEDIUM,
        description="Project complexity level"
    )
    team_agent_ids: List[str] = Field(
        default_factory=list,
        description="List of agent IDs to include in the team"
    )
    selected_agents: List[str] = Field(
        default_factory=list,
        description="Agent IDs (frontend alias for team_agent_ids)"
    )
    template_id: Optional[str] = Field(
        None,
        description="Optional template ID to use as base"
    )
    team_template_id: Optional[str] = Field(
        None,
        description="Template ID (frontend alias for template_id)"
    )
    config: Optional[ProjectConfig] = Field(
        None,
        description="Project configuration options"
    )
    git_persona_id: Optional[str] = Field(
        None,
        description="Git persona ID for repository authentication (GitHub/GitLab)"
    )
    project_type: ProjectType = Field(
        default=ProjectType.BUILD,
        description="Project type: build (code generation) or workshop (brainstorming)"
    )
    workshop_config: Optional[WorkshopConfig] = Field(
        None,
        description="Workshop configuration (required when project_type is workshop)"
    )
    model_id: Optional[str] = Field(
        None,
        description="Claude model ID for agent execution (e.g. claude-sonnet-4-6, claude-haiku-4-5-20251001, claude-opus-4-6)"
    )

    @property
    def resolved_name(self) -> str:
        """Get project name from either name or title field"""
        return self.name or self.title or ""

    @property
    def resolved_agent_ids(self) -> List[str]:
        """Get agent IDs from either team_agent_ids or selected_agents"""
        return self.team_agent_ids if self.team_agent_ids else self.selected_agents

    @property
    def resolved_template_id(self) -> Optional[str]:
        """Get template ID from either template_id or team_template_id"""
        return self.template_id or self.team_template_id


class UpdateProjectRequest(BaseModel):
    """Request model for updating an existing project"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    tech_stack: Optional[List[str]] = None
    complexity: Optional[ComplexityLevel] = None
    team_agent_ids: Optional[List[str]] = None
    config: Optional[ProjectConfig] = None
    status: Optional[ProjectStatus] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Project Name",
                "complexity": "enterprise",
                "status": "paused"
            }
        }


class ProjectResponse(BaseModel):
    """Full project response with team information"""
    project_id: str = Field(..., description="Unique project identifier")
    name: str
    title: str = Field("", description="Project title (alias for name)")
    description: str
    tech_stack: List[str]
    complexity: ComplexityLevel
    status: ProjectStatus
    team_agents: List[AgentSummary] = Field(
        default_factory=list,
        description="Team of agents assigned to project"
    )
    selected_agents: List[str] = Field(
        default_factory=list,
        description="Agent IDs in team (frontend compatibility)"
    )
    template_id: Optional[str] = None
    config: ProjectConfig
    project_type: ProjectType = Field(
        default=ProjectType.BUILD,
        description="Project type: build or workshop"
    )
    workshop_config: Optional[WorkshopConfig] = Field(None, description="Workshop config if applicable")
    user_id: str = Field(..., description="Owner user ID")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    updated_at: str = Field(..., description="Last update timestamp (ISO 8601)")
    started_at: Optional[str] = Field(None, description="Execution start timestamp")
    completed_at: Optional[str] = Field(None, description="Execution completion timestamp")
    estimated_cost_usd: float = Field(
        default=0.0,
        description="Estimated total cost in USD"
    )
    actual_cost_usd: float = Field(
        default=0.0,
        description="Actual cost incurred so far"
    )
    progress_percent: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Overall progress percentage"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "project_id": "proj-550e8400-e29b-41d4",
                "name": "E-commerce API Migration",
                "description": "Migrate legacy REST API to GraphQL",
                "tech_stack": ["typescript", "graphql", "nodejs"],
                "complexity": "complex",
                "status": "running",
                "team_agents": [
                    {
                        "agent_id": "agent-code-gen-001",
                        "name": "Code Generator",
                        "category": "code_generation",
                        "icon": "code",
                        "estimated_cost_usd": 0.05,
                        "is_enabled": True
                    }
                ],
                "template_id": "template-api-migration",
                "config": {
                    "enable_checkpoints": True,
                    "auto_create_pr": True,
                    "github_repo_url": "https://github.com/company/ecommerce-api",
                    "generate_docs": True,
                    "generate_tests": True,
                    "output_format": "markdown"
                },
                "user_id": "user-123",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T12:30:00Z",
                "started_at": "2024-01-15T10:05:00Z",
                "completed_at": None,
                "estimated_cost_usd": 2.50,
                "actual_cost_usd": 1.25,
                "progress_percent": 45
            }
        }


class ProjectListItem(BaseModel):
    """Lightweight project summary for listings"""
    project_id: str = Field(..., description="Unique project identifier")
    name: str
    title: str = Field("", description="Project title (alias for name)")
    description: str
    complexity: ComplexityLevel
    status: ProjectStatus
    project_type: ProjectType = Field(default=ProjectType.BUILD, description="Project type")
    team_agent_count: int = Field(default=0, description="Number of agents in team")
    selected_agents: List[str] = Field(default_factory=list, description="Agent IDs in team")
    created_at: str
    updated_at: str
    started_at: Optional[str] = Field(None, description="Execution start timestamp")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")
    progress_percent: int = Field(default=0, ge=0, le=100)
    estimated_cost_usd: float = Field(default=0.0)
    actual_cost_usd: float = Field(default=0.0)

    class Config:
        json_schema_extra = {
            "example": {
                "project_id": "proj-550e8400-e29b-41d4",
                "name": "E-commerce API Migration",
                "description": "Migrate legacy REST API to GraphQL",
                "complexity": "complex",
                "status": "running",
                "team_agent_count": 5,
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T12:30:00Z",
                "progress_percent": 45,
                "estimated_cost_usd": 2.50,
                "actual_cost_usd": 1.25
            }
        }


class ProjectListResponse(BaseModel):
    """Response model for list of projects"""
    success: bool = True
    projects: List[ProjectListItem]
    total_count: int = Field(..., description="Total number of projects")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Items per page")
    last_updated: str = Field(..., description="Timestamp of response")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "projects": [],
                "total_count": 0,
                "page": 1,
                "page_size": 20,
                "last_updated": "2024-01-15T10:00:00Z"
            }
        }


# ============================================================================
# Execution Models
# ============================================================================

class AgentExecutionStep(BaseModel):
    """Execution state for a single agent in a project"""
    agent_id: str = Field(..., description="Agent identifier")
    agent_name: str = Field(..., description="Agent display name")
    status: AgentStatus = Field(..., description="Current execution status")
    started_at: Optional[str] = Field(None, description="Start timestamp (ISO 8601)")
    completed_at: Optional[str] = Field(None, description="Completion timestamp (ISO 8601)")
    duration_ms: Optional[int] = Field(None, description="Execution duration in milliseconds")
    tokens_used: int = Field(default=0, description="Tokens consumed")
    cost_usd: float = Field(default=0.0, description="Cost in USD")
    files_created: List[str] = Field(
        default_factory=list,
        description="List of files created by agent"
    )
    files_modified: List[str] = Field(
        default_factory=list,
        description="List of files modified by agent"
    )
    output_summary: Optional[str] = Field(
        None,
        max_length=1000,
        description="Summary of agent output"
    )
    error: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent-code-gen-001",
                "agent_name": "Code Generator",
                "status": "completed",
                "started_at": "2024-01-15T10:05:00Z",
                "completed_at": "2024-01-15T10:08:30Z",
                "duration_ms": 210000,
                "tokens_used": 5200,
                "cost_usd": 0.052,
                "files_created": ["src/api/users.ts", "src/api/orders.ts"],
                "files_modified": ["src/index.ts"],
                "output_summary": "Generated 2 API endpoint files with full CRUD operations",
                "error": None
            }
        }


class ExecutionResponse(BaseModel):
    """Full execution state for a project"""
    execution_id: str = Field(..., description="Unique execution identifier")
    project_id: str = Field(..., description="Associated project ID")
    status: ProjectStatus = Field(..., description="Overall execution status")
    steps: List[AgentExecutionStep] = Field(
        default_factory=list,
        description="Per-agent execution steps"
    )
    agents: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Per-agent execution details with tokens and cost"
    )
    current_agent_id: Optional[str] = Field(
        None,
        description="Currently executing agent ID"
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Execution context including workshop results"
    )
    result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Execution result data"
    )
    total_tokens: int = Field(default=0, description="Total tokens used")
    total_cost_usd: float = Field(default=0.0, description="Total cost in USD")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    started_at: str = Field(..., description="Execution start timestamp")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")
    error_message: Optional[str] = Field(None, description="Overall error message if failed")

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec-550e8400-e29b-41d4",
                "project_id": "proj-123",
                "status": "running",
                "steps": [
                    {
                        "agent_id": "agent-code-gen-001",
                        "agent_name": "Code Generator",
                        "status": "completed",
                        "started_at": "2024-01-15T10:05:00Z",
                        "completed_at": "2024-01-15T10:08:30Z",
                        "duration_ms": 210000,
                        "tokens_used": 5200,
                        "cost_usd": 0.052,
                        "files_created": ["src/api/users.ts"],
                        "files_modified": [],
                        "output_summary": "Generated API endpoint",
                        "error": None
                    }
                ],
                "current_agent_id": "agent-reviewer-001",
                "total_tokens": 5200,
                "total_cost_usd": 0.052,
                "progress_percent": 33,
                "started_at": "2024-01-15T10:05:00Z",
                "completed_at": None,
                "error_message": None
            }
        }


class SSEProgressEvent(BaseModel):
    """Server-Sent Event for real-time progress updates"""
    type: str = Field(
        ...,
        description="Event type: agent_start, agent_progress, agent_complete, checkpoint, error, complete"
    )
    agent_id: Optional[str] = Field(None, description="Agent ID if applicable")
    agent_name: Optional[str] = Field(None, description="Agent name if applicable")
    progress_percent: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Overall progress percentage"
    )
    message: str = Field(..., description="Human-readable status message")
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional event-specific data"
    )
    cost_so_far_usd: float = Field(default=0.0, description="Cost accumulated so far")
    tokens_so_far: int = Field(default=0, description="Tokens consumed so far")
    timestamp: str = Field(..., description="Event timestamp (ISO 8601)")

    class Config:
        json_schema_extra = {
            "example": {
                "type": "agent_progress",
                "agent_id": "agent-code-gen-001",
                "agent_name": "Code Generator",
                "progress_percent": 45,
                "message": "Generating API endpoints...",
                "data": {"files_created": 2, "files_pending": 3},
                "cost_so_far_usd": 0.032,
                "tokens_so_far": 3200,
                "timestamp": "2024-01-15T10:07:30Z"
            }
        }


# ============================================================================
# Checkpoint Models
# ============================================================================

class CheckpointRequest(BaseModel):
    """Request to handle a checkpoint action"""
    checkpoint_id: str = Field(..., description="Checkpoint identifier")
    action: CheckpointAction = Field(..., description="Action to take")
    modifications: Optional[Dict[str, Any]] = Field(
        None,
        description="Modifications to apply (for modify action)"
    )
    feedback: Optional[str] = Field(
        None,
        max_length=2000,
        description="User feedback for the checkpoint"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "checkpoint_id": "ckpt-550e8400-e29b-41d4",
                "action": "approve",
                "modifications": None,
                "feedback": "Looks good, proceed with implementation"
            }
        }


class CheckpointResponse(BaseModel):
    """Checkpoint details for user review"""
    checkpoint_id: str = Field(..., description="Unique checkpoint identifier")
    project_id: str = Field(..., description="Associated project ID")
    execution_id: str = Field(..., description="Associated execution ID")
    agent_id: str = Field(..., description="Agent that triggered checkpoint")
    agent_name: str = Field(..., description="Agent display name")
    checkpoint_type: str = Field(
        ...,
        description="Type: pre_execution, post_execution, review_required, approval_needed"
    )
    description: str = Field(..., description="Checkpoint description")
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Checkpoint-specific data for review"
    )
    options: List[str] = Field(
        default_factory=list,
        description="Available action options"
    )
    created_at: str = Field(..., description="Checkpoint creation timestamp")
    expires_at: Optional[str] = Field(
        None,
        description="Expiration timestamp if time-limited"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "checkpoint_id": "ckpt-550e8400-e29b-41d4",
                "project_id": "proj-123",
                "execution_id": "exec-456",
                "agent_id": "agent-code-gen-001",
                "agent_name": "Code Generator",
                "checkpoint_type": "review_required",
                "description": "Please review generated API schema before proceeding",
                "data": {
                    "files_to_create": ["src/schema.ts", "src/types.ts"],
                    "preview": "interface User { id: string; name: string; }"
                },
                "options": ["approve", "reject", "modify"],
                "created_at": "2024-01-15T10:06:00Z",
                "expires_at": "2024-01-15T11:06:00Z"
            }
        }


# ============================================================================
# Template Models
# ============================================================================

class TeamTemplate(BaseModel):
    """Template for reusable agent team configurations"""
    template_id: str = Field(..., description="Unique template identifier")
    name: str = Field(..., min_length=1, max_length=100, description="Template name")
    description: str = Field("", max_length=500, description="Template description")
    icon: Optional[str] = Field(None, description="Icon identifier or URL")
    agent_ids: List[str] = Field(
        default_factory=list,
        description="List of agent IDs in the template"
    )
    team_agent_ids: List[str] = Field(
        default_factory=list,
        description="List of agent IDs (frontend alias for agent_ids)"
    )
    estimated_cost_usd: float = Field(
        default=0.0,
        description="Estimated total cost for template execution"
    )
    estimated_time_minutes: int = Field(
        default=0,
        description="Estimated execution time in minutes"
    )
    is_system: bool = Field(
        default=False,
        description="Whether this is a system-provided template"
    )
    user_id: Optional[str] = Field(
        None,
        description="Owner user ID (null for system templates)"
    )
    usage_count: int = Field(
        default=0,
        description="Number of times template has been used"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags for categorization and search"
    )
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "template-api-migration",
                "name": "API Migration Team",
                "description": "Complete team for API migration projects",
                "icon": "migration",
                "agent_ids": ["agent-code-gen-001", "agent-reviewer-001", "agent-docs-001"],
                "estimated_cost_usd": 2.50,
                "estimated_time_minutes": 45,
                "is_system": True,
                "user_id": None,
                "usage_count": 128,
                "tags": ["api", "migration", "backend"],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z"
            }
        }


class CreateTemplateRequest(BaseModel):
    """Request model for creating a new template"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Template name"
    )
    description: str = Field(
        "",
        max_length=500,
        description="Template description"
    )
    icon: Optional[str] = Field(None, description="Icon identifier or URL")
    agent_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of agent IDs to include"
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Tags for categorization"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Custom Review Team",
                "description": "Team focused on code review and quality",
                "icon": "review",
                "agent_ids": ["agent-reviewer-001", "agent-security-001", "agent-perf-001"],
                "tags": ["review", "quality", "custom"]
            }
        }


class TemplateResponse(BaseModel):
    """Template response with resolved agent details"""
    template_id: str = Field(..., description="Unique template identifier")
    name: str
    description: str
    icon: Optional[str] = None
    agents: List[AgentSummary] = Field(
        default_factory=list,
        description="Resolved agent summaries"
    )
    estimated_cost_usd: float = Field(default=0.0)
    estimated_time_minutes: int = Field(default=0)
    is_system: bool = Field(default=False)
    user_id: Optional[str] = None
    usage_count: int = Field(default=0)
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "template_id": "template-api-migration",
                "name": "API Migration Team",
                "description": "Complete team for API migration projects",
                "icon": "migration",
                "agents": [
                    {
                        "agent_id": "agent-code-gen-001",
                        "name": "Code Generator",
                        "category": "code_generation",
                        "icon": "code",
                        "estimated_cost_usd": 0.05,
                        "is_enabled": True
                    }
                ],
                "estimated_cost_usd": 2.50,
                "estimated_time_minutes": 45,
                "is_system": True,
                "user_id": None,
                "usage_count": 128,
                "tags": ["api", "migration", "backend"],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z"
            }
        }


class TemplateListResponse(BaseModel):
    """Response model for list of templates"""
    success: bool = True
    templates: List[TeamTemplate]
    total_count: int = Field(..., description="Total number of templates")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Items per page")
    last_updated: str = Field(..., description="Timestamp of response")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "templates": [],
                "total_count": 0,
                "page": 1,
                "page_size": 20,
                "last_updated": "2024-01-15T10:00:00Z"
            }
        }


# ============================================================================
# Usage/Cost Models
# ============================================================================

class CostEstimateRequest(BaseModel):
    """Request for cost estimation"""
    agent_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of agent IDs to estimate"
    )
    complexity: ComplexityLevel = Field(
        ComplexityLevel.MEDIUM,
        description="Project complexity level"
    )
    include_documentation: bool = Field(
        default=True,
        description="Include documentation generation in estimate"
    )
    include_tests: bool = Field(
        default=True,
        description="Include test generation in estimate"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "agent_ids": ["agent-code-gen-001", "agent-reviewer-001", "agent-docs-001"],
                "complexity": "complex",
                "include_documentation": True,
                "include_tests": True
            }
        }


class CostBreakdown(BaseModel):
    """Cost breakdown per agent"""
    agent_id: str = Field(..., description="Agent identifier")
    agent_name: str = Field(..., description="Agent display name")
    estimated_tokens: int = Field(default=0, description="Estimated tokens")
    estimated_cost_usd: float = Field(default=0.0, description="Estimated cost in USD")

    class Config:
        json_schema_extra = {
            "example": {
                "agent_id": "agent-code-gen-001",
                "agent_name": "Code Generator",
                "estimated_tokens": 5000,
                "estimated_cost_usd": 0.05
            }
        }


class CostEstimateResponse(BaseModel):
    """Response with cost estimation details"""
    estimated_cost_usd: float = Field(
        ...,
        description="Total estimated cost in USD"
    )
    cost_breakdown: List[CostBreakdown] = Field(
        default_factory=list,
        description="Per-agent cost breakdown"
    )
    estimated_time_minutes: int = Field(
        default=0,
        description="Estimated execution time in minutes"
    )
    estimated_tokens: int = Field(
        default=0,
        description="Total estimated tokens"
    )
    credits_required: int = Field(
        default=0,
        description="Platform credits required"
    )
    user_credits_remaining: int = Field(
        default=0,
        description="User's remaining platform credits"
    )
    can_execute: bool = Field(
        default=True,
        description="Whether user has sufficient credits"
    )
    complexity_multiplier: float = Field(
        default=1.0,
        description="Multiplier applied based on complexity"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "estimated_cost_usd": 2.50,
                "cost_breakdown": [
                    {
                        "agent_id": "agent-code-gen-001",
                        "agent_name": "Code Generator",
                        "estimated_tokens": 5000,
                        "estimated_cost_usd": 0.50
                    },
                    {
                        "agent_id": "agent-reviewer-001",
                        "agent_name": "Code Reviewer",
                        "estimated_tokens": 8000,
                        "estimated_cost_usd": 1.00
                    },
                    {
                        "agent_id": "agent-docs-001",
                        "agent_name": "Documentation Writer",
                        "estimated_tokens": 10000,
                        "estimated_cost_usd": 1.00
                    }
                ],
                "estimated_time_minutes": 45,
                "estimated_tokens": 23000,
                "credits_required": 250,
                "user_credits_remaining": 1000,
                "can_execute": True,
                "complexity_multiplier": 1.5
            }
        }


class UsageResponse(BaseModel):
    """User usage and credits information"""
    user_id: str = Field(..., description="User identifier")
    credits_allocated: int = Field(
        default=0,
        description="Total credits allocated to user"
    )
    credits_used: int = Field(
        default=0,
        description="Credits consumed so far"
    )
    credits_remaining: int = Field(
        default=0,
        description="Available credits"
    )
    execution_count: int = Field(
        default=0,
        description="Total number of project executions"
    )
    total_cost_usd: float = Field(
        default=0.0,
        description="Total cost incurred in USD"
    )
    total_tokens_used: int = Field(
        default=0,
        description="Total tokens consumed"
    )
    plan_type: str = Field(
        default="free",
        description="User's subscription plan type"
    )
    reset_date: Optional[str] = Field(
        None,
        description="Next credit reset date (ISO 8601)"
    )
    usage_this_period: Dict[str, Any] = Field(
        default_factory=dict,
        description="Usage breakdown for current billing period"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user-123",
                "credits_allocated": 1000,
                "credits_used": 250,
                "credits_remaining": 750,
                "execution_count": 12,
                "total_cost_usd": 25.00,
                "total_tokens_used": 250000,
                "plan_type": "professional",
                "reset_date": "2024-02-01T00:00:00Z",
                "usage_this_period": {
                    "projects_created": 5,
                    "agents_invoked": 24,
                    "tokens_used": 125000
                }
            }
        }


# ============================================================================
# Custom Agent Models
# ============================================================================

class CreateCustomAgentRequest(BaseModel):
    """Request model for creating a custom agent from natural language description"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Agent display name"
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Natural language description of what the agent should do"
    )
    category: Optional[str] = Field(
        None,
        description="Agent category (auto-detected if not provided)"
    )
    capabilities: Optional[List[str]] = Field(
        None,
        description="Additional capabilities (auto-extracted if not provided)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Python API Tester",
                "description": "An agent that writes comprehensive pytest test suites for FastAPI backends, including unit tests, integration tests, and load testing scripts.",
                "category": "code_quality",
                "capabilities": ["python", "pytest", "fastapi"]
            }
        }


class UpdateCustomAgentRequest(BaseModel):
    """Request model for updating a custom agent"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=10, max_length=2000)
    category: Optional[str] = None
    capabilities: Optional[List[str]] = None
    is_active: Optional[bool] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Agent Name",
                "description": "Updated description for the custom agent",
                "capabilities": ["python", "testing"]
            }
        }


class CustomAgentPreview(BaseModel):
    """Preview of a generated agent blueprint before saving"""
    model_config = {
        "protected_namespaces": (),
        "json_schema_extra": {
            "example": {
                "name": "Python API Tester",
                "description": "An agent that writes pytest test suites for FastAPI backends",
                "category": "code_quality",
                "icon": "check-circle",
                "capabilities": ["python", "pytest", "fastapi", "testing"],
                "system_prompt": "You are a Python API testing specialist...",
                "model_id": "claude-sonnet",
                "estimated_tokens": 2000,
                "estimated_cost_usd": 0.02
            }
        }
    }
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Original description")
    category: str = Field(..., description="Detected or provided category")
    icon: str = Field(..., description="Suggested icon")
    capabilities: List[str] = Field(default_factory=list, description="Extracted capabilities")
    system_prompt: str = Field(..., description="Generated system prompt")
    model_id: str = Field(..., description="Default model ID")
    estimated_tokens: int = Field(default=2000, description="Estimated token usage")
    estimated_cost_usd: float = Field(default=0.02, description="Estimated cost per run")


class CustomAgentResponse(BaseModel):
    """Response wrapping a saved custom agent"""
    success: bool = True
    agent: AgentBlueprint

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "agent": {
                    "agent_id": "custom-abc123",
                    "name": "Python API Tester",
                    "category": "code_quality",
                    "is_system": False,
                    "is_enabled": True
                }
            }
        }


# ============================================================================
# Agent List Response
# ============================================================================

class AgentListResponse(BaseModel):
    """Response model for list of agents"""
    success: bool = True
    agents: List[AgentBlueprint]
    total_count: int = Field(..., description="Total number of agents")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Items per page")
    last_updated: str = Field(..., description="Timestamp of response")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "agents": [],
                "total_count": 0,
                "page": 1,
                "page_size": 20,
                "last_updated": "2024-01-15T10:00:00Z"
            }
        }
