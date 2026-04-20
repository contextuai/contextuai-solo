"""
Scheduler Service — orchestrates cron-based post + crew recurring jobs.

Manages the lifecycle of ``ScheduledJob`` documents in tandem with
APScheduler. Each enabled scheduled job becomes an APScheduler job with a
``CronTrigger``; when the trigger fires the wrapper in this service
fetches the latest job doc, executes the corresponding action (publish
to a distribution channel, or trigger a crew run), and records the
outcome back onto the doc.

The service is defensive: exceptions inside job callables are caught,
logged, and persisted on ``last_run_error`` so the scheduler never
crashes because of a misbehaving channel or crew.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.scheduled_job_repository import ScheduledJobRepository

logger = logging.getLogger(__name__)


_JOB_ID_PREFIX = "scheduled-job:"


def _aps_job_id(job_id: str) -> str:
    """Return the APScheduler job id corresponding to a ScheduledJob."""
    return f"{_JOB_ID_PREFIX}{job_id}"


class SchedulerService:
    """Business-logic layer on top of APScheduler for scheduled jobs."""

    def __init__(self, db: AsyncIOMotorDatabase, apscheduler_adapter: Any) -> None:
        self.db = db
        self.adapter = apscheduler_adapter
        self.repo = ScheduledJobRepository(db)

    # ------------------------------------------------------------------
    # Scheduler lookup
    # ------------------------------------------------------------------

    def _scheduler(self):
        """Return the underlying AsyncIOScheduler instance."""
        if hasattr(self.adapter, "scheduler"):
            return self.adapter.scheduler()
        return self.adapter._scheduler  # fallback for compatibility

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def load_all(self) -> int:
        """Rehydrate APScheduler with every enabled scheduled job.

        Called once at application startup after the APScheduler adapter
        has been started. Returns the number of jobs registered.
        """
        jobs = await self.repo.list_enabled()
        registered = 0
        for job in jobs:
            try:
                self._register_with_scheduler(job)
                registered += 1
            except Exception:
                logger.exception(
                    "Failed to register scheduled job %s on startup",
                    job.get("id"),
                )
        logger.info(
            "SchedulerService: registered %d/%d enabled jobs on startup",
            registered,
            len(jobs),
        )
        return registered

    # ------------------------------------------------------------------
    # CRUD helpers (register/unregister with APScheduler)
    # ------------------------------------------------------------------

    async def register(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a job and (re)register it with APScheduler.

        If the job does not exist or is disabled, any existing APScheduler
        job is removed instead.
        """
        job = await self.repo.get_job(job_id)
        if not job or not job.get("enabled"):
            await self.unregister(job_id)
            return job
        self._register_with_scheduler(job)
        # Persist the next fire time for UI display.
        next_run = self._get_next_run_time(job_id)
        if next_run is not None:
            await self.repo.set_next_run_at(job_id, next_run)
        return await self.repo.get_job(job_id)

    async def unregister(self, job_id: str) -> None:
        """Remove a job from APScheduler (no-op if absent)."""
        aps_id = _aps_job_id(job_id)
        scheduler = self._scheduler()
        try:
            scheduler.remove_job(aps_id)
        except Exception:
            # Job not present — safe to ignore.
            pass
        await self.repo.set_next_run_at(job_id, None)

    async def run_now(self, job_id: str) -> Dict[str, Any]:
        """Execute a job immediately, bypassing its cron schedule."""
        job = await self.repo.get_job(job_id)
        if not job:
            return {
                "job_id": job_id,
                "status": "failed",
                "error": "Job not found",
                "ran_at": datetime.utcnow().isoformat(),
            }
        return await self._execute(job)

    # ------------------------------------------------------------------
    # APScheduler wiring
    # ------------------------------------------------------------------

    def _register_with_scheduler(self, job: Dict[str, Any]) -> None:
        """Add or replace the APScheduler job for the given ScheduledJob."""
        from apscheduler.triggers.cron import CronTrigger

        aps_id = _aps_job_id(job["id"])
        trigger = CronTrigger.from_crontab(
            job["cron"], timezone=job.get("timezone") or "UTC"
        )
        scheduler = self._scheduler()
        scheduler.add_job(
            self._fire,
            trigger=trigger,
            id=aps_id,
            replace_existing=True,
            kwargs={"job_id": job["id"]},
            name=job.get("name", aps_id),
        )
        logger.info(
            "Registered scheduled job %s (%s) cron=%s tz=%s",
            job["id"],
            job.get("name"),
            job["cron"],
            job.get("timezone", "UTC"),
        )

    def _get_next_run_time(self, job_id: str) -> Optional[str]:
        """Return the next fire time for a registered APScheduler job."""
        try:
            scheduler = self._scheduler()
            aps_job = scheduler.get_job(_aps_job_id(job_id))
            if aps_job and aps_job.next_run_time:
                return aps_job.next_run_time.isoformat()
        except Exception:
            logger.debug("next-run-time lookup failed for %s", job_id, exc_info=True)
        return None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _fire(self, job_id: str) -> None:
        """APScheduler callback: load job + execute + persist result."""
        job = await self.repo.get_job(job_id)
        if not job:
            logger.warning("Scheduled job %s no longer exists — skipping fire", job_id)
            return
        if not job.get("enabled"):
            logger.info("Scheduled job %s is disabled — skipping fire", job_id)
            return
        await self._execute(job)

    async def _execute(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Run the job's action and persist the outcome."""
        job_id = job["id"]
        job_type = job.get("job_type")
        ran_at = datetime.utcnow().isoformat()
        status = "failed"
        error: Optional[str] = None
        details: Optional[Dict[str, Any]] = None

        try:
            if job_type == "post":
                details = await self._run_post(job)
            elif job_type == "crew":
                details = await self._run_crew(job)
            else:
                raise ValueError(f"Unknown job_type: {job_type!r}")

            if details and details.get("ok"):
                status = "success"
            else:
                status = "failed"
                error = (details or {}).get("error") or "Unknown error"
        except Exception as exc:
            logger.exception("Scheduled job %s execution failed", job_id)
            status = "failed"
            error = str(exc)
            details = {"ok": False, "error": str(exc)}

        next_run = self._get_next_run_time(job_id)
        await self.repo.record_run(
            job_id, status=status, error=error, next_run_at=next_run
        )

        return {
            "job_id": job_id,
            "job_type": job_type,
            "status": status,
            "ran_at": ran_at,
            "error": error,
            "details": details,
        }

    # ------------------------------------------------------------------
    # Job-type handlers
    # ------------------------------------------------------------------

    async def _run_post(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Publish ``job.content`` to ``job.channel_id`` via DistributionService."""
        channel_id = job.get("channel_id")
        content = job.get("content")
        if not channel_id:
            return {"ok": False, "error": "Missing channel_id"}
        if not content:
            return {"ok": False, "error": "Missing content"}

        from services.distribution_service import DistributionService

        svc = DistributionService(self.db)
        channel = await svc.get_channel(channel_id)
        if not channel:
            return {"ok": False, "error": f"Channel {channel_id} not found"}
        if not channel.get("enabled"):
            return {"ok": False, "error": f"Channel {channel_id} is disabled"}

        delivery = await svc.publish(
            channel_id=channel_id,
            content=content,
            title=job.get("title"),
            metadata=job.get("metadata"),
            published_by="scheduler",
        )

        # DistributionService returns either an error envelope or a delivery
        # record with status="published" / "failed".
        if delivery.get("status") == "published":
            return {"ok": True, "delivery": delivery}
        return {
            "ok": False,
            "error": delivery.get("message") or str(delivery.get("result", {}).get("error", "publish failed")),
            "delivery": delivery,
        }

    async def _run_crew(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger a crew run via CrewService.start_run."""
        crew_id = job.get("crew_id")
        if not crew_id:
            return {"ok": False, "error": "Missing crew_id"}

        try:
            from models.crew_models import RunCrewRequest
            from repositories.crew_repository import CrewRepository, CrewRunRepository
            from repositories.workspace_agent_repository import WorkspaceAgentRepository
            from services.crew_service import CrewService

            crew_repo = CrewRepository(self.db)
            run_repo = CrewRunRepository(self.db)
            agent_repo = WorkspaceAgentRepository(self.db)
            svc = CrewService(crew_repo, run_repo, agent_repo)

            crew = await svc.get_crew(crew_id, "desktop-user")
            if not crew:
                return {"ok": False, "error": f"Crew {crew_id} not found"}

            crew_input = job.get("crew_input") or {}
            request = RunCrewRequest(
                input=crew_input.get("input"),
                input_data=crew_input or None,
            )
            run = await svc.start_run(crew_id, "desktop-user", request)
            return {
                "ok": True,
                "run_id": run.get("run_id"),
                "crew_id": crew_id,
            }
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except ImportError:
            # Crew subsystem missing — leave the post path fully working.
            logger.warning("Crew run integration TODO: imports failed")
            return {"ok": False, "error": "Crew integration unavailable"}

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def list_jobs(
        self, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List persisted jobs and decorate each with ``next_run_at``."""
        jobs = await self.repo.list_jobs(skip=skip, limit=limit)
        for job in jobs:
            next_run = self._get_next_run_time(job["id"])
            if next_run is not None:
                job["next_run_at"] = next_run
        return jobs
