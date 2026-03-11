"""
MongoDB operation tools for Strands Agent.
Provides document queries, collection management, and aggregation capabilities.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from strands.tools import tool

logger = logging.getLogger(__name__)


class MongoDBTools:
    """
    MongoDB operation tools for personas with document query and collection management.

    Features:
    - List collections
    - Find documents with filters
    - Aggregation pipelines
    - Document counting
    - Collection statistics
    """

    def __init__(self, persona_id: str, credentials: Dict[str, Any]):
        """
        Initialize MongoDB tools with persona credentials.

        Args:
            persona_id: Unique persona identifier
            credentials: MongoDB connection credentials:
                - connectionString: Full MongoDB URI (preferred)
                - host, port, database, username, password (alternative)
        """
        self.persona_id = persona_id
        self.credentials = credentials
        self.database_name = credentials.get("database", "")

        # Build connection URI
        conn_string = credentials.get("connectionString", "")
        if conn_string:
            self.connection_uri = conn_string
        else:
            host = credentials.get("host", "localhost")
            port = credentials.get("port", 27017)
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            auth_source = credentials.get("auth_source", "admin")
            if username and password:
                self.connection_uri = f"mongodb://{username}:{password}@{host}:{port}/{self.database_name}?authSource={auth_source}"
            else:
                self.connection_uri = f"mongodb://{host}:{port}/{self.database_name}"

        logger.info(f"MongoDBTools initialized for persona {persona_id}, database: {self.database_name}")

    def get_tools(self):
        """Return all MongoDB operation tools as a list for Strands Agent."""
        return [
            self.list_collections,
            self.find_documents,
            self.aggregate,
            self.count_documents,
            self.collection_stats,
            self.test_connection,
        ]

    async def _get_client(self):
        """Create and return a Motor async client."""
        from motor.motor_asyncio import AsyncIOMotorClient
        return AsyncIOMotorClient(self.connection_uri, serverSelectionTimeoutMS=10000)

    @tool
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test MongoDB connection and return server information.

        Returns:
            Dictionary with connection status:
            {
                "success": bool,
                "response_time_ms": float,
                "server_version": str,
                "database": str,
                "error": Optional[str]
            }
        """
        try:
            start_time = time.time()
            client = await self._get_client()
            try:
                server_info = await client.server_info()
                response_time = round((time.time() - start_time) * 1000)

                return {
                    "success": True,
                    "response_time_ms": response_time,
                    "server_version": server_info.get("version", "unknown"),
                    "database": self.database_name,
                }
            finally:
                client.close()

        except Exception as e:
            logger.error(f"MongoDB connection test failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Connection failed: {str(e)}",
            }

    @tool
    async def list_collections(self) -> Dict[str, Any]:
        """
        List all collections in the connected MongoDB database.

        Returns:
            Dictionary with collection list:
            {
                "success": bool,
                "database": str,
                "collections": List of { name, type },
                "count": int,
                "error": Optional[str]
            }
        """
        try:
            client = await self._get_client()
            try:
                db = client[self.database_name]
                collections = await db.list_collection_names()

                collection_info = []
                for name in sorted(collections):
                    collection_info.append({"name": name, "type": "collection"})

                return {
                    "success": True,
                    "database": self.database_name,
                    "collections": collection_info,
                    "count": len(collection_info),
                }
            finally:
                client.close()

        except Exception as e:
            logger.error(f"Error listing collections: {e}", exc_info=True)
            return {"success": False, "error": str(e), "collections": [], "count": 0}

    @tool
    async def find_documents(
        self,
        collection: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Dict[str, Any]] = None,
        sort: Optional[Dict[str, int]] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Find documents in a MongoDB collection with optional filtering, projection, and sorting.

        Args:
            collection: Collection name to query
            filter: MongoDB query filter (e.g., {"status": "active", "age": {"$gt": 21}})
            projection: Fields to include/exclude (e.g., {"name": 1, "email": 1, "_id": 0})
            sort: Sort specification (e.g., {"created_at": -1} for descending)
            limit: Maximum documents to return (default: 20, max: 100)

        Returns:
            Dictionary with query results:
            {
                "success": bool,
                "collection": str,
                "documents": List[Dict],
                "count": int,
                "error": Optional[str]
            }
        """
        limit = min(limit, 100)
        try:
            client = await self._get_client()
            try:
                db = client[self.database_name]
                coll = db[collection]

                cursor = coll.find(filter or {}, projection or None)
                if sort:
                    sort_list = [(k, v) for k, v in sort.items()]
                    cursor = cursor.sort(sort_list)
                cursor = cursor.limit(limit)

                documents = []
                async for doc in cursor:
                    # Convert ObjectId to string for JSON serialization
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])
                    documents.append(doc)

                return {
                    "success": True,
                    "collection": collection,
                    "documents": documents,
                    "count": len(documents),
                }
            finally:
                client.close()

        except Exception as e:
            logger.error(f"Error finding documents: {e}", exc_info=True)
            return {"success": False, "error": str(e), "collection": collection, "documents": [], "count": 0}

    @tool
    async def aggregate(
        self,
        collection: str,
        pipeline: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Run a MongoDB aggregation pipeline on a collection.

        Args:
            collection: Collection name to run the pipeline on
            pipeline: List of aggregation stage documents
                (e.g., [{"$match": {"status": "active"}}, {"$group": {"_id": "$category", "total": {"$sum": 1}}}])

        Returns:
            Dictionary with aggregation results:
            {
                "success": bool,
                "collection": str,
                "results": List[Dict],
                "count": int,
                "error": Optional[str]
            }
        """
        try:
            client = await self._get_client()
            try:
                db = client[self.database_name]
                coll = db[collection]

                results = []
                async for doc in coll.aggregate(pipeline):
                    if "_id" in doc and not isinstance(doc["_id"], (str, int, float, bool)):
                        doc["_id"] = str(doc["_id"])
                    results.append(doc)

                return {
                    "success": True,
                    "collection": collection,
                    "results": results[:1000],  # Cap at 1000 results
                    "count": len(results),
                }
            finally:
                client.close()

        except Exception as e:
            logger.error(f"Error running aggregation: {e}", exc_info=True)
            return {"success": False, "error": str(e), "collection": collection, "results": [], "count": 0}

    @tool
    async def count_documents(
        self,
        collection: str,
        filter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Count documents in a collection, optionally with a filter.

        Args:
            collection: Collection name
            filter: Optional MongoDB query filter

        Returns:
            Dictionary with count:
            {
                "success": bool,
                "collection": str,
                "count": int,
                "error": Optional[str]
            }
        """
        try:
            client = await self._get_client()
            try:
                db = client[self.database_name]
                coll = db[collection]
                count = await coll.count_documents(filter or {})

                return {
                    "success": True,
                    "collection": collection,
                    "count": count,
                }
            finally:
                client.close()

        except Exception as e:
            logger.error(f"Error counting documents: {e}", exc_info=True)
            return {"success": False, "error": str(e), "collection": collection, "count": 0}

    @tool
    async def collection_stats(
        self,
        collection: str
    ) -> Dict[str, Any]:
        """
        Get statistics for a MongoDB collection.

        Args:
            collection: Collection name

        Returns:
            Dictionary with collection stats:
            {
                "success": bool,
                "collection": str,
                "stats": { document_count, avg_document_size, total_size, index_count, indexes },
                "error": Optional[str]
            }
        """
        try:
            client = await self._get_client()
            try:
                db = client[self.database_name]
                stats = await db.command("collStats", collection)

                # Get index info
                coll = db[collection]
                indexes = []
                async for idx in coll.list_indexes():
                    indexes.append({
                        "name": idx.get("name", ""),
                        "keys": dict(idx.get("key", {})),
                        "unique": idx.get("unique", False),
                    })

                return {
                    "success": True,
                    "collection": collection,
                    "stats": {
                        "document_count": stats.get("count", 0),
                        "avg_document_size": stats.get("avgObjSize", 0),
                        "total_size": stats.get("size", 0),
                        "storage_size": stats.get("storageSize", 0),
                        "index_count": stats.get("nindexes", 0),
                        "indexes": indexes,
                    },
                }
            finally:
                client.close()

        except Exception as e:
            logger.error(f"Error getting collection stats: {e}", exc_info=True)
            return {"success": False, "error": str(e), "collection": collection}
