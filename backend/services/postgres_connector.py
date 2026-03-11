"""
PostgreSQL Connector Service
Provides async PostgreSQL database connectivity with connection pooling,
health monitoring, and query execution capabilities.
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import asyncpg
from asyncpg.pool import Pool

from config.database_config import get_pool_config, get_query_config
from services.connection_pool_manager import connection_pool_manager

logger = logging.getLogger(__name__)


class PostgreSQLConnector:
    """
    PostgreSQL database connector with async connection pooling.

    Features:
    - Async connection pooling using asyncpg
    - Connection health monitoring with automatic reconnection
    - Query timeout enforcement
    - Row limit enforcement
    - Connection pool metrics tracking
    - Integration with ConnectionPoolManager
    """

    def __init__(self):
        """Initialize PostgreSQL connector"""
        self.pool_manager = connection_pool_manager
        self.pool_config = get_pool_config("postgresql")
        self.query_config = get_query_config()

        # Metrics
        self.metrics = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "total_query_time_ms": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }

    async def execute_query(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        query: str,
        params: Optional[List[Any]] = None,
        timeout: Optional[int] = None,
        row_limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a SQL query against PostgreSQL database.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            query: SQL query to execute
            params: Optional query parameters
            timeout: Query timeout in seconds (default from config)
            row_limit: Maximum rows to return (default from config)

        Returns:
            Dictionary with query results and metadata:
            {
                "success": bool,
                "rows": List[Dict],
                "row_count": int,
                "columns": List[str],
                "execution_time_ms": float,
                "error": Optional[str]
            }

        Raises:
            Exception: If query execution fails critically
        """
        start_time = time.time()
        self.metrics["total_queries"] += 1

        # Apply defaults
        if timeout is None:
            timeout = self.query_config["default_timeout"]
        if row_limit is None:
            row_limit = self.query_config["default_row_limit"]

        # Enforce limits
        timeout = min(timeout, self.query_config["max_timeout"])
        row_limit = min(row_limit, self.query_config["max_row_limit"])

        try:
            # Get connection pool
            pool = await self.pool_manager.get_pool(persona_id, credentials)

            # Execute query with timeout
            async with asyncio.timeout(timeout):
                result = await self._execute_with_pool(
                    pool, query, params, row_limit
                )

            # Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000
            self.metrics["total_query_time_ms"] += execution_time_ms
            self.metrics["successful_queries"] += 1

            # Update pool metrics
            cache_key = self.pool_manager._generate_cache_key(persona_id, credentials)
            if cache_key in self.pool_manager.pool_metrics:
                metrics = self.pool_manager.pool_metrics[cache_key]
                metrics.total_queries += 1
                metrics.last_used = time.time()

                # Update average query time
                total_time = metrics.avg_query_time_ms * (metrics.total_queries - 1)
                metrics.avg_query_time_ms = (total_time + execution_time_ms) / metrics.total_queries

            logger.info(
                f"Query executed successfully for persona {persona_id}: "
                f"{result['row_count']} rows in {execution_time_ms:.2f}ms"
            )

            result["execution_time_ms"] = execution_time_ms
            return result

        except asyncio.TimeoutError:
            self.metrics["failed_queries"] += 1
            execution_time_ms = (time.time() - start_time) * 1000

            logger.error(
                f"Query timeout after {timeout}s for persona {persona_id}"
            )

            return {
                "success": False,
                "rows": [],
                "row_count": 0,
                "columns": [],
                "execution_time_ms": execution_time_ms,
                "error": f"Query timeout after {timeout} seconds"
            }

        except Exception as e:
            self.metrics["failed_queries"] += 1
            execution_time_ms = (time.time() - start_time) * 1000

            # Update pool error metrics
            cache_key = self.pool_manager._generate_cache_key(persona_id, credentials)
            if cache_key in self.pool_manager.pool_metrics:
                self.pool_manager.pool_metrics[cache_key].connection_errors += 1

            logger.error(
                f"Query execution failed for persona {persona_id}: {str(e)}",
                exc_info=True
            )

            return {
                "success": False,
                "rows": [],
                "row_count": 0,
                "columns": [],
                "execution_time_ms": execution_time_ms,
                "error": str(e)
            }

    async def _execute_with_pool(
        self,
        pool: Pool,
        query: str,
        params: Optional[List[Any]],
        row_limit: int
    ) -> Dict[str, Any]:
        """
        Execute query using connection from pool.

        Args:
            pool: asyncpg connection pool
            query: SQL query
            params: Query parameters
            row_limit: Maximum rows to fetch

        Returns:
            Query result dictionary
        """
        async with pool.acquire() as conn:
            # Add LIMIT clause if not present
            limited_query = self._add_limit_clause(query, row_limit)

            # Execute query
            if params:
                rows = await conn.fetch(limited_query, *params)
            else:
                rows = await conn.fetch(limited_query)

            # Convert rows to dictionaries
            result_rows = [dict(row) for row in rows]

            # Get column names
            columns = list(rows[0].keys()) if rows else []

            return {
                "success": True,
                "rows": result_rows,
                "row_count": len(result_rows),
                "columns": columns
            }

    def _add_limit_clause(self, query: str, limit: int) -> str:
        """
        Add LIMIT clause to query if not already present.

        Args:
            query: SQL query
            limit: Row limit

        Returns:
            Modified query with LIMIT clause
        """
        query_upper = query.upper().strip()

        # Check if LIMIT already exists
        if "LIMIT" in query_upper:
            # Extract existing limit and use the smaller value
            try:
                import re
                match = re.search(r'LIMIT\s+(\d+)', query_upper)
                if match:
                    existing_limit = int(match.group(1))
                    if existing_limit <= limit:
                        return query
            except:
                pass

        # Add LIMIT clause
        query = query.rstrip().rstrip(';')
        return f"{query} LIMIT {limit}"

    async def execute_batch(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        queries: List[Tuple[str, Optional[List[Any]]]],
        timeout: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple queries in a batch.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            queries: List of (query, params) tuples
            timeout: Overall timeout for all queries

        Returns:
            List of query results
        """
        if timeout is None:
            timeout = self.query_config["default_timeout"] * len(queries)

        results = []
        start_time = time.time()

        try:
            async with asyncio.timeout(timeout):
                for query, params in queries:
                    # Check if we're running out of time
                    elapsed = time.time() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        results.append({
                            "success": False,
                            "error": "Batch timeout exceeded",
                            "rows": [],
                            "row_count": 0,
                            "columns": []
                        })
                        continue

                    result = await self.execute_query(
                        persona_id,
                        credentials,
                        query,
                        params,
                        timeout=int(remaining)
                    )
                    results.append(result)

        except asyncio.TimeoutError:
            logger.error(f"Batch execution timeout after {timeout}s")
            # Return partial results with timeout error for remaining
            while len(results) < len(queries):
                results.append({
                    "success": False,
                    "error": "Batch timeout exceeded",
                    "rows": [],
                    "row_count": 0,
                    "columns": []
                })

        return results

    async def test_connection(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Test database connection health.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials

        Returns:
            Connection test result:
            {
                "success": bool,
                "response_time_ms": float,
                "database_version": str,
                "error": Optional[str]
            }
        """
        start_time = time.time()

        try:
            pool = await self.pool_manager.get_pool(persona_id, credentials)

            async with pool.acquire() as conn:
                # Test basic connectivity
                version = await conn.fetchval("SELECT version()")

                response_time_ms = (time.time() - start_time) * 1000

                return {
                    "success": True,
                    "response_time_ms": response_time_ms,
                    "database_version": version,
                    "connection_pool_size": pool.get_size(),
                    "idle_connections": pool.get_idle_size()
                }

        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000

            logger.error(f"Connection test failed: {str(e)}")

            return {
                "success": False,
                "response_time_ms": response_time_ms,
                "database_version": None,
                "error": str(e)
            }

    async def get_table_sample(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        table_name: str,
        sample_size: int = 10
    ) -> Dict[str, Any]:
        """
        Get sample rows from a table.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            table_name: Table to sample
            sample_size: Number of rows to return

        Returns:
            Sample data result
        """
        # Sanitize table name to prevent SQL injection
        if not self._is_valid_identifier(table_name):
            return {
                "success": False,
                "error": "Invalid table name",
                "rows": [],
                "row_count": 0,
                "columns": []
            }

        query = f"SELECT * FROM {table_name} LIMIT {sample_size}"

        return await self.execute_query(
            persona_id,
            credentials,
            query,
            row_limit=sample_size
        )

    def _is_valid_identifier(self, identifier: str) -> bool:
        """
        Validate SQL identifier (table/column name).

        Args:
            identifier: Identifier to validate

        Returns:
            True if valid, False otherwise
        """
        import re
        # Allow alphanumeric, underscore, dot (for schema.table)
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$'
        return bool(re.match(pattern, identifier))

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get connector metrics.

        Returns:
            Dictionary with connector metrics
        """
        avg_query_time = 0
        if self.metrics["successful_queries"] > 0:
            avg_query_time = (
                self.metrics["total_query_time_ms"] /
                self.metrics["successful_queries"]
            )

        return {
            **self.metrics,
            "avg_query_time_ms": avg_query_time,
            "success_rate": (
                self.metrics["successful_queries"] / self.metrics["total_queries"]
                if self.metrics["total_queries"] > 0 else 0
            )
        }

    async def close_pool(self, persona_id: str, credentials: Dict[str, Any]):
        """
        Manually close connection pool for a persona.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
        """
        cache_key = self.pool_manager._generate_cache_key(persona_id, credentials)
        await self.pool_manager._destroy_pool(cache_key)
        logger.info(f"Closed connection pool for persona {persona_id}")


# Global PostgreSQL connector instance
postgres_connector = PostgreSQLConnector()
