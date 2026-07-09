"""Memory service — CRUD, semantic search, and prompt-block formatting for
the Unified Memory Layer (SPEC-14 PR-A).

PR-A scope only: the store + manual facts + semantic search + export +
settings. No automatic extraction (PR-C) — facts are added by the user via
the API. No prompt-injection wiring (PR-B) — `format_memory_block` and
`search` are implemented now because PR-B reuses them unchanged, but nothing
in this codebase calls them from the chat/crew paths yet.

Mirrors ``services/rag_service.py``'s embed/store/retrieve pattern: inline
``"embedding": list[float]`` in the doc, numpy dot-product retrieval.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from models.memory_models import (
    MemoryFactCreate,
    MemoryFactUpdate,
    MemorySearchRequest,
    MemorySettingsUpdate,
)
from repositories.memory_repository import MemoryRepository
from repositories.memory_settings_repository import MemorySettingsRepository
from services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

# Cosine-similarity threshold above which two same-subject facts are treated
# as duplicates. Unused in PR-A (manual facts are never auto-deduped) — PR-C's
# extraction/dedupe pass wires this up.
DEDUPE_SIMILARITY = 0.92

DEFAULT_TOP_K = 8

# Editing any of these fields changes the rendered `text`, so the fact needs
# to be re-embedded.
_TEXT_FIELDS = ("subject", "predicate", "value", "text")


class MemoryService:
    def __init__(self, memory_repo: MemoryRepository, settings_repo: MemorySettingsRepository):
        self.memory_repo = memory_repo
        self.settings_repo = settings_repo

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(fact: Dict[str, Any]) -> Dict[str, Any]:
        """Strip the raw embedding vector; ensure both `_id` and `id` are set.

        Facts read via raw `collection.find()` carry `_id`; facts read via
        the inherited `BaseRepository.get_by_id`/`update` carry `id`
        (converted from `_id`). Callers (router/tests) shouldn't have to
        care which path produced the dict.
        """
        fact = dict(fact)
        fact.pop("embedding", None)
        if "_id" in fact and "id" not in fact:
            fact["id"] = fact["_id"]
        elif "id" in fact and "_id" not in fact:
            fact["_id"] = fact["id"]
        return fact

    @staticmethod
    async def _embed(text: str) -> Optional[List[float]]:
        """Best-effort embed. Returns None if the ONNX model isn't available
        (missing onnxruntime/tokenizers -> RuntimeError, missing model files
        -> FileNotFoundError) so callers can still save the fact without a
        vector — it just won't be eligible for semantic search."""
        try:
            return await asyncio.to_thread(embedding_service.embed, text)
        except (RuntimeError, FileNotFoundError) as e:
            logger.warning("Embedding unavailable, saving fact without a vector: %s", e)
            return None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add_fact(self, data: MemoryFactCreate) -> Dict[str, Any]:
        text = data.text or f"{data.subject} {data.predicate} {data.value}".strip()
        vector = await self._embed(text)

        now = datetime.utcnow().isoformat()
        doc: Dict[str, Any] = {
            "_id": str(uuid.uuid4()),
            "scope": data.scope,
            "subject": data.subject,
            "predicate": data.predicate,
            "value": data.value,
            "text": text,
            "confidence": 1.0,
            "status": "active",
            "pinned": False,
            "source_kind": "user",
            "source_id": None,
            "source_label": None,
            "origin": "user",
            "created_at": now,
            "updated_at": now,
            "last_used_at": None,
        }
        if vector is not None:
            doc["embedding"] = vector

        await self.memory_repo.collection.insert_one(doc)
        return self._normalize(doc)

    async def list_facts(
        self,
        scope: Optional[str] = None,
        status: Optional[str] = None,
        q: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if q:
            req = MemorySearchRequest(
                query=q, top_k=DEFAULT_TOP_K, scopes=[scope] if scope else None
            )
            results = await self.search(req)
            if status:
                results = [f for f in results if f.get("status") == status]
            return results

        if scope:
            facts = await self.memory_repo.list_by_scope(
                [scope], [status] if status else None
            )
        else:
            facts = await self.memory_repo.list_all()
            if status:
                facts = [f for f in facts if f.get("status") == status]

        facts.sort(
            key=lambda f: (bool(f.get("pinned")), f.get("updated_at") or ""),
            reverse=True,
        )
        return [self._normalize(f) for f in facts]

    async def get_fact(self, fact_id: str) -> Optional[Dict[str, Any]]:
        fact = await self.memory_repo.get_by_id(fact_id)
        return self._normalize(fact) if fact else None

    async def update_fact(
        self, fact_id: str, data: MemoryFactUpdate
    ) -> Optional[Dict[str, Any]]:
        existing = await self.memory_repo.get_by_id(fact_id)
        if not existing:
            return None

        patch = data.model_dump(exclude_unset=True, exclude_none=True)
        if not patch:
            return self._normalize(existing)

        if any(f in patch for f in _TEXT_FIELDS):
            subject = patch.get("subject", existing.get("subject"))
            predicate = patch.get("predicate", existing.get("predicate"))
            value = patch.get("value", existing.get("value"))
            text = patch.get("text") or f"{subject} {predicate} {value}".strip()
            patch["text"] = text

            vector = await self._embed(text)
            if vector is not None:
                patch["embedding"] = vector
            else:
                # Model unavailable — drop any stale vector rather than keep
                # an embedding that no longer matches the new text.
                await self.memory_repo.collection.update_one(
                    {"_id": fact_id}, {"$unset": {"embedding": ""}}
                )

        updated = await self.memory_repo.update(fact_id, patch)
        return self._normalize(updated) if updated else None

    async def delete_fact(self, fact_id: str) -> bool:
        return await self.memory_repo.delete(fact_id)

    async def set_pinned(self, fact_id: str, pinned: bool) -> Optional[Dict[str, Any]]:
        updated = await self.memory_repo.update(fact_id, {"pinned": pinned})
        return self._normalize(updated) if updated else None

    # ------------------------------------------------------------------
    # Recall / search — the primitive PR-B reuses for prompt-build recall
    # ------------------------------------------------------------------

    async def search(self, req: MemorySearchRequest) -> List[Dict[str, Any]]:
        """Semantic search over active + pinned facts that have an embedding.

        Bumps `last_used_at` on every returned fact. Gracefully returns []
        if the embedding model isn't available — search should never raise
        just because the ONNX model hasn't been downloaded yet.
        """
        query = (req.query or "").strip()
        if not query:
            return []

        try:
            q_vec = await asyncio.to_thread(embedding_service.embed, query)
        except (RuntimeError, FileNotFoundError) as e:
            logger.warning("Embedding service unavailable — memory search returning no results: %s", e)
            return []

        scopes = req.scopes or ["global"]
        top_k = req.top_k or DEFAULT_TOP_K

        all_facts = await self.memory_repo.list_by_scope(scopes, None)
        candidates = [
            f
            for f in all_facts
            if f.get("embedding") and (f.get("status") == "active" or f.get("pinned"))
        ]
        if not candidates:
            return []

        q = np.asarray(q_vec, dtype=np.float32)
        emb = np.asarray([f["embedding"] for f in candidates], dtype=np.float32)
        scores = emb @ q  # cosine for unit vectors
        order = np.argsort(-scores)[:top_k]

        results: List[Dict[str, Any]] = []
        used_ids: List[str] = []
        for idx in order:
            i = int(idx)
            f = candidates[i]
            fact = self._normalize(f)
            fact["score"] = float(scores[i])
            results.append(fact)
            used_ids.append(f["_id"])

        if used_ids:
            now = datetime.utcnow().isoformat()
            await self.memory_repo.collection.update_many(
                {"_id": {"$in": used_ids}}, {"$set": {"last_used_at": now}}
            )

        return results

    @staticmethod
    def format_memory_block(facts: List[Dict[str, Any]]) -> str:
        """Render a compact "## What I know" block for prompt injection.

        One bullet per fact, capped at ~12 lines. Returns "" if there's
        nothing to show — callers should skip prepending an empty block.
        """
        if not facts:
            return ""

        lines = ["## What I know"]
        for f in facts[:12]:
            text = f.get("text") or f"{f.get('subject', '')} {f.get('predicate', '')} {f.get('value', '')}".strip()
            if text:
                lines.append(f"- {text}")

        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    async def export_all(self) -> Dict[str, Any]:
        """Full JSON export of every fact, minus the raw embedding arrays."""
        facts = await self.memory_repo.list_all()
        exported: List[Dict[str, Any]] = []
        for f in facts:
            has_embedding = bool(f.get("embedding"))
            fact = self._normalize(f)
            fact["has_embedding"] = has_embedding
            exported.append(fact)
        return {"exported_at": datetime.utcnow().isoformat(), "facts": exported}

    # ------------------------------------------------------------------
    # Settings / kill switch
    # ------------------------------------------------------------------

    async def get_settings(self) -> Dict[str, Any]:
        settings = await self.settings_repo.get_settings()
        settings.pop("_id", None)
        return settings

    async def update_settings(self, patch: MemorySettingsUpdate) -> Dict[str, Any]:
        data = patch.model_dump(exclude_unset=True, exclude_none=True)
        settings = await self.settings_repo.update_settings(data)
        settings.pop("_id", None)
        return settings
