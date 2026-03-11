"""
Abstract Scheduler Adapter

Defines the interface for background task scheduling. Implementations provide
Celery (enterprise) or APScheduler (desktop) backends.
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class SchedulerAdapter(ABC):
    """Abstract base class for task scheduling."""

    @abstractmethod
    async def start(self) -> None:
        """Start the scheduler and begin processing jobs."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the scheduler."""
        ...

    @abstractmethod
    async def schedule_task(
        self,
        task_fn: Callable,
        run_at,
        task_id: str,
        **kwargs: Any,
    ) -> str:
        """Schedule *task_fn* to run at *run_at*. Returns the task ID."""
        ...

    @abstractmethod
    async def schedule_immediate(
        self, task_fn: Callable, task_id: str, **kwargs: Any
    ) -> str:
        """Schedule *task_fn* to run immediately. Returns the task ID."""
        ...

    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a scheduled task. Returns ``True`` if the task was found and cancelled."""
        ...

    @abstractmethod
    async def list_scheduled(self) -> list:
        """Return a list of currently scheduled tasks."""
        ...

    @abstractmethod
    async def reschedule_task(self, task_id: str, new_run_at) -> bool:
        """Reschedule an existing task to *new_run_at*. Returns ``True`` on success."""
        ...

    @abstractmethod
    async def get_task_status(self, task_id: str) -> Optional[dict]:
        """Return status information for a task, or ``None`` if not found."""
        ...
