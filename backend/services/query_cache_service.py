"""
Query Cache Service
Provides intelligent query result caching with DynamoDB integration.

Features:
- Query fingerprinting using MD5 hash of normalized query
- Cache key generation including persona_id
- TTL based on query type (5 min for simple, 30 min for aggregations)
- Cache invalidation rules
- Cache statistics tracking
- DynamoDB integration with query-cache table
"""

import time
import json
import logging
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import boto3
from boto3.dynamodb.conditions import Key

from config.database_config import get_cache_config
from services.sql_validator import QueryType

logger = logging.getLogger(__name__)


class QueryCacheService:
    """
    Query result caching service with intelligent TTL and invalidation.

    Features:
    - Query fingerprinting with MD5 hash
    - Persona-scoped caching
    - Query type-based TTL
    - Memory and DynamoDB two-tier caching
    - Cache statistics and monitoring
    - Automatic expiration
    """

    def __init__(self):
        """Initialize query cache service"""
        self._dynamodb = None  # Lazy initialization
        self._dynamodb_available = None
        self._cache_table = None

        # Get environment
        import os
        self.environment = os.getenv("ENVIRONMENT", "dev")

        # DynamoDB table
        self.cache_table_name = f"contextuai-backend-query-cache-{self.environment}"

    @property
    def dynamodb(self):
        """Lazy initialization of DynamoDB resource with region fallback."""
        if self._dynamodb is None and self._dynamodb_available is not False:
            try:
                import os
                region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
                self._dynamodb = boto3.resource('dynamodb', region_name=region)
                self._dynamodb_available = True
            except Exception as e:
                logger.warning(f"DynamoDB not available for query cache: {e}")
                self._dynamodb_available = False
        return self._dynamodb

    @property
    def cache_table(self):
        """Lazy initialization of cache table."""
        if self._cache_table is None and self.dynamodb is not None:
            self._cache_table = self.dynamodb.Table(self.cache_table_name)
        return self._cache_table

        # Cache configuration
        self.cache_config = get_cache_config("query")

        # Memory cache (L1 cache)
        self.memory_cache = {}
        self.memory_cache_access_times = {}
        self.max_memory_cache_items = self.cache_config.get("max_memory_cache_items", 100)
        self.memory_cache_ttl = self.cache_config.get("memory_cache_ttl", 600)  # 10 minutes

        # TTL configuration based on query type (seconds)
        self.query_type_ttl = {
            QueryType.SELECT: 300,  # 5 minutes - simple selects
            QueryType.UNKNOWN: 180,  # 3 minutes - unknown queries (be conservative)
        }

        # TTL for aggregation queries (detected by keywords)
        self.aggregation_ttl = 1800  # 30 minutes

        # Statistics
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_writes": 0,
            "cache_invalidations": 0,
            "memory_cache_hits": 0,
            "dynamodb_cache_hits": 0,
            "total_queries": 0,
            "bytes_cached": 0
        }

    async def get_cached_result(
        self,
        persona_id: str,
        query_hash: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached query result.

        Args:
            persona_id: Database persona identifier
            query_hash: Hash of the query

        Returns:
            Cached result if found and not expired, None otherwise
            {
                "data": List[Dict],
                "columns": List[str],
                "cached_at": str,
                "ttl": int
            }
        """
        self.stats["total_queries"] += 1

        cache_key = self._generate_cache_key(persona_id, query_hash)

        # L1: Check memory cache first
        memory_result = self._get_from_memory_cache(cache_key)
        if memory_result:
            self.stats["cache_hits"] += 1
            self.stats["memory_cache_hits"] += 1
            logger.debug(f"Memory cache hit for key {cache_key[:16]}...")
            return memory_result

        # L2: Check DynamoDB cache
        dynamodb_result = await self._get_from_dynamodb_cache(cache_key)
        if dynamodb_result:
            self.stats["cache_hits"] += 1
            self.stats["dynamodb_cache_hits"] += 1
            logger.debug(f"DynamoDB cache hit for key {cache_key[:16]}...")

            # Promote to memory cache
            self._set_memory_cache(cache_key, dynamodb_result)

            return dynamodb_result

        # Cache miss
        self.stats["cache_misses"] += 1
        logger.debug(f"Cache miss for key {cache_key[:16]}...")
        return None

    async def cache_result(
        self,
        persona_id: str,
        query_hash: str,
        query: str,
        data: List[Dict[str, Any]],
        columns: List[str],
        query_type: QueryType = QueryType.SELECT
    ) -> bool:
        """
        Cache query result with appropriate TTL.

        Args:
            persona_id: Database persona identifier
            query_hash: Hash of the query
            query: Original SQL query
            data: Query result data
            columns: Column names
            query_type: Type of query (affects TTL)

        Returns:
            True if cached successfully
        """
        try:
            cache_key = self._generate_cache_key(persona_id, query_hash)

            # Determine TTL based on query type and content
            ttl_seconds = self._calculate_ttl(query, query_type)

            # Prepare cache entry
            cache_entry = {
                "data": data,
                "columns": columns,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl": ttl_seconds,
                "query_preview": query[:200] if len(query) > 200 else query
            }

            # Calculate size for statistics
            cache_size = len(json.dumps(cache_entry))
            self.stats["bytes_cached"] += cache_size

            # L1: Store in memory cache
            self._set_memory_cache(cache_key, cache_entry)

            # L2: Store in DynamoDB cache
            success = await self._set_dynamodb_cache(
                cache_key=cache_key,
                persona_id=persona_id,
                query_hash=query_hash,
                query=query,
                data=data,
                columns=columns,
                ttl_seconds=ttl_seconds
            )

            if success:
                self.stats["cache_writes"] += 1
                logger.info(
                    f"Cached query result (key: {cache_key[:16]}..., "
                    f"rows: {len(data)}, ttl: {ttl_seconds}s, size: {cache_size} bytes)"
                )

            return success

        except Exception as e:
            logger.error(f"Failed to cache query result: {str(e)}", exc_info=True)
            return False

    def _generate_cache_key(self, persona_id: str, query_hash: str) -> str:
        """
        Generate cache key combining persona and query hash.

        Args:
            persona_id: Database persona identifier
            query_hash: Hash of the query

        Returns:
            Combined cache key
        """
        # Combine persona_id and query_hash for unique cache key
        combined = f"{persona_id}:{query_hash}"
        return hashlib.md5(combined.encode()).hexdigest()

    def _calculate_ttl(self, query: str, query_type: QueryType) -> int:
        """
        Calculate appropriate TTL based on query characteristics.

        Args:
            query: SQL query
            query_type: Type of query

        Returns:
            TTL in seconds
        """
        query_upper = query.upper()

        # Check for aggregation functions
        aggregation_keywords = [
            "COUNT(", "SUM(", "AVG(", "MIN(", "MAX(",
            "GROUP BY", "HAVING", "DISTINCT"
        ]

        if any(keyword in query_upper for keyword in aggregation_keywords):
            logger.debug(f"Detected aggregation query, using extended TTL: {self.aggregation_ttl}s")
            return self.aggregation_ttl

        # Check for complex joins
        if query_upper.count("JOIN") >= 2:
            logger.debug("Detected complex join, using extended TTL")
            return self.aggregation_ttl

        # Default TTL based on query type
        ttl = self.query_type_ttl.get(query_type, self.cache_config["query_cache_ttl"])

        logger.debug(f"Using default TTL for {query_type}: {ttl}s")
        return ttl

    def _get_from_memory_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get result from memory cache.

        Args:
            cache_key: Cache key

        Returns:
            Cached result or None
        """
        if cache_key not in self.memory_cache:
            return None

        # Check if expired
        access_time = self.memory_cache_access_times.get(cache_key, 0)
        if time.time() - access_time > self.memory_cache_ttl:
            # Expired, remove from cache
            del self.memory_cache[cache_key]
            del self.memory_cache_access_times[cache_key]
            return None

        # Update access time
        self.memory_cache_access_times[cache_key] = time.time()

        return self.memory_cache[cache_key]

    def _set_memory_cache(self, cache_key: str, value: Dict[str, Any]):
        """
        Set value in memory cache with LRU eviction.

        Args:
            cache_key: Cache key
            value: Value to cache
        """
        # Check if we need to evict (LRU)
        if len(self.memory_cache) >= self.max_memory_cache_items:
            # Find least recently used
            oldest_key = min(
                self.memory_cache_access_times.keys(),
                key=lambda k: self.memory_cache_access_times[k]
            )
            del self.memory_cache[oldest_key]
            del self.memory_cache_access_times[oldest_key]

        # Store in cache
        self.memory_cache[cache_key] = value
        self.memory_cache_access_times[cache_key] = time.time()

    async def _get_from_dynamodb_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get result from DynamoDB cache.

        Args:
            cache_key: Cache key

        Returns:
            Cached result or None
        """
        try:
            response = self.cache_table.get_item(
                Key={"cache_key": cache_key}
            )

            if "Item" not in response:
                return None

            item = response["Item"]

            # Check if expired (DynamoDB TTL is eventually consistent)
            if "expires_at" in item:
                expires_at = int(item["expires_at"])
                if time.time() > expires_at:
                    logger.debug(f"Cache entry expired for key {cache_key[:16]}...")
                    return None

            # Parse cached data
            return {
                "data": json.loads(item["data"]),
                "columns": json.loads(item["columns"]),
                "cached_at": item["cached_at"],
                "ttl": item.get("ttl_seconds", 0)
            }

        except Exception as e:
            logger.error(f"Failed to get from DynamoDB cache: {str(e)}")
            return None

    async def _set_dynamodb_cache(
        self,
        cache_key: str,
        persona_id: str,
        query_hash: str,
        query: str,
        data: List[Dict[str, Any]],
        columns: List[str],
        ttl_seconds: int
    ) -> bool:
        """
        Set result in DynamoDB cache.

        Args:
            cache_key: Cache key
            persona_id: Persona identifier
            query_hash: Query hash
            query: Original query
            data: Result data
            columns: Column names
            ttl_seconds: Time to live in seconds

        Returns:
            True if successful
        """
        try:
            # Calculate expiration timestamp
            expires_at = int(time.time()) + ttl_seconds

            # Prepare item
            item = {
                "cache_key": cache_key,
                "query_hash": query_hash,
                "persona_id": persona_id,
                "query": query[:1000],  # Truncate for DynamoDB
                "data": json.dumps(data),
                "columns": json.dumps(columns),
                "cached_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at,
                "ttl_seconds": ttl_seconds,
                "row_count": len(data)
            }

            # Write to DynamoDB (sync for now, use aioboto3 for true async)
            self.cache_table.put_item(Item=item)

            return True

        except Exception as e:
            logger.error(f"Failed to set DynamoDB cache: {str(e)}", exc_info=True)
            return False

    async def invalidate_cache(
        self,
        persona_id: Optional[str] = None,
        query_hash: Optional[str] = None
    ) -> int:
        """
        Invalidate cache entries.

        Args:
            persona_id: Invalidate all entries for persona (optional)
            query_hash: Invalidate specific query hash (optional)

        Returns:
            Number of entries invalidated
        """
        invalidated_count = 0

        try:
            if persona_id and query_hash:
                # Invalidate specific entry
                cache_key = self._generate_cache_key(persona_id, query_hash)

                # Remove from memory cache
                if cache_key in self.memory_cache:
                    del self.memory_cache[cache_key]
                    del self.memory_cache_access_times[cache_key]
                    invalidated_count += 1

                # Remove from DynamoDB
                self.cache_table.delete_item(Key={"cache_key": cache_key})
                invalidated_count += 1

            elif persona_id:
                # Invalidate all entries for persona
                # Query by persona_id using GSI
                response = self.cache_table.query(
                    IndexName='persona_id-expires_at-index',
                    KeyConditionExpression=Key('persona_id').eq(persona_id)
                )

                items = response.get('Items', [])

                for item in items:
                    cache_key = item["cache_key"]

                    # Remove from memory cache
                    if cache_key in self.memory_cache:
                        del self.memory_cache[cache_key]
                        del self.memory_cache_access_times[cache_key]

                    # Remove from DynamoDB
                    self.cache_table.delete_item(Key={"cache_key": cache_key})

                    invalidated_count += 1

            self.stats["cache_invalidations"] += invalidated_count

            logger.info(f"Invalidated {invalidated_count} cache entries")

        except Exception as e:
            logger.error(f"Failed to invalidate cache: {str(e)}", exc_info=True)

        return invalidated_count

    def clear_memory_cache(self):
        """Clear all entries from memory cache"""
        count = len(self.memory_cache)
        self.memory_cache.clear()
        self.memory_cache_access_times.clear()
        logger.info(f"Cleared {count} entries from memory cache")

    async def cleanup_expired(self) -> int:
        """
        Manually cleanup expired entries from memory cache.
        DynamoDB handles TTL automatically.

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = []

        for cache_key, access_time in self.memory_cache_access_times.items():
            if current_time - access_time > self.memory_cache_ttl:
                expired_keys.append(cache_key)

        for key in expired_keys:
            del self.memory_cache[key]
            del self.memory_cache_access_times[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired memory cache entries")

        return len(expired_keys)

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Statistics dictionary
        """
        total_requests = self.stats["cache_hits"] + self.stats["cache_misses"]
        hit_rate = (
            self.stats["cache_hits"] / total_requests
            if total_requests > 0 else 0
        )

        memory_hit_rate = (
            self.stats["memory_cache_hits"] / self.stats["cache_hits"]
            if self.stats["cache_hits"] > 0 else 0
        )

        return {
            **self.stats,
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "memory_hit_rate": memory_hit_rate,
            "memory_cache_size": len(self.memory_cache),
            "memory_cache_max_size": self.max_memory_cache_items,
            "avg_cached_bytes": (
                self.stats["bytes_cached"] / self.stats["cache_writes"]
                if self.stats["cache_writes"] > 0 else 0
            )
        }

    async def get_cache_info(self, persona_id: str) -> Dict[str, Any]:
        """
        Get cache information for a persona.

        Args:
            persona_id: Persona identifier

        Returns:
            Cache information
        """
        try:
            # Query DynamoDB for persona's cache entries
            response = self.cache_table.query(
                IndexName='persona_id-expires_at-index',
                KeyConditionExpression=Key('persona_id').eq(persona_id)
            )

            items = response.get('Items', [])

            return {
                "persona_id": persona_id,
                "total_cached_queries": len(items),
                "cache_entries": [
                    {
                        "query_hash": item["query_hash"],
                        "query_preview": item.get("query", "")[:100],
                        "row_count": item.get("row_count", 0),
                        "cached_at": item.get("cached_at"),
                        "expires_at": item.get("expires_at"),
                        "ttl_seconds": item.get("ttl_seconds", 0)
                    }
                    for item in items[:10]  # Limit to 10 most recent
                ]
            }

        except Exception as e:
            logger.error(f"Failed to get cache info: {str(e)}")
            return {
                "persona_id": persona_id,
                "total_cached_queries": 0,
                "cache_entries": [],
                "error": str(e)
            }


# Global query cache service instance
query_cache_service = QueryCacheService()
