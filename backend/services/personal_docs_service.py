"""Orchestrate folder-source sync: walk → plan → friction-pause → execute.

Backed by the existing `RAGService` for actual embedding work; this module
owns the lifecycle of a sync job (status transitions, cancellation,
friction-modal pause, periodic progress patches).
"""
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from repositories.document_repository import DocumentRepository
from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from services.folder_walker import classify_diffs, walk_folder
from services.rag_service import RAGService

logger = logging.getLogger(__name__)


class PersonalDocsService:
    def __init__(
        self,
        src_repo: FolderSourceRepository,
        job_repo: IndexJobRepository,
        doc_repo: DocumentRepository,
        rag: RAGService,
        friction_threshold: int,
    ):
        self.src = src_repo
        self.jobs = job_repo
        self.docs = doc_repo
        self.rag = rag
        self.friction_threshold = friction_threshold
        # Track in-flight asyncio.Tasks per job_id so cancel() can act.
        self._tasks: Dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_sync(
        self, *, source: Dict[str, Any], kind: str
    ) -> Dict[str, Any]:
        """Start (or attach to) a sync job for `source`.

        Returns the existing running job if one is already in flight for
        this source — callers treat that as a "joined" response, not an
        error.
        """
        existing = await self.jobs.running_for_source(source["_id"])
        if existing:
            return existing
        job = await self.jobs.create_job(
            kb_id=source["kb_id"], source_id=source["_id"], kind=kind,
        )
        task = asyncio.create_task(self._run(source, job))
        self._tasks[job["_id"]] = task
        return job

    async def confirm(self, *, job_id: str) -> None:
        await self.jobs.patch(job_id, {"status": "running"})

    async def cancel(self, *, job_id: str) -> None:
        await self.jobs.request_cancel(job_id)

    async def delete_source(self, *, source: Dict[str, Any]) -> None:
        """Cancel any active job, drop all docs/chunks, drop the source row."""
        running = await self.jobs.running_for_source(source["_id"])
        if running:
            await self.jobs.request_cancel(running["_id"])
            # Give the running task a chance to observe the cancel flag
            for _ in range(20):
                refreshed = await self.jobs.get_job(running["_id"])
                if refreshed and refreshed["status"] in (
                    "cancelled", "done", "error",
                ):
                    break
                await asyncio.sleep(0.1)
        await self.rag.delete_for_source(source["kb_id"], source["_id"])
        await self.src.delete_source(source["_id"])

    # ------------------------------------------------------------------
    # Internal lifecycle
    # ------------------------------------------------------------------

    async def _run(self, source: Dict[str, Any], job: Dict[str, Any]) -> None:
        job_id = job["_id"]
        try:
            await self.jobs.patch(job_id, {
                "status": "walking",
                "started_at": datetime.utcnow().isoformat(),
            })
            candidates, capped = await asyncio.to_thread(
                walk_folder,
                source["path"],
                include_globs=source["include_globs"],
                exclude_globs=source["exclude_globs"],
                max_file_bytes=source["max_file_bytes"],
                max_files=source["max_files"],
                max_depth=source["max_depth"],
            )
            if capped:
                await self._finish(
                    job_id,
                    status="error",
                    error="cap_reached",
                    files_total=len(candidates),
                )
                await self.src.update_source(source["_id"], {
                    "status": "error", "error": "cap_reached",
                })
                return

            existing_by_path = await self.docs.list_paths_for_source(source["_id"])
            plan = classify_diffs(candidates, existing_by_path)
            total_work = len(plan.new) + len(plan.updated)
            await self.jobs.patch(job_id, {
                "files_total": len(candidates),
                "files_skipped": plan.unchanged_count,
                "bytes_total": sum(c.size for c in (plan.new + plan.updated)),
            })

            # Friction modal: only on full_sync above threshold
            if (
                job["kind"] == "full_sync"
                and total_work > self.friction_threshold
            ):
                await self.jobs.patch(job_id, {"status": "awaiting_confirmation"})
                if not await self._wait_for_confirm(job_id):
                    return  # cancelled while paused

            if total_work == 0 and not plan.removed_doc_ids:
                await self._stamp_source(source, job_id, candidates)
                await self._finish(job_id, status="done")
                return

            await self.jobs.patch(job_id, {"status": "running"})

            files_added = 0
            files_updated = 0
            files_removed = 0
            bytes_done = 0

            for c in plan.new:
                if await self._cancel_check(job_id):
                    await self._finish(job_id, status="cancelled")
                    return
                try:
                    await self.rag.ingest_from_path(
                        kb_id=source["kb_id"],
                        source_id=source["_id"],
                        abs_path=c.abs_path,
                        label_of_source=source["label"],
                    )
                    files_added += 1
                    bytes_done += c.size
                except Exception:
                    logger.exception("ingest failed for %s", c.abs_path)
                await self.jobs.patch(job_id, {
                    "files_done": files_added + files_updated,
                    "files_added": files_added,
                    "files_updated": files_updated,
                    "bytes_done": bytes_done,
                })

            for c in plan.updated:
                if await self._cancel_check(job_id):
                    await self._finish(job_id, status="cancelled")
                    return
                prev = existing_by_path[c.abs_path]
                try:
                    await self.rag.ingest_from_path(
                        kb_id=source["kb_id"],
                        source_id=source["_id"],
                        abs_path=c.abs_path,
                        label_of_source=source["label"],
                        existing_doc_id=prev["_id"],
                    )
                    files_updated += 1
                    bytes_done += c.size
                except Exception:
                    logger.exception("re-ingest failed for %s", c.abs_path)
                await self.jobs.patch(job_id, {
                    "files_done": files_added + files_updated,
                    "files_added": files_added,
                    "files_updated": files_updated,
                    "bytes_done": bytes_done,
                })

            for doc_id in plan.removed_doc_ids:
                await self.rag.chunk_repo.delete_for_document(doc_id)
                await self.docs.delete(doc_id)
                files_removed += 1
                await self.jobs.patch(job_id, {"files_removed": files_removed})

            await self.rag._refresh_kb_counts(source["kb_id"])
            await self._stamp_source(source, job_id, candidates)
            await self._finish(job_id, status="done")
        except asyncio.CancelledError:
            await self._finish(job_id, status="cancelled")
            raise
        except Exception as e:
            logger.exception("personal-docs sync failed for source %s",
                             source.get("_id"))
            await self._finish(job_id, status="error", error=str(e))
        finally:
            self._tasks.pop(job_id, None)

    async def _wait_for_confirm(self, job_id: str) -> bool:
        """Block until the friction-modal job is confirmed or cancelled."""
        while True:
            j = await self.jobs.get_job(job_id)
            if j is None:
                return False
            if j.get("cancel_requested"):
                await self._finish(job_id, status="cancelled")
                return False
            if j["status"] == "running":
                return True
            await asyncio.sleep(0.2)

    async def _cancel_check(self, job_id: str) -> bool:
        j = await self.jobs.get_job(job_id)
        return bool(j and j.get("cancel_requested"))

    async def _finish(
        self, job_id: str, *, status: str, error: Optional[str] = None, **extra,
    ) -> None:
        update: Dict[str, Any] = {
            "status": status,
            "finished_at": datetime.utcnow().isoformat(),
        }
        if error is not None:
            update["error"] = error
        update.update(extra)
        await self.jobs.patch(job_id, update)

    async def _stamp_source(self, source, job_id, candidates) -> None:
        await self.src.update_source(source["_id"], {
            "last_sync_at": datetime.utcnow().isoformat(),
            "last_sync_job_id": job_id,
            "file_count": len(candidates),
            "byte_count": sum(c.size for c in candidates),
            "error": None,
        })
