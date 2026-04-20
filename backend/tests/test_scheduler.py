"""
Tests for the Post/Crew Scheduler feature.

Covers:
- ScheduledJobRepository CRUD
- SchedulerService register / unregister / run-now (mocked APScheduler)
- /api/v1/scheduled-jobs validate-cron endpoint
- Creating a post job via the HTTP API
- Deleting a job removes it from the scheduler
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Repository ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestScheduledJobRepository:
    async def test_create_and_get(self, db_proxy):
        from repositories.scheduled_job_repository import ScheduledJobRepository

        repo = ScheduledJobRepository(db_proxy)
        job = await repo.create_job({
            "name": "Daily LinkedIn post",
            "job_type": "post",
            "cron": "0 9 * * *",
            "timezone": "UTC",
            "channel_id": "chan-abc",
            "content": "Hello world",
        })

        assert job["name"] == "Daily LinkedIn post"
        assert job["job_type"] == "post"
        assert job["enabled"] is True
        assert job["run_count"] == 0
        assert job["id"]

        fetched = await repo.get_job(job["id"])
        assert fetched is not None
        assert fetched["channel_id"] == "chan-abc"

    async def test_update_and_delete(self, db_proxy):
        from repositories.scheduled_job_repository import ScheduledJobRepository

        repo = ScheduledJobRepository(db_proxy)
        job = await repo.create_job({
            "name": "Crew run",
            "job_type": "crew",
            "cron": "0 8 * * *",
            "crew_id": "crew-1",
        })
        jid = job["id"]

        updated = await repo.update_job(jid, {"enabled": False})
        assert updated["enabled"] is False

        deleted = await repo.delete_job(jid)
        assert deleted is True
        assert await repo.get_job(jid) is None


# ── SchedulerService ──────────────────────────────────────────────────


def _mock_adapter():
    """Return an APSchedulerAdapter-shaped mock with an AsyncIOScheduler stub."""
    scheduler = MagicMock()
    scheduler.add_job = MagicMock()
    scheduler.remove_job = MagicMock()
    scheduler.get_job = MagicMock(return_value=None)

    adapter = MagicMock()
    adapter.scheduler.return_value = scheduler
    adapter._scheduler = scheduler
    return adapter, scheduler


@pytest.mark.asyncio
class TestSchedulerService:
    async def test_register_adds_job_to_apscheduler(self, db_proxy):
        from services.scheduler_service import SchedulerService, _aps_job_id

        adapter, aps = _mock_adapter()
        svc = SchedulerService(db_proxy, adapter)

        created = await svc.repo.create_job({
            "name": "Daily post",
            "job_type": "post",
            "cron": "0 9 * * *",
            "channel_id": "c-1",
            "content": "hi",
        })

        await svc.register(created["id"])
        assert aps.add_job.called
        kwargs = aps.add_job.call_args.kwargs
        assert kwargs["id"] == _aps_job_id(created["id"])
        assert kwargs["replace_existing"] is True
        assert kwargs["kwargs"]["job_id"] == created["id"]

    async def test_unregister_removes_job(self, db_proxy):
        from services.scheduler_service import SchedulerService, _aps_job_id

        adapter, aps = _mock_adapter()
        svc = SchedulerService(db_proxy, adapter)

        created = await svc.repo.create_job({
            "name": "Disable me",
            "job_type": "post",
            "cron": "0 * * * *",
            "channel_id": "c-1",
            "content": "hi",
        })

        await svc.unregister(created["id"])
        aps.remove_job.assert_called_once_with(_aps_job_id(created["id"]))

    async def test_run_now_post_path(self, db_proxy, monkeypatch):
        """run_now should dispatch to DistributionService.publish."""
        from services.scheduler_service import SchedulerService
        import services.scheduler_service as mod

        adapter, _ = _mock_adapter()
        svc = SchedulerService(db_proxy, adapter)

        created = await svc.repo.create_job({
            "name": "Run now test",
            "job_type": "post",
            "cron": "0 9 * * *",
            "channel_id": "c-1",
            "content": "hi",
        })

        # Patch DistributionService inside services.distribution_service
        fake_dist = MagicMock()
        fake_dist.get_channel = AsyncMock(return_value={"channel_id": "c-1", "enabled": True})
        fake_dist.publish = AsyncMock(return_value={"status": "published", "delivery_id": "d-1"})

        import services.distribution_service as dist_mod
        monkeypatch.setattr(
            dist_mod, "DistributionService", lambda db: fake_dist
        )

        result = await svc.run_now(created["id"])
        assert result["status"] == "success"
        fake_dist.publish.assert_awaited_once()

        refreshed = await svc.repo.get_job(created["id"])
        assert refreshed["last_run_status"] == "success"
        assert refreshed["run_count"] == 1


# ── HTTP API ──────────────────────────────────────────────────────────


class TestScheduledJobsAPI:
    def _install_scheduler_service(self, test_app, db_proxy):
        """Attach a SchedulerService + ensure the router is registered.

        The production wiring lives in ``app.py`` startup (added post-hoc).
        For tests we idempotently include the router so the HTTP paths are
        exercised without relying on the startup snippet being applied.
        """
        from services.scheduler_service import SchedulerService
        from routers.scheduled_jobs import router as scheduled_jobs_router

        adapter, _ = _mock_adapter()
        svc = SchedulerService(db_proxy, adapter)
        test_app.app.state.scheduler_service = svc

        # Register the router once (idempotent — skip if already present).
        routes = [getattr(r, "path", None) for r in test_app.app.routes]
        if not any(p and p.startswith("/api/v1/scheduled-jobs") for p in routes):
            test_app.app.include_router(scheduled_jobs_router)
        return svc

    def _ensure_router(self, test_app):
        from routers.scheduled_jobs import router as scheduled_jobs_router
        routes = [getattr(r, "path", None) for r in test_app.app.routes]
        if not any(p and p.startswith("/api/v1/scheduled-jobs") for p in routes):
            test_app.app.include_router(scheduled_jobs_router)

    def test_validate_cron_valid(self, test_app):
        self._ensure_router(test_app)
        resp = test_app.get("/api/v1/scheduled-jobs/validate-cron?expr=0+9+*+*+*&count=3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert len(body["next_runs"]) == 3

    def test_validate_cron_invalid(self, test_app):
        self._ensure_router(test_app)
        resp = test_app.get("/api/v1/scheduled-jobs/validate-cron?expr=not-a-cron")
        assert resp.status_code == 400

    def test_create_post_job_persists(self, test_app, db_proxy):
        self._install_scheduler_service(test_app, db_proxy)

        resp = test_app.post("/api/v1/scheduled-jobs/", json={
            "name": "Morning LinkedIn",
            "job_type": "post",
            "cron": "0 9 * * *",
            "channel_id": "chan-1",
            "content": "Hello LinkedIn!",
            "enabled": True,
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["name"] == "Morning LinkedIn"
        assert data["job_type"] == "post"
        assert data["id"]

    def test_delete_job_unregisters(self, test_app, db_proxy):
        svc = self._install_scheduler_service(test_app, db_proxy)

        resp = test_app.post("/api/v1/scheduled-jobs/", json={
            "name": "To delete",
            "job_type": "post",
            "cron": "0 9 * * *",
            "channel_id": "chan-x",
            "content": "bye",
        })
        job_id = resp.json()["data"]["id"]

        aps = svc._scheduler()
        aps.remove_job.reset_mock()

        del_resp = test_app.delete(f"/api/v1/scheduled-jobs/{job_id}")
        assert del_resp.status_code == 200
        # remove_job was invoked as part of unregister
        assert aps.remove_job.called

        missing = test_app.get(f"/api/v1/scheduled-jobs/{job_id}")
        assert missing.status_code == 404
