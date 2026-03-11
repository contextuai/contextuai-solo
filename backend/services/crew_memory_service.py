"""
Crew Memory Service — Business logic for persistent crew memory.

Provides a structured memory store that crews can use to:
- Remember facts, decisions, and user preferences across runs
- Build up knowledge over time (agent-level and crew-level)
- Inject relevant context into new runs automatically
- Support time-limited memories (TTL) for temporary context
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

from repositories.crew_memory_repository import CrewMemoryRepository

logger = logging.getLogger(__name__)

# Memory categories
MEMORY_CATEGORIES = [
    "general",       # General facts and information
    "decision",      # Decisions made during runs
    "preference",    # User or stakeholder preferences
    "feedback",      # Human feedback from checkpoints
    "output",        # Key outputs / artifacts from runs
    "error",         # Errors and how they were resolved
    "context",       # Contextual information about the domain
]

IMPORTANCE_LEVELS = ["low", "normal", "high", "critical"]

MAX_MEMORIES_PER_CREW = 500


class CrewMemoryService:
    """Service layer for crew memory operations."""

    def __init__(self, memory_repo: CrewMemoryRepository):
        self.memory_repo = memory_repo

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def add_memory(
        self,
        crew_id: str,
        content: str,
        *,
        key: Optional[str] = None,
        category: str = "general",
        source_run_id: Optional[str] = None,
        source_agent_id: Optional[str] = None,
        source_agent_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importance: str = "normal",
        ttl_hours: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Add a memory entry for a crew.

        Args:
            crew_id: The crew this memory belongs to
            content: The memory content (text)
            key: Optional unique key for upsert-style behavior
            category: Memory category (general, decision, preference, etc.)
            source_run_id: The run that generated this memory
            source_agent_id: The agent that generated this memory
            source_agent_name: Human-readable agent name
            tags: Optional tags for filtering
            importance: low, normal, high, or critical
            ttl_hours: Optional time-to-live in hours
        """
        if category not in MEMORY_CATEGORIES:
            raise ValueError(f"Invalid category '{category}'. Must be one of: {MEMORY_CATEGORIES}")
        if importance not in IMPORTANCE_LEVELS:
            raise ValueError(f"Invalid importance '{importance}'. Must be one of: {IMPORTANCE_LEVELS}")

        # Check capacity
        existing_count = await self.memory_repo.collection.count_documents({"crew_id": crew_id})
        if existing_count >= MAX_MEMORIES_PER_CREW:
            raise ValueError(f"Crew has reached the maximum of {MAX_MEMORIES_PER_CREW} memories. Delete old entries first.")

        # If a key is provided, check for existing entry and update it
        if key:
            existing = await self._find_by_key(crew_id, key)
            if existing:
                return await self.update_memory(
                    existing["memory_id"],
                    content=content,
                    tags=tags,
                    importance=importance,
                )

        # Calculate expiry
        expires_at = None
        if ttl_hours:
            expires_at = (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat()

        data = {
            "content": content,
            "key": key,
            "category": category,
            "source_run_id": source_run_id,
            "source_agent_id": source_agent_id,
            "source_agent_name": source_agent_name,
            "tags": tags or [],
            "importance": importance,
            "ttl_hours": ttl_hours,
            "expires_at": expires_at,
        }

        memory = await self.memory_repo.add_memory(crew_id, data)
        logger.info(f"Added memory {memory['memory_id']} to crew {crew_id} (category={category})")
        return memory

    async def update_memory(
        self,
        memory_id: str,
        *,
        content: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importance: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update an existing memory entry."""
        update_data: Dict[str, Any] = {}
        if content is not None:
            update_data["content"] = content
        if category is not None:
            if category not in MEMORY_CATEGORIES:
                raise ValueError(f"Invalid category '{category}'")
            update_data["category"] = category
        if tags is not None:
            update_data["tags"] = tags
        if importance is not None:
            if importance not in IMPORTANCE_LEVELS:
                raise ValueError(f"Invalid importance '{importance}'")
            update_data["importance"] = importance

        if not update_data:
            return await self.memory_repo.get_by_memory_id(memory_id)

        return await self.memory_repo.update_memory(memory_id, update_data)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a single memory entry."""
        return await self.memory_repo.get_by_memory_id(memory_id)

    async def list_memories(
        self,
        crew_id: str,
        category: Optional[str] = None,
        agent_id: Optional[str] = None,
        importance: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List memories with filters and pagination."""
        offset = (page - 1) * page_size
        return await self.memory_repo.get_crew_memories(
            crew_id,
            category=category,
            agent_id=agent_id,
            importance=importance,
            limit=page_size,
            offset=offset,
        )

    async def search_memories(
        self,
        crew_id: str,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search memories by text content."""
        return await self.memory_repo.search_memories(crew_id, query, limit=limit)

    async def get_run_context(
        self,
        crew_id: str,
        max_entries: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get formatted memory context for injection into a new crew run.

        Returns the most relevant, non-expired memories sorted by importance
        then recency. This is what gets passed to agents as context.
        """
        memories = await self.memory_repo.get_context_for_run(crew_id, max_entries)
        return memories

    async def format_context_prompt(
        self,
        crew_id: str,
        max_entries: int = 30,
    ) -> Optional[str]:
        """
        Build a text prompt from crew memories for injection into agent context.

        Returns None if no memories exist.
        """
        memories = await self.get_run_context(crew_id, max_entries)
        if not memories:
            return None

        lines = ["## Crew Memory (context from previous runs)\n"]
        for mem in memories:
            prefix = f"[{mem.get('category', 'general')}]"
            if mem.get("importance") in ("high", "critical"):
                prefix += f" [{mem['importance'].upper()}]"
            if mem.get("source_agent_name"):
                prefix += f" (from {mem['source_agent_name']})"
            lines.append(f"- {prefix} {mem['content']}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Delete operations
    # ------------------------------------------------------------------

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a single memory entry."""
        deleted = await self.memory_repo.delete_memory(memory_id)
        if deleted:
            logger.info(f"Deleted memory {memory_id}")
        return deleted

    async def clear_crew_memories(self, crew_id: str) -> int:
        """Clear all memories for a crew. Returns count deleted."""
        count = await self.memory_repo.clear_crew_memories(crew_id)
        logger.info(f"Cleared {count} memories for crew {crew_id}")
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _find_by_key(
        self, crew_id: str, key: str
    ) -> Optional[Dict[str, Any]]:
        """Find a memory by its unique key within a crew."""
        doc = await self.memory_repo.collection.find_one(
            {"crew_id": crew_id, "key": key}
        )
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def add_run_summary(
        self,
        crew_id: str,
        run_id: str,
        summary: str,
        agent_summaries: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Convenience method to add run summary memories after a crew execution.

        Creates a crew-level summary and optional per-agent summaries.
        """
        results = []

        # Overall run summary
        mem = await self.add_memory(
            crew_id,
            summary,
            key=f"run_summary_{run_id}",
            category="output",
            source_run_id=run_id,
            importance="high",
        )
        results.append(mem)

        # Per-agent summaries
        if agent_summaries:
            for agent_sum in agent_summaries:
                mem = await self.add_memory(
                    crew_id,
                    agent_sum.get("summary", ""),
                    key=f"agent_summary_{run_id}_{agent_sum.get('agent_id', '')}",
                    category="output",
                    source_run_id=run_id,
                    source_agent_id=agent_sum.get("agent_id"),
                    source_agent_name=agent_sum.get("agent_name"),
                    importance="normal",
                )
                results.append(mem)

        return results
