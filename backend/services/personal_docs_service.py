"""Orchestrate folder-source sync: walk → plan → friction-pause → execute.

Backed by the existing `RAGService` for actual embedding work; this module
owns the lifecycle of a sync job (status transitions, cancellation,
friction-modal pause, periodic progress patches).
"""
import asyncio
import logging
import os
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

    async def check_folder_staleness(self, mapping_id: str) -> Dict[str, Any]:
        """SPEC-11: Check whether a folder mapping has changed files since last sync.

        Compares current filesystem candidates (size + mtime) against indexed
        documents and the last index job/source sync timestamp.
        """
        source = (
            mapping_id
            if isinstance(mapping_id, dict)
            else await self.src.get_source(mapping_id)
        )
        if not source:
            raise ValueError(f"Folder source not found: {mapping_id}")

        source_id = source["_id"]
        folder_path = source.get("path", "")
        if not folder_path or not os.path.isdir(folder_path):
            return {
                "source_id": source_id,
                "is_stale": True,
                "changed_files_count": 0,
                "new_files": 0,
                "updated_files": 0,
                "removed_files": 0,
                "last_sync_at": source.get("last_sync_at"),
                "error": "folder_missing",
            }

        candidates, _capped = await asyncio.to_thread(
            walk_folder,
            folder_path,
            include_globs=source.get("include_globs") or [],
            exclude_globs=source.get("exclude_globs") or [],
            max_file_bytes=int(source.get("max_file_bytes") or 10 * 1024 * 1024),
            max_files=int(source.get("max_files") or 5000),
            max_depth=int(source.get("max_depth") or 8),
        )

        existing_by_path = await self.docs.list_paths_for_source(source_id)
        if existing_by_path:
            plan = classify_diffs(candidates, existing_by_path)
            changed_count = (
                len(plan.new) + len(plan.updated) + len(plan.removed_doc_ids)
            )
            return {
                "source_id": source_id,
                "is_stale": changed_count > 0,
                "changed_files_count": changed_count,
                "new_files": len(plan.new),
                "updated_files": len(plan.updated),
                "removed_files": len(plan.removed_doc_ids),
                "last_sync_at": source.get("last_sync_at"),
            }

        # Fallback: compare file mtimes against last_sync_at (or last job finished_at)
        last_sync_str = source.get("last_sync_at")
        if not last_sync_str and self.jobs is not None:
            recent_jobs = await self.jobs.list_for_source(source_id)
            for j in recent_jobs or []:
                if j.get("status") == "done" and j.get("finished_at"):
                    last_sync_str = j["finished_at"]
                    break

        if not last_sync_str:
            changed_count = len(candidates)
            return {
                "source_id": source_id,
                "is_stale": changed_count > 0,
                "changed_files_count": changed_count,
                "new_files": changed_count,
                "updated_files": 0,
                "removed_files": 0,
                "last_sync_at": None,
            }

        try:
            last_sync_ts = datetime.fromisoformat(
                last_sync_str.replace("Z", "+00:00")
            ).timestamp()
        except Exception:
            last_sync_ts = 0.0

        newer_files = [c for c in candidates if float(c.mtime) > last_sync_ts]
        prev_file_count = int(source.get("file_count") or 0)
        removed_est = max(0, prev_file_count - len(candidates))
        changed_count = len(newer_files) + removed_est
        return {
            "source_id": source_id,
            "is_stale": changed_count > 0,
            "changed_files_count": changed_count,
            "new_files": max(0, len(candidates) - prev_file_count),
            "updated_files": len(newer_files),
            "removed_files": removed_est,
            "last_sync_at": last_sync_str,
        }

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
            files_failed = 0
            bytes_done = 0
            first_error: Optional[str] = None

            def _record_failure(path: str, exc: Exception) -> None:
                nonlocal files_failed, first_error
                files_failed += 1
                if first_error is None:
                    first_error = f"{os.path.basename(path)}: {exc}"

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
                except Exception as exc:
                    logger.exception("ingest failed for %s", c.abs_path)
                    _record_failure(c.abs_path, exc)
                await self.jobs.patch(job_id, {
                    "files_done": files_added + files_updated,
                    "files_added": files_added,
                    "files_updated": files_updated,
                    "files_failed": files_failed,
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
                except Exception as exc:
                    logger.exception("re-ingest failed for %s", c.abs_path)
                    _record_failure(c.abs_path, exc)
                await self.jobs.patch(job_id, {
                    "files_done": files_added + files_updated,
                    "files_added": files_added,
                    "files_updated": files_updated,
                    "files_failed": files_failed,
                    "bytes_done": bytes_done,
                })

            for doc_id in plan.removed_doc_ids:
                await self.rag.chunk_repo.delete_for_document(doc_id)
                await self.docs.delete(doc_id)
                files_removed += 1
                await self.jobs.patch(job_id, {"files_removed": files_removed})

            await self.rag._refresh_kb_counts(source["kb_id"])
            await self._stamp_source(source, job_id, candidates, error=first_error)

            # If every file we tried to ingest failed, the sync did not do
            # what the user asked — surface it as an error rather than a
            # silent "done, 0 docs". A partial failure stays "done" but
            # still carries the first error so the UI can warn.
            if files_failed and (files_added + files_updated) == 0:
                await self._finish(
                    job_id, status="error", error=first_error,
                    files_failed=files_failed,
                )
            else:
                await self._finish(
                    job_id, status="done", error=first_error,
                    files_failed=files_failed,
                )
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

    async def _stamp_source(
        self, source, job_id, candidates, error: Optional[str] = None,
    ) -> None:
        await self.src.update_source(source["_id"], {
            "last_sync_at": datetime.utcnow().isoformat(),
            "last_sync_job_id": job_id,
            "file_count": len(candidates),
            "byte_count": sum(c.size for c in candidates),
            "error": error,
        })
