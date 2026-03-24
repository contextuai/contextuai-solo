"""
Base Repository for MongoDB Operations

Abstract base class providing common CRUD operations for all repositories.
Uses motor for async MongoDB operations.
"""

from typing import TypeVar, Generic, List, Optional, Dict, Any, Type
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from abc import ABC, abstractmethod
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)


class BaseRepository(Generic[T], ABC):
    """
    Abstract base repository class for MongoDB operations.

    Provides common CRUD operations with pagination and filtering support.
    All repositories should inherit from this class.

    Type Parameters:
        T: The Pydantic model type for the repository entity

    Attributes:
        db: The MongoDB database instance
        collection: The MongoDB collection instance
        collection_name: Name of the collection
    """

    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str):
        """
        Initialize the repository with database and collection.

        Args:
            db: AsyncIOMotorDatabase instance
            collection_name: Name of the MongoDB collection
        """
        self.db: AsyncIOMotorDatabase = db
        self.collection_name: str = collection_name
        self.collection: AsyncIOMotorCollection = db[collection_name]

    @staticmethod
    def _convert_id(doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert MongoDB _id to string id in document.

        Args:
            doc: Document with _id field

        Returns:
            Document with id field as string, _id removed
        """
        if doc and '_id' in doc:
            doc['id'] = str(doc.pop('_id'))
        return doc

    @staticmethod
    def _to_object_id(id: str):
        """
        Convert string id to ObjectId, or return the raw string if it is
        not a valid ObjectId (e.g. UUID from the SQLite adapter).

        The motor_compat layer normalises ObjectId values back to strings
        before passing them to the SQLite adapter, so both forms work.
        """
        try:
            return ObjectId(id)
        except (InvalidId, TypeError, ValueError):
            # UUID or other non-ObjectId string — pass through as-is
            return id

    def _add_timestamps(self, data: Dict[str, Any], update: bool = False) -> Dict[str, Any]:
        """
        Add timestamp fields to document.

        Args:
            data: Document data
            update: If True, only add updated_at; if False, add created_at and updated_at

        Returns:
            Document with timestamp fields added
        """
        now = datetime.utcnow().isoformat()
        if not update:
            data['created_at'] = now
        data['updated_at'] = now
        return data

    async def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new document in the collection.

        Args:
            data: Document data to insert

        Returns:
            Created document with id field
        """
        data = self._add_timestamps(data.copy())
        result = await self.collection.insert_one(data)
        data['id'] = str(result.inserted_id)
        data.pop('_id', None)
        return data

    async def create_many(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create multiple documents in the collection.

        Args:
            documents: List of document data to insert

        Returns:
            List of created documents with id fields
        """
        docs = [self._add_timestamps(doc.copy()) for doc in documents]
        result = await self.collection.insert_many(docs)

        for doc, inserted_id in zip(docs, result.inserted_ids):
            doc['id'] = str(inserted_id)
            doc.pop('_id', None)

        return docs

    async def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a document by its ID.

        Args:
            id: String representation of the document's ObjectId

        Returns:
            Document with id field, or None if not found

        Raises:
            ValueError: If id is not a valid ObjectId string
        """
        object_id = self._to_object_id(id)
        doc = await self.collection.find_one({"_id": object_id})
        return self._convert_id(doc) if doc else None

    async def get_one(self, filter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single document matching the filter.

        Args:
            filter: MongoDB query filter

        Returns:
            Matching document with id field, or None if not found
        """
        doc = await self.collection.find_one(filter)
        return self._convert_id(doc) if doc else None

    async def get_all(
        self,
        filter: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None,
        projection: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all documents matching the filter with pagination.

        Args:
            filter: MongoDB query filter (default: empty filter)
            skip: Number of documents to skip (offset)
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting
                  Direction: 1 for ascending, -1 for descending
            projection: Fields to include/exclude in results

        Returns:
            List of documents with id fields
        """
        filter = filter or {}
        cursor = self.collection.find(filter, projection)

        if sort:
            cursor = cursor.sort(sort)

        cursor = cursor.skip(skip).limit(limit)

        docs = await cursor.to_list(length=limit)
        return [self._convert_id(doc) for doc in docs]

    async def get_paginated(
        self,
        filter: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort: Optional[List[tuple]] = None,
        projection: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Retrieve paginated documents with metadata.

        Args:
            filter: MongoDB query filter (default: empty filter)
            page: Page number (1-indexed)
            page_size: Number of documents per page
            sort: List of (field, direction) tuples for sorting
            projection: Fields to include/exclude in results

        Returns:
            Dictionary containing:
                - items: List of documents
                - total: Total count of matching documents
                - page: Current page number
                - page_size: Number of items per page
                - total_pages: Total number of pages
                - has_next: Whether there is a next page
                - has_prev: Whether there is a previous page
        """
        filter = filter or {}
        page = max(1, page)
        skip = (page - 1) * page_size

        # Get total count
        total = await self.count(filter)

        # Get paginated items
        items = await self.get_all(
            filter=filter,
            skip=skip,
            limit=page_size,
            sort=sort,
            projection=projection
        )

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }

    async def update(self, id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update a document by its ID.

        Args:
            id: String representation of the document's ObjectId
            data: Fields to update (partial update supported)

        Returns:
            Updated document with id field, or None if not found

        Raises:
            ValueError: If id is not a valid ObjectId string
        """
        object_id = self._to_object_id(id)
        data = self._add_timestamps(data.copy(), update=True)

        # Remove id field if present to avoid conflicts
        data.pop('id', None)
        data.pop('_id', None)

        result = await self.collection.find_one_and_update(
            {"_id": object_id},
            {"$set": data},
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def update_many(
        self,
        filter: Dict[str, Any],
        data: Dict[str, Any]
    ) -> int:
        """
        Update multiple documents matching the filter.

        Args:
            filter: MongoDB query filter
            data: Fields to update

        Returns:
            Number of documents modified
        """
        data = self._add_timestamps(data.copy(), update=True)
        data.pop('id', None)
        data.pop('_id', None)

        result = await self.collection.update_many(filter, {"$set": data})
        return result.modified_count

    async def delete(self, id: str) -> bool:
        """
        Delete a document by its ID.

        Args:
            id: String representation of the document's ObjectId

        Returns:
            True if document was deleted, False if not found

        Raises:
            ValueError: If id is not a valid ObjectId string
        """
        object_id = self._to_object_id(id)
        result = await self.collection.delete_one({"_id": object_id})
        return result.deleted_count > 0

    async def delete_many(self, filter: Dict[str, Any]) -> int:
        """
        Delete multiple documents matching the filter.

        Args:
            filter: MongoDB query filter

        Returns:
            Number of documents deleted
        """
        result = await self.collection.delete_many(filter)
        return result.deleted_count

    async def count(self, filter: Optional[Dict[str, Any]] = None) -> int:
        """
        Count documents matching the filter.

        Args:
            filter: MongoDB query filter (default: count all)

        Returns:
            Number of matching documents
        """
        filter = filter or {}
        return await self.collection.count_documents(filter)

    async def exists(self, filter: Dict[str, Any]) -> bool:
        """
        Check if any document matches the filter.

        Args:
            filter: MongoDB query filter

        Returns:
            True if at least one document matches, False otherwise
        """
        doc = await self.collection.find_one(filter, {"_id": 1})
        return doc is not None

    async def exists_by_id(self, id: str) -> bool:
        """
        Check if a document with the given ID exists.

        Args:
            id: String representation of the document's ObjectId

        Returns:
            True if document exists, False otherwise

        Raises:
            ValueError: If id is not a valid ObjectId string
        """
        object_id = self._to_object_id(id)
        return await self.exists({"_id": object_id})

    async def aggregate(
        self,
        pipeline: List[Dict[str, Any]],
        convert_ids: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Execute an aggregation pipeline.

        Args:
            pipeline: MongoDB aggregation pipeline stages
            convert_ids: Whether to convert _id to id in results

        Returns:
            List of aggregation results
        """
        cursor = self.collection.aggregate(pipeline)
        docs = await cursor.to_list(length=None)

        if convert_ids:
            return [self._convert_id(doc) for doc in docs]
        return docs

    async def distinct(
        self,
        field: str,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """
        Get distinct values for a field.

        Args:
            field: Field name to get distinct values for
            filter: Optional filter to apply

        Returns:
            List of distinct values
        """
        filter = filter or {}
        return await self.collection.distinct(field, filter)

    async def find_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        Retrieve multiple documents by their IDs.

        Args:
            ids: List of string representations of ObjectIds

        Returns:
            List of documents with id fields (order may not match input)

        Raises:
            ValueError: If any id is not a valid ObjectId string
        """
        object_ids = [self._to_object_id(id) for id in ids]
        docs = await self.collection.find({"_id": {"$in": object_ids}}).to_list(length=None)
        return [self._convert_id(doc) for doc in docs]

    async def upsert(
        self,
        filter: Dict[str, Any],
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a document or create it if it doesn't exist.

        Args:
            filter: MongoDB query filter to find the document
            data: Document data for update/insert

        Returns:
            Updated or created document with id field
        """
        data = data.copy()
        data.pop('id', None)
        data.pop('_id', None)

        now = datetime.utcnow().isoformat()

        result = await self.collection.find_one_and_update(
            filter,
            {
                "$set": {**data, "updated_at": now},
                "$setOnInsert": {"created_at": now}
            },
            upsert=True,
            return_document=True
        )

        return self._convert_id(result)

    async def soft_delete(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Soft delete a document by setting deleted_at timestamp.

        Args:
            id: String representation of the document's ObjectId

        Returns:
            Updated document with id field, or None if not found

        Raises:
            ValueError: If id is not a valid ObjectId string
        """
        return await self.update(id, {"deleted_at": datetime.utcnow().isoformat()})

    async def restore(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Restore a soft-deleted document by removing deleted_at.

        Args:
            id: String representation of the document's ObjectId

        Returns:
            Updated document with id field, or None if not found

        Raises:
            ValueError: If id is not a valid ObjectId string
        """
        object_id = self._to_object_id(id)

        result = await self.collection.find_one_and_update(
            {"_id": object_id},
            {
                "$unset": {"deleted_at": ""},
                "$set": {"updated_at": datetime.utcnow().isoformat()}
            },
            return_document=True
        )

        return self._convert_id(result) if result else None

    async def get_active(
        self,
        filter: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get documents that haven't been soft-deleted.

        Args:
            filter: Additional filter criteria
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            sort: List of (field, direction) tuples for sorting

        Returns:
            List of non-deleted documents with id fields
        """
        active_filter = {"deleted_at": {"$exists": False}}
        if filter:
            active_filter.update(filter)

        return await self.get_all(
            filter=active_filter,
            skip=skip,
            limit=limit,
            sort=sort
        )
