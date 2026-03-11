"""
Pydantic models for AI Automation workflows
Defines request/response schemas for automation CRUD operations
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum


class ExecutionMode(str, Enum):
    """Execution modes for automations"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    SMART = "smart"


class TriggerType(str, Enum):
    """Trigger types for automations"""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    EVENT = "event"


class AutomationStatus(str, Enum):
    """Status values for automations"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


class ExecutionStatus(str, Enum):
    """Status values for automation executions"""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"  # Some steps succeeded, some failed


class OutputActionType(str, Enum):
    """Types of output actions that can be executed after automation completion"""
    GENERATE_PDF = "generate_pdf"
    GENERATE_PPTX = "generate_pptx"
    SEND_EMAIL = "send_email"
    WEBHOOK = "webhook"
    SAVE_FILE = "save_file"
    SLACK_MESSAGE = "slack_message"


class OutputAction(BaseModel):
    """Configuration for a single output action"""
    type: OutputActionType = Field(..., description="Type of output action")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific configuration"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {"type": "generate_pdf", "config": {"title": "Weekly Report", "template": "report"}},
                {"type": "send_email", "config": {"to": ["user@example.com"], "subject": "Report", "include_pdf": True}},
                {"type": "webhook", "config": {"url": "https://hooks.example.com/notify", "method": "POST", "headers": {}}},
                {"type": "save_file", "config": {"format": "json", "filename": "results"}},
            ]
        }


# Request Models
class AutomationCreate(BaseModel):
    """Model for creating a new automation"""
    name: str = Field(..., min_length=1, max_length=100, description="Automation name")
    description: str = Field("", max_length=500, description="Optional description")
    prompt_template: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Natural language prompt with @persona mentions"
    )
    trigger_type: TriggerType = Field(
        TriggerType.MANUAL,
        description="How this automation is triggered"
    )
    trigger_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Configuration for scheduled/event triggers"
    )
    status: AutomationStatus = Field(
        AutomationStatus.DRAFT,
        description="Initial status of the automation"
    )
    output_actions: Optional[List[OutputAction]] = Field(
        None,
        description="Actions to execute after automation completes (PDF, email, webhook, etc.)"
    )
    model_id: Optional[str] = Field(
        None,
        description="Claude model ID for execution (e.g. claude-sonnet-4-6, claude-haiku-4-5-20251001, claude-opus-4-6)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Weekly Sales Report",
                "description": "Generate and send weekly sales report to management",
                "prompt_template": "@sales_db get weekly revenue then @email_sender send to management team",
                "trigger_type": "manual",
                "status": "draft",
                "output_actions": [
                    {"type": "generate_pdf", "config": {"title": "Weekly Report"}},
                    {"type": "webhook", "config": {"url": "https://hooks.example.com/notify", "method": "POST"}}
                ]
            }
        }


class AutomationUpdate(BaseModel):
    """Model for updating an existing automation"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    prompt_template: Optional[str] = Field(None, min_length=10, max_length=5000)
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[Dict[str, Any]] = None
    status: Optional[AutomationStatus] = None
    output_actions: Optional[List[OutputAction]] = None
    model_id: Optional[str] = Field(None, description="Claude model ID for execution")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Updated Weekly Sales Report",
                "status": "active",
                "output_actions": [
                    {"type": "generate_pdf", "config": {"title": "Updated Report"}}
                ]
            }
        }


# Response Models
class AutomationResponse(BaseModel):
    """Model for automation response"""
    automation_id: str = Field(..., description="Unique automation identifier")
    name: str
    description: str
    prompt_template: str
    trigger_type: str
    trigger_config: Optional[Dict[str, Any]]
    user_id: str
    status: str
    created_at: str
    updated_at: str
    last_run: Optional[str] = None
    run_count: int = Field(default=0, description="Number of times executed")
    personas_detected: List[str] = Field(
        default_factory=list,
        description="List of @personas found in prompt"
    )
    execution_mode: str = Field(
        default="smart",
        description="Sequential, parallel, or smart execution"
    )
    output_actions: Optional[List[OutputAction]] = Field(
        None,
        description="Configured output actions for this automation"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "automation_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Weekly Sales Report",
                "description": "Generate and send weekly sales report",
                "prompt_template": "@sales_db get weekly revenue then @email_sender send to management",
                "trigger_type": "manual",
                "trigger_config": None,
                "user_id": "user-123",
                "status": "active",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "last_run": None,
                "run_count": 0,
                "personas_detected": ["sales_db", "email_sender"],
                "execution_mode": "sequential",
                "output_actions": [
                    {"type": "generate_pdf", "config": {"title": "Weekly Report"}}
                ]
            }
        }


class AutomationListResponse(BaseModel):
    """Model for list of automations response"""
    success: bool = True
    automations: List[AutomationResponse]
    total_count: int = Field(..., description="Total number of automations")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Items per page")
    last_updated: str = Field(..., description="Timestamp of response")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "automations": [],
                "total_count": 0,
                "page": 1,
                "page_size": 20,
                "last_updated": "2024-01-15T10:00:00Z"
            }
        }


# Validation Models
class PersonaDetection(BaseModel):
    """Model for detected persona information"""
    name: str = Field(..., description="Persona name (without @ symbol)")
    position: int = Field(..., description="Character position in prompt")
    exists: bool = Field(default=True, description="Whether persona exists in system")


class AutomationValidation(BaseModel):
    """Model for automation validation results"""
    is_valid: bool = Field(..., description="Whether automation is valid")
    personas_detected: List[str] = Field(
        default_factory=list,
        description="List of persona names found"
    )
    execution_mode: ExecutionMode = Field(
        ExecutionMode.SMART,
        description="Detected execution mode"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-blocking validation warnings"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Blocking validation errors"
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="Suggestions for improvement"
    )
    estimated_duration_seconds: Optional[int] = Field(
        None,
        description="Estimated execution duration"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "is_valid": True,
                "personas_detected": ["sales_db", "email_sender"],
                "execution_mode": "sequential",
                "warnings": [],
                "errors": [],
                "suggestions": ["Consider adding error handling for database queries"],
                "estimated_duration_seconds": 15
            }
        }


# Execution Models (Phase 2)
class ExecutionStep(BaseModel):
    """Model for individual automation execution step"""
    step_number: int = Field(..., description="Step sequence number")
    persona: str = Field(..., description="Persona name used in this step")
    instruction: str = Field(..., description="Instruction for this step")
    full_prompt: str = Field(..., description="Complete prompt sent to AI including context")
    result: str = Field(..., description="Result from this step")
    status: ExecutionStatus = Field(..., description="Step execution status")
    error: Optional[str] = Field(None, description="Error message if step failed")
    duration_ms: int = Field(..., description="Step execution duration in milliseconds")

    class Config:
        json_schema_extra = {
            "example": {
                "step_number": 1,
                "persona": "sales_db",
                "instruction": "get weekly revenue",
                "full_prompt": "get weekly revenue\n\nContext: None",
                "result": "Weekly revenue: $50,000",
                "status": "success",
                "error": None,
                "duration_ms": 1500
            }
        }


class AutomationExecutionRequest(BaseModel):
    """Model for manual automation execution"""
    parameters: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional parameters to pass to automation"
    )
    dry_run: bool = Field(
        False,
        description="Validate without executing"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "parameters": {"date_range": "last_7_days"},
                "dry_run": False
            }
        }


class AutomationExecutionResponse(BaseModel):
    """Model for automation execution results"""
    execution_id: str
    automation_id: str
    user_id: str
    status: ExecutionStatus = Field(..., description="Overall execution status")
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = Field(None, description="Total execution duration in milliseconds")
    steps: List[ExecutionStep] = Field(
        default_factory=list,
        description="Detailed step-by-step execution results"
    )
    final_result: str = Field("", description="Aggregated final result")
    error_message: Optional[str] = Field(None, description="Overall error message if execution failed")
    total_steps: int = Field(0, description="Total number of steps")
    successful_steps: int = Field(0, description="Number of successful steps")
    failed_steps: int = Field(0, description="Number of failed steps")
    output_results: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Results from output actions (PDF, email, webhook, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec-550e8400-e29b-41d4",
                "automation_id": "auto-446655440000",
                "user_id": "user-123",
                "status": "success",
                "started_at": "2024-01-15T10:00:00Z",
                "completed_at": "2024-01-15T10:00:15Z",
                "duration_ms": 15500,
                "steps": [
                    {
                        "step_number": 1,
                        "persona": "sales_db",
                        "instruction": "get weekly revenue",
                        "full_prompt": "get weekly revenue",
                        "result": "Weekly revenue: $50,000",
                        "status": "success",
                        "error": None,
                        "duration_ms": 1500
                    }
                ],
                "final_result": "Successfully retrieved revenue and sent email",
                "error_message": None,
                "total_steps": 2,
                "successful_steps": 2,
                "failed_steps": 0,
                "output_results": [
                    {"type": "generate_pdf", "status": "success", "file_id": "file-123", "filename": "Weekly_Report.pdf"},
                    {"type": "webhook", "status": "success", "details": {"status_code": 200}}
                ]
            }
        }


class ExecutionHistoryResponse(BaseModel):
    """Model for list of execution history"""
    success: bool = True
    executions: List[AutomationExecutionResponse]
    total_count: int = Field(..., description="Total number of executions")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(20, description="Items per page")
    last_updated: str = Field(..., description="Timestamp of response")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "executions": [],
                "total_count": 0,
                "page": 1,
                "page_size": 20,
                "last_updated": "2024-01-15T10:00:00Z"
            }
        }
