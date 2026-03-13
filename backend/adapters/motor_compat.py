"""
Motor Compatibility Layer

Provides proxy classes that make a ``DatabaseAdapter`` look like Motor's
``AsyncIOMotorDatabase`` and ``AsyncIOMotorCollection`` so that
``BaseRepository`` can work with **zero changes**.

Classes
-------
DatabaseProxy
    Drop-in replacement for ``AsyncIOMotorDatabase``.  Access a collection
    via ``db[name]`` or ``db.name`` and receive a ``CollectionProxy``.

CollectionProxy
    Drop-in replacement for ``AsyncIOMotorCollection``.  Every async method
    delegates to the underlying ``DatabaseAdapter``.

CursorProxy
    Lazy query builder returned by ``CollectionProxy.find()`` and
    ``.aggregate()``.  Supports ``.sort()``, ``.skip()``, ``.limit()``,
    and ``await .to_list(length)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from bson import ObjectId
from bson.errors import InvalidId

from adapters.database_adapter import DatabaseAdapter


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class InsertOneResult:
    """Mimics ``pymongo.results.InsertOneResult``."""
    inserted_id: str


@dataclass
class InsertManyResult:
    """Mimics ``pymongo.results.InsertManyResult``."""
    inserted_ids: List[str]


@dataclass
class UpdateResult:
    """Mimics ``pymongo.results.UpdateResult``."""
    modified_count: int
    matched_count: int = 0


@dataclass
class DeleteResult:
    """Mimics ``pymongo.results.DeleteResult``."""
    deleted_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_filter(filter_doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert ``ObjectId`` values in *filter_doc* to plain strings.

    This allows queries such as ``{"_id": ObjectId("...")}`` to work against
    adapters that store IDs as strings (e.g. SQLite with UUIDs).

    The function recurses into nested dicts and lists so that operators like
    ``{"_id": {"$in": [ObjectId(...), ...]}}`` are handled as well.
    """
    if filter_doc is None:
        return {}
    return _deep_convert(filter_doc)


def _deep_convert(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: _deep_convert(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        converted = [_deep_convert(item) for item in value]
        return type(value)(converted) if isinstance(value, tuple) else converted
    return value


def _apply_projection(
    doc: Optional[Dict[str, Any]],
    projection: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Apply a MongoDB-style projection to *doc*.

    Supports inclusion (``{field: 1}``) and exclusion (``{field: 0}``)
    projections.  ``_id`` is included by default unless explicitly excluded.
    """
    if doc is None or projection is None:
        return doc

    # Determine if this is an inclusion or exclusion projection.
    # MongoDB does not allow mixing 1s and 0s (except for _id).
    non_id_values = {v for k, v in projection.items() if k != "_id"}

    if non_id_values == {1} or non_id_values == {True}:
        # Inclusion projection
        include_keys = {k for k, v in projection.items() if v}
        # _id is included by default unless explicitly excluded
        if "_id" not in projection:
            include_keys.add("_id")
        elif not projection.get("_id"):
            include_keys.discard("_id")
        return {k: v for k, v in doc.items() if k in include_keys}

    if non_id_values == {0} or non_id_values == {False}:
        # Exclusion projection
        exclude_keys = {k for k, v in projection.items() if not v}
        return {k: v for k, v in doc.items() if k not in exclude_keys}

    # Empty or _id-only projection – return doc as-is
    return doc


# ---------------------------------------------------------------------------
# CursorProxy
# ---------------------------------------------------------------------------

class CursorProxy:
    """Lazy query builder that mimics an ``AsyncIOMotorCursor``.

    Parameters are accumulated via chained calls to ``.sort()``, ``.skip()``,
    and ``.limit()``.  The actual query runs when ``await .to_list()`` is
    called.
    """

    def __init__(
        self,
        adapter: DatabaseAdapter,
        collection_name: str,
        filter_doc: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        *,
        _preloaded: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._adapter = adapter
        self._collection = collection_name
        self._filter = filter_doc
        self._projection = projection
        self._sort: Optional[List[Tuple[str, int]]] = None
        self._skip: int = 0
        self._limit: int = 0
        self._preloaded = _preloaded

    # -- chaining methods ----------------------------------------------------

    def sort(self, sort_list: Union[List[Tuple[str, int]], str], direction: Optional[int] = None) -> "CursorProxy":
        """Store sort parameters; return *self* for chaining."""
        if isinstance(sort_list, str):
            self._sort = [(sort_list, direction or 1)]
        else:
            self._sort = list(sort_list)
        return self

    def skip(self, n: int) -> "CursorProxy":
        self._skip = n
        return self

    def limit(self, n: int) -> "CursorProxy":
        self._limit = n
        return self

    # -- execution -----------------------------------------------------------

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        """Execute the query and return a list of documents."""
        if self._preloaded is not None:
            docs = self._preloaded
        else:
            effective_limit = self._limit or (length if length is not None else 0)
            docs = await self._adapter.find(
                collection=self._collection,
                filter=self._filter,
                sort=self._sort,
                skip=self._skip,
                limit=effective_limit,
                projection=None,  # we apply projection ourselves for consistency
            )

        if self._projection:
            docs = [_apply_projection(d, self._projection) for d in docs if d is not None]

        return docs

    # Support ``async for doc in cursor``
    def __aiter__(self):
        return self._async_iter()

    async def _async_iter(self):
        docs = await self.to_list(length=None)
        for doc in docs:
            yield doc


# ---------------------------------------------------------------------------
# CollectionProxy
# ---------------------------------------------------------------------------

class CollectionProxy:
    """Wraps a ``DatabaseAdapter`` + collection name and exposes the same
    async interface as ``AsyncIOMotorCollection``."""

    def __init__(self, adapter: DatabaseAdapter, collection_name: str) -> None:
        self._adapter = adapter
        self._collection = collection_name

    # -- insert --------------------------------------------------------------

    async def insert_one(self, document: Dict[str, Any]) -> InsertOneResult:
        inserted_id = await self._adapter.insert_one(self._collection, document)
        return InsertOneResult(inserted_id=inserted_id)

    async def insert_many(self, documents: List[Dict[str, Any]]) -> InsertManyResult:
        inserted_ids = await self._adapter.insert_many(self._collection, documents)
        return InsertManyResult(inserted_ids=inserted_ids)

    # -- find ----------------------------------------------------------------

    async def find_one(
        self,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        normalized = _normalize_filter(filter)
        doc = await self._adapter.find_one(self._collection, normalized, projection=None)
        return _apply_projection(doc, projection)

    def find(
        self,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        *args: Any,
        **kwargs: Any,
    ) -> CursorProxy:
        """Return a ``CursorProxy`` (synchronous – the query is lazy)."""
        normalized = _normalize_filter(filter)
        return CursorProxy(
            adapter=self._adapter,
            collection_name=self._collection,
            filter_doc=normalized,
            projection=projection,
        )

    # -- update --------------------------------------------------------------

    async def find_one_and_update(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        return_document: bool = True,
        upsert: bool = False,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        normalized = _normalize_filter(filter)
        return await self._adapter.find_one_and_update(
            self._collection,
            normalized,
            update,
            upsert=upsert,
            return_document=return_document,
        )

    async def update_one(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
        **kwargs: Any,
    ) -> UpdateResult:
        normalized = _normalize_filter(filter)
        modified = await self._adapter.update_one(self._collection, normalized, update, upsert=upsert)
        return UpdateResult(modified_count=modified, matched_count=modified)

    async def update_many(
        self,
        filter: Dict[str, Any],
        update: Dict[str, Any],
        **kwargs: Any,
    ) -> UpdateResult:
        normalized = _normalize_filter(filter)
        modified = await self._adapter.update_many(self._collection, normalized, update)
        return UpdateResult(modified_count=modified, matched_count=modified)

    # -- delete --------------------------------------------------------------

    async def delete_one(self, filter: Dict[str, Any], **kwargs: Any) -> DeleteResult:
        normalized = _normalize_filter(filter)
        deleted = await self._adapter.delete_one(self._collection, normalized)
        return DeleteResult(deleted_count=deleted)

    async def delete_many(self, filter: Dict[str, Any], **kwargs: Any) -> DeleteResult:
        normalized = _normalize_filter(filter)
        deleted = await self._adapter.delete_many(self._collection, normalized)
        return DeleteResult(deleted_count=deleted)

    # -- count / distinct ----------------------------------------------------

    async def count_documents(self, filter: Optional[Dict[str, Any]] = None, **kwargs: Any) -> int:
        normalized = _normalize_filter(filter)
        return await self._adapter.count(self._collection, normalized)

    async def distinct(
        self,
        field: str,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Any]:
        normalized = _normalize_filter(filter)
        return await self._adapter.distinct(self._collection, field, normalized)

    # -- aggregate -----------------------------------------------------------

    def aggregate(self, pipeline: List[Dict[str, Any]], **kwargs: Any) -> CursorProxy:
        """Return a ``CursorProxy`` wrapping the aggregation result.

        The pipeline is executed eagerly when ``.to_list()`` is awaited on the
        returned cursor (matching Motor's behavior).
        """
        return _AggregationCursorProxy(
            adapter=self._adapter,
            collection_name=self._collection,
            pipeline=pipeline,
        )

    # -- index ---------------------------------------------------------------

    async def create_index(self, keys: Any, **kwargs: Any) -> str:
        return await self._adapter.create_index(self._collection, keys, **kwargs)


# ---------------------------------------------------------------------------
# Aggregation cursor (separate because it calls adapter.aggregate)
# ---------------------------------------------------------------------------

class _AggregationCursorProxy(CursorProxy):
    """Specialised cursor for aggregation pipelines."""

    def __init__(
        self,
        adapter: DatabaseAdapter,
        collection_name: str,
        pipeline: List[Dict[str, Any]],
    ) -> None:
        super().__init__(adapter, collection_name, filter_doc={})
        self._pipeline = pipeline

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        docs = await self._adapter.aggregate(self._collection, self._pipeline)
        return docs


# ---------------------------------------------------------------------------
# DatabaseProxy
# ---------------------------------------------------------------------------

class DatabaseProxy:
    """Drop-in replacement for ``AsyncIOMotorDatabase``.

    Usage::

        adapter = SqliteAdapter(...)      # or any DatabaseAdapter impl
        db = DatabaseProxy(adapter)
        repo = SomeRepository(db, "my_collection")
        # repo.collection is now a CollectionProxy
    """

    def __init__(self, adapter: DatabaseAdapter) -> None:
        self._adapter = adapter

    def __getitem__(self, collection_name: str) -> CollectionProxy:
        return CollectionProxy(self._adapter, collection_name)

    def __getattr__(self, collection_name: str) -> CollectionProxy:
        # Avoid hijacking dunder / private attributes
        if collection_name.startswith("_"):
            raise AttributeError(collection_name)
        return CollectionProxy(self._adapter, collection_name)
