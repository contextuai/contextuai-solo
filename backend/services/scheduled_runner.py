"""
Phase 3 PR 3 — Scheduled Runner for crew triggers.

Reads `crew.triggers[type=scheduled]` across all active crews and registers
each one as an APScheduler job. When the trigger fires, dispatches the crew
via ``crew_service.start_run`` with ``trigger_type="scheduled"`` so the run
record carries its origin.

APScheduler job-id namespace: ``crew-trigger:<crew_id>:<trigger_index>``
(one crew can hold multiple scheduled triggers).

This runs alongside the legacy `SchedulerService` (which handles post / crew
jobs from the `scheduled_jobs` collection). They share the APScheduler
instance but use disjoint id namespaces, so neither interferes with the
other. PR 4 can retire the legacy scheduler once v1 soaks.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


CREW_TRIGGER_PREFIX = "crew-trigger:"


def _aps_id(crew_id: str, trigger_idx: int) -> str:
    return f"{CREW_TRIGGER_PREFIX}{crew_id}:{trigger_idx}"


class ScheduledRunner:
    """Registers crew scheduled triggers with APScheduler."""

    def __init__(self, db, apscheduler_adapter: Any) -> None:
        self.db = db
        self.adapter = apscheduler_adapter

    # ------------------------------------------------------------------
    # Scheduler lookup
    # ------------------------------------------------------------------

    def _scheduler(self):
        if hasattr(self.adapter, "scheduler"):
            return self.adapter.scheduler()
        return self.adapter._scheduler

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def load_all(self) -> int:
        """Scan every active crew at startup, register one APScheduler job per
        scheduled trigger. Returns total number of registered jobs.
        """
        registered = 0
        cursor = self.db["crews"].find({"status": "active"})
        async for crew in cursor:
            try:
                registered += self._register_triggers(crew)
            except Exception:
                logger.exception(
                    "Failed to register scheduled triggers for crew %s",
                    crew.get("crew_id"),
                )
        logger.info("ScheduledRunner: registered %d crew scheduled trigger(s)", registered)
        return registered

    async def refresh_for_crew(self, crew_id: str) -> int:
        """Re-register all triggers for a single crew.

        Called from CrewService after create/update/delete so changes pick
        up without a full reload.
        """
        # Remove any stale triggers first (we don't know how many there used
        # to be; scan by prefix).
        self._unregister_crew_jobs(crew_id)

        crew = await self.db["crews"].find_one({"crew_id": crew_id})
        if not crew:
            return 0
        if crew.get("status") != "active":
            return 0
        return self._register_triggers(crew)

    def unregister_for_crew(self, crew_id: str) -> None:
        """Drop all APScheduler jobs for a given crew."""
        self._unregister_crew_jobs(crew_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _register_triggers(self, crew: Dict[str, Any]) -> int:
        triggers: List[Dict[str, Any]] = crew.get("triggers") or []
        crew_id = crew.get("crew_id")
        if not crew_id:
            return 0
        registered = 0
        for idx, trigger in enumerate(triggers):
            if (trigger or {}).get("type") != "scheduled":
                continue
            try:
                self._register_one(crew_id, idx, trigger)
                registered += 1
            except Exception:
                logger.exception(
                    "Skipping malformed scheduled trigger idx=%d on crew %s",
                    idx,
                    crew_id,
                )
        return registered

    def _register_one(
        self,
        crew_id: str,
        trigger_idx: int,
        trigger: Dict[str, Any],
    ) -> None:
        cron = trigger.get("cron")
        run_at = trigger.get("run_at")

        aps_id = _aps_id(crew_id, trigger_idx)
        scheduler = self._scheduler()

        if cron:
            from apscheduler.triggers.cron import CronTrigger
            aps_trigger = CronTrigger.from_crontab(cron, timezone="UTC")
            source = cron
        elif run_at:
            from apscheduler.triggers.date import DateTrigger
            aps_trigger = DateTrigger(run_date=run_at)
            source = run_at
        else:
            raise ValueError("Scheduled trigger must have either cron or run_at")

        scheduler.add_job(
            self._fire,
            trigger=aps_trigger,
            id=aps_id,
            replace_existing=True,
            kwargs={
                "crew_id": crew_id,
                "trigger_idx": trigger_idx,
                "trigger_source": source,
                "content_brief": trigger.get("content_brief"),
            },
            name=f"crew:{crew_id} trigger:{trigger_idx}",
        )
        logger.info(
            "Registered scheduled trigger %s (cron=%s run_at=%s)",
            aps_id, cron, run_at,
        )

    def _unregister_crew_jobs(self, crew_id: str) -> None:
        scheduler = self._scheduler()
        prefix = f"{CREW_TRIGGER_PREFIX}{crew_id}:"
        try:
            jobs = scheduler.get_jobs()
        except Exception:
            return
        for job in jobs:
            if job.id and job.id.startswith(prefix):
                try:
                    scheduler.remove_job(job.id)
                except Exception:
                    pass

    async def _fire(
        self,
        crew_id: str,
        trigger_idx: int,
        trigger_source: str,
        content_brief: Optional[str],
    ) -> None:
        """Callback invoked by APScheduler when a cron/date boundary hits."""
        logger.info(
            "Scheduled trigger fired: crew=%s idx=%s source=%s",
            crew_id, trigger_idx, trigger_source,
        )
        try:
            from models.crew_models import RunCrewRequest
            from repositories.crew_repository import CrewRepository, CrewRunRepository
            from repositories.workspace_agent_repository import WorkspaceAgentRepository
            from services.crew_service import CrewService

            crew_repo = CrewRepository(self.db)
            run_repo = CrewRunRepository(self.db)
            agent_repo = WorkspaceAgentRepository(self.db)
            svc = CrewService(crew_repo=crew_repo, run_repo=run_repo, agent_repo=agent_repo)

            # Need the user_id from the crew document.
            crew = await self.db["crews"].find_one({"crew_id": crew_id})
            if not crew:
                logger.warning("Scheduled trigger fire: crew %s no longer exists", crew_id)
                return
            user_id = crew.get("user_id") or "desktop-user"

            request = RunCrewRequest(input=content_brief or f"Scheduled run at {datetime.utcnow().isoformat()}")
            await svc.start_run(
                crew_id=crew_id,
                user_id=user_id,
                request=request,
                trigger_type="scheduled",
                trigger_source=trigger_source,
            )
        except Exception:
            logger.exception("Scheduled trigger fire failed for crew %s", crew_id)
