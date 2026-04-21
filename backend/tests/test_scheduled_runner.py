"""Tests for Phase 3 PR 3 — scheduled_runner."""

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
import pytest_asyncio

from services.scheduled_runner import CREW_TRIGGER_PREFIX, ScheduledRunner


# ---------------------------------------------------------------------------
# Fake APScheduler that records add_job / remove_job calls.
# ---------------------------------------------------------------------------

class FakeJob:
    def __init__(self, job_id: str, kwargs: Dict[str, Any]):
        self.id = job_id
        self.kwargs = kwargs
        self.next_run_time = None


class FakeScheduler:
    def __init__(self):
        self._jobs: Dict[str, FakeJob] = {}
        self.add_calls: List[Dict[str, Any]] = []

    def add_job(self, func, trigger=None, id=None, replace_existing=False, kwargs=None, name=None):
        if id in self._jobs and not replace_existing:
            raise RuntimeError(f"Duplicate id {id}")
        self._jobs[id] = FakeJob(id, kwargs or {})
        self.add_calls.append({"id": id, "trigger": trigger, "kwargs": kwargs or {}})
        return self._jobs[id]

    def remove_job(self, job_id: str):
        if job_id not in self._jobs:
            raise KeyError(job_id)
        self._jobs.pop(job_id)

    def get_jobs(self):
        return list(self._jobs.values())

    def get_job(self, job_id: str):
        return self._jobs.get(job_id)


class FakeAdapter:
    def __init__(self, scheduler: FakeScheduler):
        self._sched = scheduler

    def scheduler(self):
        return self._sched


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def runner(db_proxy):
    scheduler = FakeScheduler()
    r = ScheduledRunner(db_proxy, FakeAdapter(scheduler))
    r._fake_scheduler = scheduler  # expose for assertions
    return r


async def _insert_crew(db, crew_id: str, triggers: list, status: str = "active"):
    await db["crews"].insert_one({
        "_id": crew_id,
        "crew_id": crew_id,
        "user_id": "u1",
        "name": f"crew {crew_id}",
        "status": status,
        "triggers": triggers,
    })


# ---------------------------------------------------------------------------
# load_all
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_all_registers_cron_triggers(runner, db_proxy):
    await _insert_crew(db_proxy, "c1", [
        {"type": "scheduled", "connection_ids": ["linkedin"], "cron": "0 9 * * *"},
    ])
    await _insert_crew(db_proxy, "c2", [
        {"type": "scheduled", "connection_ids": ["blog"], "cron": "0 12 * * MON"},
        {"type": "reactive", "connection_id": "reddit", "keywords": ["x"]},  # ignored
    ])

    count = await runner.load_all()
    assert count == 2

    ids = sorted(runner._fake_scheduler._jobs.keys())
    assert ids == [f"{CREW_TRIGGER_PREFIX}c1:0", f"{CREW_TRIGGER_PREFIX}c2:0"]


@pytest.mark.asyncio
async def test_load_all_registers_date_trigger(runner, db_proxy):
    await _insert_crew(db_proxy, "c1", [
        {"type": "scheduled", "connection_ids": ["linkedin"], "run_at": "2026-12-01T09:00:00+00:00"},
    ])
    count = await runner.load_all()
    assert count == 1


@pytest.mark.asyncio
async def test_load_all_skips_inactive_crews(runner, db_proxy):
    await _insert_crew(db_proxy, "c-paused", [
        {"type": "scheduled", "cron": "0 9 * * *"},
    ], status="paused")
    count = await runner.load_all()
    assert count == 0


@pytest.mark.asyncio
async def test_load_all_survives_malformed_trigger(runner, db_proxy):
    # Neither cron nor run_at — should log+skip, not crash, and not count.
    await _insert_crew(db_proxy, "c-bad", [
        {"type": "scheduled", "connection_ids": ["linkedin"]},
    ])
    await _insert_crew(db_proxy, "c-good", [
        {"type": "scheduled", "cron": "0 9 * * *"},
    ])
    count = await runner.load_all()
    assert count == 1
    ids = list(runner._fake_scheduler._jobs.keys())
    assert ids == [f"{CREW_TRIGGER_PREFIX}c-good:0"]


# ---------------------------------------------------------------------------
# refresh_for_crew
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_for_crew_adds_and_removes(runner, db_proxy):
    await _insert_crew(db_proxy, "c1", [
        {"type": "scheduled", "cron": "0 9 * * *"},
        {"type": "scheduled", "cron": "0 18 * * *"},
    ])
    count = await runner.refresh_for_crew("c1")
    assert count == 2
    assert len(runner._fake_scheduler._jobs) == 2

    # Drop one trigger, refresh — old jobs gone, new set registered.
    await db_proxy["crews"].update_one(
        {"crew_id": "c1"},
        {"$set": {"triggers": [{"type": "scheduled", "cron": "0 12 * * *"}]}},
    )
    count = await runner.refresh_for_crew("c1")
    assert count == 1
    assert len(runner._fake_scheduler._jobs) == 1
    assert f"{CREW_TRIGGER_PREFIX}c1:0" in runner._fake_scheduler._jobs


@pytest.mark.asyncio
async def test_refresh_for_crew_handles_unknown(runner):
    count = await runner.refresh_for_crew("nonexistent")
    assert count == 0


@pytest.mark.asyncio
async def test_unregister_removes_all_crew_jobs(runner, db_proxy):
    await _insert_crew(db_proxy, "c1", [
        {"type": "scheduled", "cron": "0 9 * * *"},
        {"type": "scheduled", "cron": "0 18 * * *"},
    ])
    await runner.load_all()
    assert len(runner._fake_scheduler._jobs) == 2

    runner.unregister_for_crew("c1")
    assert runner._fake_scheduler._jobs == {}
