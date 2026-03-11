"""
Scheduler Factory

Returns the APScheduler SchedulerAdapter for ContextuAI Solo.
Maintains a module-level singleton so only one scheduler instance exists.
"""

import logging
from typing import Optional

from adapters.scheduler_adapter import SchedulerAdapter
from adapters.apscheduler_adapter import APSchedulerAdapter

logger = logging.getLogger(__name__)

_scheduler: Optional[SchedulerAdapter] = None


async def get_scheduler_adapter() -> SchedulerAdapter:
    """Return the singleton APSchedulerAdapter instance."""
    global _scheduler

    if _scheduler is not None:
        return _scheduler

    logger.info("Initialising APScheduler adapter")

    adapter = APSchedulerAdapter()
    await adapter.start()
    _scheduler = adapter

    return _scheduler


async def stop_scheduler_adapter() -> None:
    """Stop and release the singleton scheduler (call during shutdown)."""
    global _scheduler
    if _scheduler is not None:
        await _scheduler.stop()
        _scheduler = None
