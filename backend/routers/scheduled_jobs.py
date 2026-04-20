"""
Scheduled Jobs Router — REST API for cron-based post + crew jobs.

Endpoints (prefix ``/api/v1/scheduled-jobs``):

- ``GET /``                          — list jobs (paginated)
- ``POST /``                         — create
- ``GET /{id}``                      — detail
- ``PATCH /{id}``                    — update (re-registers on cron change)
- ``DELETE /{id}``                   — delete (unregisters from scheduler)
- ``POST /{id}/run-now``             — fire immediately
- ``POST /{id}/toggle``              — pause/resume
- ``GET /validate-cron?expr=...``    — validate a cron string, preview runs
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from models.scheduled_job import (
    ScheduledJobCreate,
    ScheduledJobUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduled-jobs", tags=["scheduled-jobs"])


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------


def _get_scheduler_service(request: Request):
    """Pull the SchedulerService instance off ``app.state``.

    Constructed during startup in ``app.py`` after the APScheduler
    adapter has been initialised.
    """
    svc = getattr(request.app.state, "scheduler_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler service not initialised",
        )
    return svc


# ------------------------------------------------------------------
# Validation helper
# ------------------------------------------------------------------


def _validate_job_payload(data: Dict[str, Any]) -> None:
    """Validate cron string + per-job-type required fields."""
    from apscheduler.triggers.cron import CronTrigger

    cron_expr = data.get("cron")
    tz = data.get("timezone") or "UTC"
    if cron_expr:
        try:
            CronTrigger.from_crontab(cron_expr, timezone=tz)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid cron expression: {exc}",
            )

    job_type = data.get("job_type")
    if job_type == "post":
        if not data.get("channel_id"):
            raise HTTPException(400, "channel_id is required for post jobs")
        if not data.get("content"):
            raise HTTPException(400, "content is required for post jobs")
    elif job_type == "crew":
        if not data.get("crew_id"):
            raise HTTPException(400, "crew_id is required for crew jobs")


# ------------------------------------------------------------------
# Cron preview (must be before /{id} to avoid collision)
# ------------------------------------------------------------------


@router.get("/validate-cron")
async def validate_cron(
    expr: str = Query(..., description="Standard 5-field cron expression"),
    timezone_name: str = Query("UTC", alias="timezone"),
    count: int = Query(5, ge=1, le=20),
):
    """Validate a cron expression and return the next N fire times."""
    from apscheduler.triggers.cron import CronTrigger

    try:
        trigger = CronTrigger.from_crontab(expr, timezone=timezone_name)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cron expression: {exc}",
        )

    runs: List[str] = []
    previous = None
    now = datetime.now(timezone.utc)
    for _ in range(count):
        nxt = trigger.get_next_fire_time(previous, now if previous is None else previous)
        if nxt is None:
            break
        runs.append(nxt.isoformat())
        previous = nxt

    return {
        "valid": True,
        "cron": expr,
        "timezone": timezone_name,
        "next_runs": runs,
    }


# ------------------------------------------------------------------
# List + create
# ------------------------------------------------------------------


@router.get("/")
async def list_scheduled_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    svc=Depends(_get_scheduler_service),
):
    """List all scheduled jobs with live ``next_run_at`` annotations."""
    jobs = await svc.list_jobs(skip=skip, limit=limit)
    total = await svc.repo.count_all()
    return {
        "status": "success",
        "data": {"jobs": jobs, "total": total, "skip": skip, "limit": limit},
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_scheduled_job(
    request: ScheduledJobCreate,
    svc=Depends(_get_scheduler_service),
):
    """Create a new scheduled job and register it with APScheduler."""
    payload = request.model_dump()
    _validate_job_payload(payload)

    job = await svc.repo.create_job(payload)
    if job.get("enabled"):
        try:
            job = await svc.register(job["id"]) or job
        except Exception as exc:
            logger.exception("Failed to register new scheduled job")
            # Rollback the DB row so the UI doesn't show a phantom job.
            await svc.repo.delete_job(job["id"])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to register job: {exc}",
            )
    return {"status": "success", "data": job}


# ------------------------------------------------------------------
# Detail / update / delete
# ------------------------------------------------------------------


@router.get("/{job_id}")
async def get_scheduled_job(
    job_id: str,
    svc=Depends(_get_scheduler_service),
):
    job = await svc.repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled job not found")
    next_run = svc._get_next_run_time(job_id)
    if next_run is not None:
        job["next_run_at"] = next_run
    return {"status": "success", "data": job}


@router.patch("/{job_id}")
async def update_scheduled_job(
    job_id: str,
    request: ScheduledJobUpdate,
    svc=Depends(_get_scheduler_service),
):
    existing = await svc.repo.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled job not found")

    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    # Validate merged payload so half-updates still make sense.
    merged = {**existing, **updates}
    _validate_job_payload(merged)

    job = await svc.repo.update_job(job_id, updates)

    # Re-register whenever a field that affects scheduling changes.
    reschedule_keys = {"cron", "timezone", "enabled"}
    if reschedule_keys.intersection(updates.keys()):
        job = await svc.register(job_id) or job

    return {"status": "success", "data": job}


@router.delete("/{job_id}")
async def delete_scheduled_job(
    job_id: str,
    svc=Depends(_get_scheduler_service),
):
    existing = await svc.repo.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled job not found")
    await svc.unregister(job_id)
    await svc.repo.delete_job(job_id)
    return {"status": "success", "message": "Scheduled job deleted"}


# ------------------------------------------------------------------
# Run now / toggle
# ------------------------------------------------------------------


@router.post("/{job_id}/run-now")
async def run_scheduled_job_now(
    job_id: str,
    svc=Depends(_get_scheduler_service),
):
    """Fire a scheduled job immediately, ignoring its cron."""
    result = await svc.run_now(job_id)
    if result.get("status") == "failed" and result.get("error") == "Job not found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled job not found")
    return {"status": "success", "data": result}


@router.post("/{job_id}/toggle")
async def toggle_scheduled_job(
    job_id: str,
    svc=Depends(_get_scheduler_service),
):
    """Flip ``enabled`` and register/unregister with APScheduler."""
    existing = await svc.repo.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled job not found")

    new_enabled = not bool(existing.get("enabled"))
    job = await svc.repo.update_job(job_id, {"enabled": new_enabled})
    if new_enabled:
        job = await svc.register(job_id) or job
    else:
        await svc.unregister(job_id)
        job = await svc.repo.get_job(job_id) or job
    return {"status": "success", "data": job}
