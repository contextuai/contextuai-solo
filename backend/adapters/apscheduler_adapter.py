"""
APScheduler Adapter

Provides in-process task scheduling for desktop mode using APScheduler with
a SQLite job store.  Jobs persist across application restarts.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from adapters.scheduler_adapter import SchedulerAdapter

logger = logging.getLogger(__name__)

_DEFAULT_DB_DIR = os.path.expanduser("~/.contextuai-solo/data")
_DEFAULT_JOB_DB = os.path.join(_DEFAULT_DB_DIR, "scheduler.db")


class APSchedulerAdapter(SchedulerAdapter):
    """SchedulerAdapter backed by APScheduler with SQLite persistence.

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database used for the APScheduler job store.
        Defaults to ``~/.contextuai-solo/data/scheduler.db``.
    """

    def __init__(self, db_path: str = _DEFAULT_JOB_DB) -> None:
        self.db_path = db_path
        self._scheduler = None
        self._task_statuses: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise and start the APScheduler ``BackgroundScheduler``."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

            jobstores = {
                "default": SQLAlchemyJobStore(url=f"sqlite:///{self.db_path}")
            }
            self._scheduler = AsyncIOScheduler(
                jobstores=jobstores,
                job_defaults={
                    "coalesce": True,
                    "max_instances": 3,
                    "misfire_grace_time": 60,
                },
            )
            self._scheduler.start()
            logger.info(
                "APSchedulerAdapter started (job store: %s)", self.db_path
            )
        except ImportError:
            raise RuntimeError(
                "APScheduler is required for desktop mode. "
                "Install it with: pip install apscheduler sqlalchemy"
            )

    async def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if self._scheduler:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None
            logger.info("APSchedulerAdapter stopped")

    # ------------------------------------------------------------------
    # Task scheduling
    # ------------------------------------------------------------------

    async def schedule_task(
        self,
        task_fn: Callable,
        run_at,
        task_id: str,
        **kwargs: Any,
    ) -> str:
        """Schedule *task_fn* to run once at *run_at*."""
        self._require_running()

        if isinstance(run_at, (int, float)):
            run_at = datetime.fromtimestamp(run_at, tz=timezone.utc)

        # Wrap sync callables to run in the event loop
        wrapped = self._wrap_callable(task_fn, task_id, **kwargs)

        self._scheduler.add_job(
            wrapped,
            trigger="date",
            run_date=run_at,
            id=task_id,
            replace_existing=True,
        )
        self._task_statuses[task_id] = {
            "task_id": task_id,
            "status": "scheduled",
            "scheduled_for": run_at.isoformat() if hasattr(run_at, "isoformat") else str(run_at),
        }
        logger.info("Scheduled task %s for %s", task_id, run_at)
        return task_id

    async def schedule_immediate(
        self, task_fn: Callable, task_id: str, **kwargs: Any
    ) -> str:
        """Schedule *task_fn* to run immediately."""
        self._require_running()

        wrapped = self._wrap_callable(task_fn, task_id, **kwargs)

        self._scheduler.add_job(
            wrapped,
            trigger="date",
            id=task_id,
            replace_existing=True,
        )
        self._task_statuses[task_id] = {
            "task_id": task_id,
            "status": "pending",
        }
        logger.info("Dispatched immediate task %s", task_id)
        return task_id

    async def cancel_task(self, task_id: str) -> bool:
        """Remove a scheduled job."""
        self._require_running()
        try:
            self._scheduler.remove_job(task_id)
            self._task_statuses[task_id] = {
                "task_id": task_id,
                "status": "cancelled",
            }
            logger.info("Cancelled task %s", task_id)
            return True
        except Exception:
            logger.warning("Task %s not found for cancellation", task_id)
            return False

    async def list_scheduled(self) -> list:
        """Return all currently scheduled jobs."""
        self._require_running()
        jobs = self._scheduler.get_jobs()
        return [
            {
                "task_id": job.id,
                "task_name": job.name,
                "next_run_time": (
                    job.next_run_time.isoformat() if job.next_run_time else None
                ),
            }
            for job in jobs
        ]

    async def reschedule_task(self, task_id: str, new_run_at) -> bool:
        """Reschedule an existing job to a new time."""
        self._require_running()

        if isinstance(new_run_at, (int, float)):
            new_run_at = datetime.fromtimestamp(new_run_at, tz=timezone.utc)

        try:
            self._scheduler.reschedule_job(
                task_id, trigger="date", run_date=new_run_at
            )
            self._task_statuses[task_id] = {
                "task_id": task_id,
                "status": "rescheduled",
                "scheduled_for": new_run_at.isoformat(),
            }
            logger.info("Rescheduled task %s to %s", task_id, new_run_at)
            return True
        except Exception:
            logger.warning("Task %s not found for rescheduling", task_id)
            return False

    async def get_task_status(self, task_id: str) -> Optional[dict]:
        """Return tracked status for a task."""
        return self._task_statuses.get(task_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_running(self) -> None:
        if self._scheduler is None:
            raise RuntimeError("APSchedulerAdapter is not started. Call start() first.")

    def _wrap_callable(
        self, task_fn: Callable, task_id: str, **kwargs: Any
    ) -> Callable:
        """Wrap *task_fn* so it updates ``_task_statuses`` on completion."""
        statuses = self._task_statuses

        def wrapper():
            statuses[task_id] = {"task_id": task_id, "status": "running"}
            try:
                result = task_fn(**kwargs)
                # If the callable is a coroutine, run it
                if asyncio.iscoroutine(result):
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(result)
                    else:
                        loop.run_until_complete(result)
                statuses[task_id] = {
                    "task_id": task_id,
                    "status": "completed",
                }
            except Exception as exc:
                logger.error("Task %s failed: %s", task_id, exc)
                statuses[task_id] = {
                    "task_id": task_id,
                    "status": "failed",
                    "error": str(exc),
                }

        return wrapper
