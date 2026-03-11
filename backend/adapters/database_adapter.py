"""
Abstract Database Adapter

Defines the interface for all database operations. Implementations provide
MongoDB (enterprise) or SQLite (desktop) backends while exposing the same API.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DatabaseAdapter(ABC):
    """Abstract base class for database operations.

    All methods mirror MongoDB's collection-level operations so that
    existing repository code can switch backends transparently.
    """

    @abstractmethod
    async def find(
        self,
        collection: str,
        filter: dict,
        sort: list = None,
        limit: int = 0,
        skip: int = 0,
        projection: dict = None,
    ) -> list:
        """Find documents matching *filter* with optional sort, limit, skip."""
        ...

    @abstractmethod
    async def find_one(
        self, collection: str, filter: dict, projection: dict = None
    ) -> Optional[dict]:
        """Return the first document matching *filter*, or ``None``."""
        ...

    @abstractmethod
    async def insert_one(self, collection: str, document: dict) -> str:
        """Insert a single document. Returns the generated ``_id`` as a string."""
        ...

    @abstractmethod
    async def insert_many(self, collection: str, documents: list) -> list:
        """Insert multiple documents. Returns a list of ``_id`` strings."""
        ...

    @abstractmethod
    async def update_one(
        self,
        collection: str,
        filter: dict,
        update: dict,
        upsert: bool = False,
    ) -> int:
        """Update the first document matching *filter*. Returns modified count."""
        ...

    @abstractmethod
    async def update_many(
        self, collection: str, filter: dict, update: dict
    ) -> int:
        """Update all documents matching *filter*. Returns modified count."""
        ...

    @abstractmethod
    async def delete_one(self, collection: str, filter: dict) -> int:
        """Delete the first document matching *filter*. Returns deleted count."""
        ...

    @abstractmethod
    async def delete_many(self, collection: str, filter: dict) -> int:
        """Delete all documents matching *filter*. Returns deleted count."""
        ...

    @abstractmethod
    async def count(self, collection: str, filter: dict = None) -> int:
        """Count documents matching *filter*."""
        ...

    @abstractmethod
    async def distinct(
        self, collection: str, field: str, filter: dict = None
    ) -> list:
        """Return distinct values of *field* for documents matching *filter*."""
        ...

    @abstractmethod
    async def find_one_and_update(
        self,
        collection: str,
        filter: dict,
        update: dict,
        upsert: bool = False,
        return_document: bool = True,
    ) -> Optional[dict]:
        """Atomically find and update a document. Returns the document."""
        ...

    @abstractmethod
    async def aggregate(self, collection: str, pipeline: list) -> list:
        """Execute an aggregation pipeline against *collection*."""
        ...

    @abstractmethod
    async def create_index(self, collection: str, keys, **kwargs) -> str:
        """Create an index on *collection*. Returns the index name."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release all resources held by this adapter."""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """Return a health-check dict with at least ``healthy`` (bool) and ``message``."""
        ...
