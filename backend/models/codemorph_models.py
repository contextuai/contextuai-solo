"""
Pydantic models for CodeMorph code migration platform
Defines request/response schemas for migration job operations
"""

from pydantic import BaseModel, Field, validator, field_validator
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class MigrationType(str, Enum):
    """Supported code migration types"""
    JAVA_UPGRADE = "java_upgrade"
    SPRING_BOOT_UPGRADE = "spring_boot_upgrade"
    PYTHON_UPGRADE = "python_upgrade"
    NODEJS_UPGRADE = "nodejs_upgrade"
    DOTNET_UPGRADE = "dotnet_upgrade"
    FRAMEWORK_MIGRATION = "framework_migration"
    DEPENDENCY_UPGRADE = "dependency_upgrade"
    CODE_CONVERSION = "code_conversion"
    CUSTOM = "custom"


class JobStatus(str, Enum):
    """Job execution status states"""
    PENDING = "pending"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPhase(str, Enum):
    """Execution phases during migration"""
    INITIALIZE = "INITIALIZE"
    CLONE = "CLONE"
    ANALYZE = "ANALYZE"
    TRANSFORM = "TRANSFORM"
    BUILD = "BUILD"
    TEST = "TEST"
    VALIDATE = "VALIDATE"
    COMMIT = "COMMIT"
    PUSH = "PUSH"
    PR_CREATE = "PR_CREATE"
    COMPLETE = "COMPLETE"


class CheckpointType(str, Enum):
    """Types of checkpoints that require user approval"""
    HIGH_COMPLEXITY_WARNING = "high_complexity_warning"
    BUILD_FAILURE = "build_failure"
    TEST_FAILURE = "test_failure"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    SECURITY_CONCERN = "security_concern"
    BREAKING_CHANGE = "breaking_change"


# Request Models
class CreateJobRequest(BaseModel):
    """Model for creating a new migration job"""
    repo_url: str = Field(
        ...,
        min_length=1,
        description="Git repository URL (HTTPS or SSH)"
    )
    branch: str = Field(
        "main",
        description="Target branch for migration"
    )
    migration_type: MigrationType = Field(
        ...,
        description="Type of code migration to perform"
    )
    source_version: Optional[str] = Field(
        None,
        description="Current version/framework being migrated from"
    )
    target_version: Optional[str] = Field(
        None,
        description="Target version/framework to migrate to"
    )
    source_language: Optional[str] = Field(
        None,
        description="Source programming language (for code conversion)"
    )
    target_language: Optional[str] = Field(
        None,
        description="Target programming language (for code conversion)"
    )
    run_tests: bool = Field(
        True,
        description="Whether to run tests after migration"
    )
    validate_build: bool = Field(
        True,
        description="Whether to validate build compiles successfully"
    )
    exclude_paths: List[str] = Field(
        default_factory=list,
        description="Paths to exclude from migration"
    )
    include_paths: Optional[List[str]] = Field(
        None,
        description="Specific paths to include (if not all)"
    )
    custom_instructions: Optional[str] = Field(
        None,
        max_length=5000,
        description="Additional migration instructions for AI agent"
    )
    create_pr: bool = Field(
        True,
        description="Automatically create pull request with changes"
    )
    pr_title: Optional[str] = Field(
        None,
        description="Custom PR title (auto-generated if not provided)"
    )
    pr_description: Optional[str] = Field(
        None,
        description="Custom PR description (auto-generated if not provided)"
    )
    requires_approval: bool = Field(
        True,
        description="Whether to pause for approval at checkpoints"
    )
    source_persona_id: Optional[str] = Field(None, description="Persona ID for source repo SCM credentials")
    target_repo_url: Optional[str] = Field(None, description="Target repo URL (for code conversion to a different repo)")
    target_branch: Optional[str] = Field("main", description="Target repo branch")
    target_persona_id: Optional[str] = Field(None, description="Persona ID for target repo SCM credentials")
    model_id: Optional[str] = Field(
        None,
        description="Claude model ID for transformation (e.g. claude-sonnet-4-6, claude-haiku-4-5-20251001, claude-opus-4-6)"
    )

    @field_validator("target_repo_url")
    @classmethod
    def validate_target_repo_url(cls, v):
        if v is not None and not (v.startswith("https://") or v.startswith("git@")):
            raise ValueError("Target repo URL must start with https:// or git@")
        return v

    @validator('repo_url')
    def validate_repo_url(cls, v):
        """Validate repository URL format"""
        if not v.strip():
            raise ValueError('Repository URL cannot be empty')
        # Basic URL validation
        if not (v.startswith('https://') or v.startswith('git@')):
            raise ValueError('Repository URL must be HTTPS or SSH format')
        return v.strip()

    @validator('target_version', always=True)
    def validate_target_version(cls, v, values):
        """Require target_version for non-conversion migration types"""
        migration_type = values.get('migration_type')
        if migration_type and migration_type != MigrationType.CODE_CONVERSION and not v:
            raise ValueError('target_version is required for migration types')
        return v

    @validator('source_language', always=True)
    def validate_source_language(cls, v, values):
        """Require source_language for code conversion"""
        migration_type = values.get('migration_type')
        if migration_type == MigrationType.CODE_CONVERSION and not v:
            raise ValueError('source_language is required for code conversion')
        return v

    @validator('target_language', always=True)
    def validate_target_language(cls, v, values):
        """Require target_language for code conversion"""
        migration_type = values.get('migration_type')
        if migration_type == MigrationType.CODE_CONVERSION and not v:
            raise ValueError('target_language is required for code conversion')
        return v

    @validator('exclude_paths', 'include_paths')
    def validate_paths(cls, v):
        """Validate path lists"""
        if v is None:
            return v
        # Remove empty strings and duplicates
        return list(set(path.strip() for path in v if path.strip()))

    class Config:
        json_schema_extra = {
            "example": {
                "repo_url": "https://github.com/myorg/myproject.git",
                "branch": "main",
                "migration_type": "java_upgrade",
                "source_version": "11",
                "target_version": "17",
                "run_tests": True,
                "validate_build": True,
                "exclude_paths": ["node_modules", "target"],
                "custom_instructions": "Preserve existing logging framework",
                "create_pr": True,
                "requires_approval": True
            }
        }


class JobUpdate(BaseModel):
    """Model for updating job metadata"""
    custom_instructions: Optional[str] = None
    status: Optional[JobStatus] = None


class ApproveCheckpointRequest(BaseModel):
    """Model for approving a checkpoint"""
    checkpoint_id: str = Field(..., description="ID of checkpoint to approve")
    comment: Optional[str] = Field(None, description="Optional approval comment")


class RejectCheckpointRequest(BaseModel):
    """Model for rejecting a checkpoint"""
    checkpoint_id: str = Field(..., description="ID of checkpoint to reject")
    reason: str = Field(..., min_length=1, description="Reason for rejection")


# Response Models
class Job(BaseModel):
    """Model for job response"""
    job_id: str = Field(..., description="Unique job identifier")
    user_id: str = Field(..., description="User who created the job")
    repo_url: str
    repo_name: Optional[str] = Field(None, description="Repository name parsed from URL")
    branch: str
    migration_type: str
    source_version: Optional[str] = None
    target_version: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    status: str
    progress_percentage: int = Field(0, ge=0, le=100)
    current_phase: Optional[str] = None
    current_step: Optional[str] = None
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    checkpoint_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Current checkpoint awaiting approval"
    )
    run_tests: bool = True
    validate_build: bool = True
    exclude_paths: List[str] = Field(default_factory=list)
    include_paths: Optional[List[str]] = None
    custom_instructions: Optional[str] = None
    create_pr: bool = True
    pr_url: Optional[str] = Field(None, description="Pull request URL if created")
    requires_approval: bool = True
    source_persona_id: Optional[str] = Field(None, description="Persona ID for source repo SCM credentials")
    target_repo_url: Optional[str] = Field(None, description="Target repo URL (for code conversion to a different repo)")
    target_branch: Optional[str] = Field("main", description="Target repo branch")
    target_persona_id: Optional[str] = Field(None, description="Persona ID for target repo SCM credentials")
    resume_phase: Optional[str] = Field(None, description="Phase to resume from after checkpoint approval")
    analysis_result: Optional[Dict[str, Any]] = Field(None, description="Persisted ANALYZE output for resume")
    model_id: Optional[str] = Field(None, description="Claude model ID selected for transformation")

    # Cost tracking fields (populated after TRANSFORM phase via Claude Agent SDK)
    cost_usd: Optional[float] = Field(None, description="Total cost in USD for the TRANSFORM phase")
    input_tokens: Optional[int] = Field(None, description="Input tokens consumed")
    output_tokens: Optional[int] = Field(None, description="Output tokens consumed")
    total_tokens: Optional[int] = Field(None, description="Total tokens (input + output)")
    model_used: Optional[str] = Field(None, description="AI model used for transformation")
    num_turns: Optional[int] = Field(None, description="Number of agent turns in TRANSFORM")
    transform_duration_ms: Optional[int] = Field(None, description="TRANSFORM phase duration in milliseconds")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-550e8400-e29b-41d4-a716-446655440000",
                "user_id": "user-123",
                "repo_url": "https://github.com/myorg/myproject.git",
                "branch": "main",
                "migration_type": "java_upgrade",
                "source_version": "11",
                "target_version": "17",
                "status": "processing",
                "progress_percentage": 45,
                "current_phase": "TRANSFORM",
                "current_step": "Migrating javax to jakarta imports",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:05:30Z",
                "started_at": "2024-01-15T10:00:15Z",
                "completed_at": None,
                "error_message": None,
                "result": None,
                "checkpoint_data": None,
                "run_tests": True,
                "validate_build": True,
                "exclude_paths": ["node_modules", "target"],
                "custom_instructions": None,
                "create_pr": True,
                "pr_url": None,
                "requires_approval": True
            }
        }


class JobListResponse(BaseModel):
    """Model for list of jobs response"""
    success: bool = True
    jobs: List[Job]
    total_count: int = Field(..., description="Total number of jobs matching filters")
    limit: int = Field(20, description="Items per page")
    offset: int = Field(0, description="Number of items skipped")
    has_more: bool = Field(False, description="Whether more results exist")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "jobs": [],
                "total_count": 0,
                "limit": 20,
                "offset": 0,
                "has_more": False
            }
        }


class JobStatusResponse(BaseModel):
    """Model for quick job status check"""
    job_id: str
    status: str
    progress_percentage: int
    current_phase: Optional[str] = None
    current_step: Optional[str] = None
    updated_at: str
    has_checkpoint: bool = Field(False, description="Whether job is waiting at checkpoint")


class Checkpoint(BaseModel):
    """Model for checkpoint information"""
    checkpoint_id: str
    job_id: str
    checkpoint_type: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    requires_action: bool = True
    actions: List[str] = Field(
        default_factory=lambda: ["approve", "reject"],
        description="Available actions for this checkpoint"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "checkpoint_id": "cp-550e8400-e29b",
                "job_id": "job-550e8400-e29b-41d4-a716-446655440000",
                "checkpoint_type": "high_complexity_warning",
                "message": "High migration complexity detected in 5 files",
                "details": {
                    "files": ["UserService.java", "OrderController.java"],
                    "complexity_score": 8.5,
                    "recommendation": "Manual review recommended for complex async patterns"
                },
                "created_at": "2024-01-15T10:05:30Z",
                "requires_action": True,
                "actions": ["approve", "reject"]
            }
        }


class CheckpointResponse(BaseModel):
    """Model for checkpoint response"""
    success: bool
    checkpoint: Checkpoint
    job: Job


class ArtifactsResponse(BaseModel):
    """Model for job artifacts response"""
    success: bool = True
    job_id: str
    artifacts: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of artifact names to presigned URLs"
    )
    expires_in_seconds: int = Field(
        3600,
        description="How long presigned URLs are valid"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "job_id": "job-550e8400-e29b-41d4-a716-446655440000",
                "artifacts": {
                    "migration_report": "https://s3.amazonaws.com/...",
                    "diff_summary": "https://s3.amazonaws.com/...",
                    "test_results": "https://s3.amazonaws.com/..."
                },
                "expires_in_seconds": 3600
            }
        }


class LogsResponse(BaseModel):
    """Model for job logs response"""
    success: bool = True
    job_id: str
    logs: Optional[str] = Field(None, description="Log content if small enough")
    log_url: Optional[str] = Field(None, description="Presigned URL for large logs")
    log_size_bytes: int = Field(0, description="Size of logs in bytes")
    expires_in_seconds: Optional[int] = Field(
        None,
        description="How long presigned URL is valid (if provided)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "job_id": "job-550e8400-e29b-41d4-a716-446655440000",
                "logs": None,
                "log_url": "https://s3.amazonaws.com/...",
                "log_size_bytes": 524288,
                "expires_in_seconds": 3600
            }
        }


# WebSocket Message Models
class ProgressMessage(BaseModel):
    """WebSocket progress update message"""
    type: str = "progress"
    job_id: str
    status: str
    phase: Optional[str] = None
    progress_percentage: int
    current_step: Optional[str] = None
    timestamp: str


class CheckpointMessage(BaseModel):
    """WebSocket checkpoint notification message"""
    type: str = "checkpoint"
    job_id: str
    checkpoint_type: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    actions: List[str] = Field(default_factory=lambda: ["approve", "reject"])


class CompletedMessage(BaseModel):
    """WebSocket completion message"""
    type: str = "completed"
    job_id: str
    result: Dict[str, Any]


class ErrorMessage(BaseModel):
    """WebSocket error message"""
    type: str = "error"
    job_id: str
    error: str
    details: Optional[Dict[str, Any]] = None
