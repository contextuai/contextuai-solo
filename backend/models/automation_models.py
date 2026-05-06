"""
Pydantic models for Automation workflows.

Solo single-user variant of the enterprise automation models. user_id has
been dropped from the public request/response surface — Solo persists
"desktop" as the static owner internally.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class ExecutionMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    SMART = "smart"


class TriggerType(str, Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT = "event"


class AutomationStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class OutputActionType(str, Enum):
    GENERATE_PDF = "generate_pdf"
    GENERATE_PPTX = "generate_pptx"
    SEND_EMAIL = "send_email"
    WEBHOOK = "webhook"
    SAVE_FILE = "save_file"
    DISTRIBUTE = "distribute"  # Sends through a configured Distribution (LinkedIn, Twitter, blog, slack_webhook, …)
    RUN_CODER_PROJECT = "run_coder_project"  # Runs a Coder project headlessly and captures its output


# =============================================================================
# Embedded sub-models
# =============================================================================

class OutputAction(BaseModel):
    type: OutputActionType
    config: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Request models
# =============================================================================

class AutomationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    prompt_template: str = Field(..., min_length=1, max_length=5000)
    trigger_type: TriggerType = TriggerType.MANUAL
    trigger_config: Optional[Dict[str, Any]] = None
    status: AutomationStatus = AutomationStatus.DRAFT
    output_actions: Optional[List[OutputAction]] = None
    model_id: Optional[str] = None


class AutomationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    prompt_template: Optional[str] = Field(None, min_length=1, max_length=5000)
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[Dict[str, Any]] = None
    status: Optional[AutomationStatus] = None
    output_actions: Optional[List[OutputAction]] = None
    model_id: Optional[str] = None


class AutomationExecutionRequest(BaseModel):
    parameters: Optional[Dict[str, Any]] = None
    dry_run: bool = False


class ValidationRequest(BaseModel):
    prompt_template: str


class PromoteToCrewRequest(BaseModel):
    name: Optional[str] = Field(None, description="Optional name override; defaults to the automation name + ' Crew'")


# =============================================================================
# Response models
# =============================================================================

class AutomationResponse(BaseModel):
    automation_id: str
    name: str
    description: str
    prompt_template: str
    trigger_type: str
    trigger_config: Optional[Dict[str, Any]] = None
    status: str
    created_at: str
    updated_at: str
    last_run: Optional[str] = None
    run_count: int = 0
    personas_detected: List[str] = Field(default_factory=list)
    execution_mode: str = "smart"
    output_actions: Optional[List[OutputAction]] = None
    model_id: Optional[str] = None


class AutomationListResponse(BaseModel):
    success: bool = True
    automations: List[AutomationResponse]
    total_count: int
    page: int = 1
    page_size: int = 20
    last_updated: str


class PersonaDetection(BaseModel):
    name: str
    position: int
    exists: bool = True


class AutomationValidation(BaseModel):
    is_valid: bool
    personas_detected: List[str] = Field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.SMART
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    estimated_duration_seconds: Optional[int] = None


class ExecutionStep(BaseModel):
    step_number: int
    persona: str
    instruction: str
    full_prompt: str = ""
    result: str = ""
    status: str = "pending"  # pending | success | failed | skipped
    error: Optional[str] = None
    duration_ms: int = 0


class AutomationExecutionResponse(BaseModel):
    execution_id: str
    automation_id: str
    status: ExecutionStatus
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    steps: List[ExecutionStep] = Field(default_factory=list)
    final_result: str = ""
    error_message: Optional[str] = None
    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    output_results: Optional[List[Dict[str, Any]]] = None


class ExecutionHistoryResponse(BaseModel):
    success: bool = True
    executions: List[AutomationExecutionResponse]
    total_count: int
    page: int = 1
    page_size: int = 20
    last_updated: str
