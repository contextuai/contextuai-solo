"""
Crew Models — Pydantic models for Crew configuration, runs, and API contracts.

Crews are reusable teams of AI agents that can be scheduled, executed repeatedly,
and maintain shared memory across runs.
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Literal, Union, Annotated
from pydantic import BaseModel, Field, model_validator, Discriminator


# =============================================================================
# Enums
# =============================================================================

class CrewStatus(str, Enum):
    """Lifecycle status of a crew configuration."""
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class CrewRunStatus(str, Enum):
    """Status of a single crew execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CrewAgentRole(str, Enum):
    """Predefined roles an agent can play within a crew."""
    RESEARCHER = "researcher"
    WRITER = "writer"
    EDITOR = "editor"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"
    DEVELOPER = "developer"
    DESIGNER = "designer"
    STRATEGIST = "strategist"
    CUSTOM = "custom"


class ExecutionMode(str, Enum):
    """How agents in the crew are executed."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    AUTONOMOUS = "autonomous"


# =============================================================================
# Embedded Sub-Models
# =============================================================================

class CrewAgentConfig(BaseModel):
    """Configuration for a single agent within a crew."""
    model_config = {"protected_namespaces": ()}

    agent_id: Optional[str] = None
    role: CrewAgentRole = CrewAgentRole.CUSTOM
    custom_role: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=100)
    instructions: str = Field(..., min_length=1)
    persona_id: Optional[str] = None
    model_id: Optional[str] = None
    tools: List[str] = Field(default_factory=list)
    order: int = Field(default=0, ge=0)
    depends_on: List[str] = Field(default_factory=list)
    library_agent_id: Optional[str] = Field(
        None, description="Workspace agent library ID this agent was sourced from"
    )


class CrewExecutionConfig(BaseModel):
    """Execution settings for a crew run."""
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    max_iterations: int = Field(default=1, ge=1, le=50)
    timeout_seconds: int = Field(default=600, ge=30, le=7200)
    retry_on_failure: bool = False
    max_retries: int = Field(default=0, ge=0, le=5)
    checkpoint_enabled: bool = False
    # Autonomous mode settings
    max_agent_invocations: int = Field(
        default=10, ge=1, le=50,
        description="Max agents the coordinator can invoke (autonomous mode)"
    )
    budget_limit_usd: float = Field(
        default=1.0, ge=0.01, le=100.0,
        description="Budget cap in USD for autonomous agent invocations"
    )


class CrewSchedule(BaseModel):
    """Optional schedule for automatic crew execution."""
    enabled: bool = False
    cron_expression: Optional[str] = None
    timezone: str = "UTC"
    next_run_at: Optional[str] = None


class ChannelBinding(BaseModel):
    """Binds a crew to a social/messaging connection for inbound/outbound use."""
    channel_type: str = Field(..., description="e.g. telegram, discord, linkedin, twitter, instagram, facebook")
    enabled: bool = True
    approval_required: bool = False


class DistributionChannel(BaseModel):
    """Output distribution channel for crew results."""
    channel_type: str = Field(..., description="e.g. slack, email, webhook, s3")
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ConnectionBinding(BaseModel):
    """Binds a crew to a connection (platform auth) with a direction.

    Direction controls whether the crew listens on inbound messages from this
    connection, publishes outbound via it, or both.
    """
    connection_id: str = Field(..., description="ID of the underlying connection record (oauth_tokens.id, reddit_accounts.id, etc.)")
    platform: str = Field(..., description="telegram | discord | reddit | linkedin | twitter | instagram | facebook | blog | email | slack_webhook")
    direction: Literal["inbound", "outbound", "both"] = "both"


class ReactiveTrigger(BaseModel):
    """Fires when an inbound message on `connection_id` matches any keyword/hashtag/mention."""
    type: Literal["reactive"] = "reactive"
    connection_id: str
    keywords: List[str] = Field(default_factory=list)
    hashtags: List[str] = Field(default_factory=list)
    mentions: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_at_least_one_match(self):
        if not (self.keywords or self.hashtags or self.mentions):
            raise ValueError("Reactive trigger requires at least one of keywords, hashtags, or mentions")
        return self


class ScheduledTrigger(BaseModel):
    """Fires on a cron schedule (repeating) or at `run_at` (one-shot)."""
    type: Literal["scheduled"] = "scheduled"
    connection_ids: List[str] = Field(default_factory=list)
    cron: Optional[str] = None
    run_at: Optional[str] = Field(None, description="ISO-8601 datetime for one-shot scheduling")
    content_brief: Optional[str] = None

    @model_validator(mode="after")
    def require_exactly_one_schedule(self):
        if bool(self.cron) == bool(self.run_at):
            raise ValueError("Scheduled trigger requires exactly one of `cron` or `run_at`")
        return self


CrewTrigger = Annotated[Union[ReactiveTrigger, ScheduledTrigger], Discriminator("type")]


# =============================================================================
# Request Models
# =============================================================================

class CreateCrewRequest(BaseModel):
    """Request to create a new crew."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=10000)
    agents: List[CrewAgentConfig] = Field(default_factory=list, max_length=20)
    execution_config: CrewExecutionConfig = Field(default_factory=CrewExecutionConfig)
    schedule: Optional[CrewSchedule] = None
    channel_bindings: List[ChannelBinding] = Field(default_factory=list)
    distribution_channels: List[DistributionChannel] = Field(default_factory=list)
    connection_bindings: List[ConnectionBinding] = Field(default_factory=list)
    triggers: List[CrewTrigger] = Field(default_factory=list)
    approval_required: bool = False
    memory_enabled: bool = True
    tags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_agents_for_mode(self):
        """Non-autonomous modes require at least 1 agent; autonomous allows empty."""
        mode = self.execution_config.mode if self.execution_config else ExecutionMode.SEQUENTIAL
        if mode != ExecutionMode.AUTONOMOUS and len(self.agents) < 1:
            raise ValueError("At least 1 agent is required for non-autonomous execution modes")
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Content Research Crew",
                "description": "Researches topics and produces structured reports",
                "agents": [
                    {
                        "name": "Researcher",
                        "role": "researcher",
                        "instructions": "Search the web and gather data on the given topic.",
                        "tools": ["web_search"],
                        "order": 0
                    },
                    {
                        "name": "Writer",
                        "role": "writer",
                        "instructions": "Write a structured report from the research findings.",
                        "order": 1,
                        "depends_on": ["Researcher"]
                    }
                ],
                "execution_config": {"mode": "sequential", "timeout_seconds": 300},
                "memory_enabled": True,
                "tags": ["content", "research"]
            }
        }


class UpdateCrewRequest(BaseModel):
    """Request to update an existing crew."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=10000)
    agents: Optional[List[CrewAgentConfig]] = None
    execution_config: Optional[CrewExecutionConfig] = None
    schedule: Optional[CrewSchedule] = None
    channel_bindings: Optional[List[ChannelBinding]] = None
    distribution_channels: Optional[List[DistributionChannel]] = None
    connection_bindings: Optional[List[ConnectionBinding]] = None
    triggers: Optional[List[CrewTrigger]] = None
    approval_required: Optional[bool] = None
    memory_enabled: Optional[bool] = None
    tags: Optional[List[str]] = None
    status: Optional[CrewStatus] = None


class RunCrewRequest(BaseModel):
    """Request to execute a crew."""
    input: Optional[str] = Field(None, description="Input prompt or task for the crew")
    input_data: Optional[Dict[str, Any]] = Field(None, description="Structured input data")
    override_config: Optional[CrewExecutionConfig] = None


# =============================================================================
# Response Models
# =============================================================================

class CrewResponse(BaseModel):
    """Full crew configuration response."""
    id: Optional[str] = None
    crew_id: str
    user_id: str
    name: str
    description: Optional[str] = None
    status: str = CrewStatus.ACTIVE.value
    agents: List[CrewAgentConfig] = Field(default_factory=list)
    execution_config: CrewExecutionConfig = Field(default_factory=CrewExecutionConfig)
    schedule: Optional[CrewSchedule] = None
    channel_bindings: List[ChannelBinding] = Field(default_factory=list)
    distribution_channels: List[DistributionChannel] = Field(default_factory=list)
    connection_bindings: List[ConnectionBinding] = Field(default_factory=list)
    triggers: List[CrewTrigger] = Field(default_factory=list)
    approval_required: bool = False
    memory_enabled: bool = True
    tags: List[str] = Field(default_factory=list)
    total_runs: int = 0
    total_cost_usd: float = 0.0
    last_run_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class CrewListItem(BaseModel):
    """Lightweight crew item for list views."""
    id: Optional[str] = None
    crew_id: str
    name: str
    description: Optional[str] = None
    status: str
    agent_count: int = 0
    execution_config: Optional[CrewExecutionConfig] = None
    total_runs: int = 0
    total_cost_usd: float = 0.0
    last_run_at: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CrewListResponse(BaseModel):
    """Paginated crew list response."""
    success: bool = True
    crews: List[CrewListItem]
    total_count: int
    page: int = 1
    page_size: int = 20


# =============================================================================
# Crew Run Models
# =============================================================================

class CrewRunAgentState(BaseModel):
    """Runtime state of an individual agent during a crew run."""
    agent_id: str
    name: str
    role: str
    status: str = CrewRunStatus.PENDING.value
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    iteration: int = 0


class CrewRunResponse(BaseModel):
    """Full crew run (execution) response."""
    id: Optional[str] = None
    run_id: str
    crew_id: str
    user_id: str
    status: str = CrewRunStatus.PENDING.value
    input: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    agents: List[CrewRunAgentState] = Field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    duration_ms: Optional[int] = None
    trigger_type: Literal["reactive", "scheduled", "manual"] = "manual"
    trigger_source: Optional[str] = Field(
        None,
        description="connection_id (reactive), cron expression or run_at (scheduled), or 'manual' (button)"
    )

    class Config:
        from_attributes = True


class CrewRunListItem(BaseModel):
    """Lightweight crew run for list views."""
    id: Optional[str] = None
    run_id: str
    crew_id: str
    status: str
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: Optional[str] = None
    trigger_type: Literal["reactive", "scheduled", "manual"] = "manual"
    trigger_source: Optional[str] = None


class CrewRunListResponse(BaseModel):
    """Paginated crew run list."""
    success: bool = True
    runs: List[CrewRunListItem]
    total_count: int
    page: int = 1
    page_size: int = 20
