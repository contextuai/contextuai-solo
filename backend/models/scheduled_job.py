"""
Scheduled Job Models — Pydantic v2 models for cron-based recurring jobs.

A ScheduledJob represents a cron-scheduled task that either publishes
content to a distribution channel (``job_type="post"``) or triggers a
crew run (``job_type="crew"``). Managed by SchedulerService on top of
the APScheduler adapter.
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class ScheduledJob(BaseModel):
    """A persisted cron-scheduled job."""

    model_config = {"protected_namespaces": (), "populate_by_name": True}

    id: Optional[str] = Field(default=None, alias="_id")
    name: str = Field(..., min_length=1, max_length=200)
    job_type: Literal["post", "crew"]
    cron: str = Field(..., description='Standard 5-field cron, e.g. "0 9 * * *"')
    timezone: str = "UTC"
    enabled: bool = True

    # For job_type=post
    channel_id: Optional[str] = None
    content: Optional[str] = None
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    # For job_type=crew
    crew_id: Optional[str] = None
    crew_input: Optional[Dict[str, Any]] = None

    # Tracking
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None  # "success" | "failed"
    last_run_error: Optional[str] = None
    next_run_at: Optional[str] = None
    run_count: int = 0

    created_at: datetime
    updated_at: datetime


class ScheduledJobCreate(BaseModel):
    """Request body to create a new scheduled job."""

    model_config = {"protected_namespaces": ()}

    name: str = Field(..., min_length=1, max_length=200)
    job_type: Literal["post", "crew"]
    cron: str = Field(..., description='Standard 5-field cron, e.g. "0 9 * * *"')
    timezone: str = "UTC"
    enabled: bool = True

    # post
    channel_id: Optional[str] = None
    content: Optional[str] = None
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    # crew
    crew_id: Optional[str] = None
    crew_input: Optional[Dict[str, Any]] = None


class ScheduledJobUpdate(BaseModel):
    """Partial update for an existing scheduled job."""

    model_config = {"protected_namespaces": ()}

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    cron: Optional[str] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None

    channel_id: Optional[str] = None
    content: Optional[str] = None
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    crew_id: Optional[str] = None
    crew_input: Optional[Dict[str, Any]] = None


class ScheduledJobRunResult(BaseModel):
    """Result of an immediate or scheduled job execution."""

    model_config = {"protected_namespaces": ()}

    job_id: str
    job_type: Literal["post", "crew"]
    status: Literal["success", "failed", "skipped"]
    ran_at: str
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
