"""Periodic scheduler for Personal Docs folder mappings.

Tick every N seconds, find folder sources whose schedule has elapsed,
and enqueue an incremental sync. Mirrors the shape of `RedditPoller`.
"""
import asyncio
import logging
from typing import Optional

import settings
from repositories.chunk_repository import ChunkRepository
from repositories.document_repository import DocumentRepository
from repositories.folder_source_repository import FolderSourceRepository
from repositories.index_job_repository import IndexJobRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from services.personal_docs_service import PersonalDocsService
from services.rag_service import RAGService

logger = logging.getLogger(__name__)


class PersonalDocsScheduler:
    def __init__(self, db):
        self.db = db
        self._task: Optional[asyncio.Task] = None
        self._stopping = False
        self._tick = settings.PERSONAL_DOCS_SCHEDULER_TICK_SECONDS

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run())
        logger.info(
            "PersonalDocsScheduler started (tick=%ss)", self._tick
        )

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("PersonalDocsScheduler stopped")

    async def _run(self) -> None:
        src_repo = FolderSourceRepository(self.db)
        job_repo = IndexJobRepository(self.db)
        doc_repo = DocumentRepository(self.db)
        chunk_repo = ChunkRepository(self.db)
        kb_repo = KnowledgeBaseRepository(self.db)
        rag = RAGService(kb_repo, doc_repo, chunk_repo)
        svc = PersonalDocsService(
            src_repo, job_repo, doc_repo, rag,
            friction_threshold=settings.PERSONAL_DOCS_FRICTION_THRESHOLD,
        )

        while not self._stopping:
            try:
                due = await src_repo.list_due_for_sync()
                for src in due:
                    running = await job_repo.running_for_source(src["_id"])
                    if running:
                        continue
                    await svc.start_sync(source=src, kind="incremental")
            except Exception:
                logger.exception("PersonalDocsScheduler tick failed")
            try:
                await asyncio.sleep(self._tick)
            except asyncio.CancelledError:
                break
