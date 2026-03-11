"""
MSSQL Connector Service
Provides async MSSQL database connectivity with connection pooling,
health monitoring, and query execution capabilities.
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from config.database_config import get_pool_config, get_query_config
from services.connection_pool_manager import connection_pool_manager

logger = logging.getLogger(__name__)


class MSSQLConnector:
    """
    MSSQL database connector with async connection pooling.

    Features:
    - Async connection pooling using aioodbc
    - Connection health monitoring with automatic reconnection
    - Query timeout enforcement
    - Row limit enforcement
    - Connection pool metrics tracking
    - Integration with ConnectionPoolManager
    """

    def __init__(self):
        """Initialize MSSQL connector"""
        self.pool_manager = connection_pool_manager
        self.pool_config = get_pool_config("mssql")
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
        Execute a SQL query against MSSQL database.

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

        # Ensure credentials have db_type set to mssql
        mssql_credentials = {**credentials, "db_type": "mssql"}

        try:
            # Get connection pool
            pool = await self.pool_manager.get_pool(persona_id, mssql_credentials)

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
            cache_key = self.pool_manager._generate_cache_key(persona_id, mssql_credentials)
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
            mssql_credentials = {**credentials, "db_type": "mssql"}
            cache_key = self.pool_manager._generate_cache_key(persona_id, mssql_credentials)
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
        pool,
        query: str,
        params: Optional[List[Any]],
        row_limit: int
    ) -> Dict[str, Any]:
        """
        Execute query using connection from pool.

        Args:
            pool: aioodbc connection pool
            query: SQL query
            params: Query parameters
            row_limit: Maximum rows to fetch

        Returns:
            Query result dictionary
        """
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Add row limit clause if not present
                limited_query = self._add_limit_clause(query, row_limit)

                # Execute query
                if params:
                    await cursor.execute(limited_query, params)
                else:
                    await cursor.execute(limited_query)

                # Get column names from cursor description
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

                # Fetch all rows
                rows = await cursor.fetchall()

                # Convert tuples to dictionaries
                result_rows = [
                    {col: val for col, val in zip(columns, row)}
                    for row in rows
                ]

                return {
                    "success": True,
                    "rows": result_rows,
                    "row_count": len(result_rows),
                    "columns": columns
                }

    def _add_limit_clause(self, query: str, limit: int) -> str:
        """
        Add row limit to query using MSSQL-specific syntax.

        MSSQL uses different syntax depending on the query structure:
        - Simple SELECT: Add TOP N
        - With ORDER BY: Can use OFFSET FETCH
        - Subqueries: Handle appropriately

        Args:
            query: SQL query
            limit: Row limit

        Returns:
            Modified query with limit clause
        """
        query_upper = query.upper().strip()

        # Check if query already has TOP
        if "TOP " in query_upper.split("FROM")[0]:
            # Extract existing TOP value and use the smaller limit
            try:
                import re
                match = re.search(r'TOP\s+(\d+)', query_upper)
                if match:
                    existing_limit = int(match.group(1))
                    if existing_limit <= limit:
                        return query
                    else:
                        # Replace existing TOP with our limit
                        return re.sub(r'TOP\s+\d+', f'TOP {limit}', query, flags=re.IGNORECASE)
            except:
                pass

        # Check if query has OFFSET FETCH (pagination)
        if "OFFSET" in query_upper and "FETCH" in query_upper:
            # Already has pagination, respect it
            return query

        # Check if query has ORDER BY (can use OFFSET FETCH)
        if "ORDER BY" in query_upper:
            # Use OFFSET FETCH syntax for consistent pagination support
            query = query.rstrip().rstrip(';')
            return f"{query} OFFSET 0 ROWS FETCH NEXT {limit} ROWS ONLY"

        # Simple SELECT without ORDER BY - add TOP
        # Find position after SELECT keyword
        select_pos = query_upper.find("SELECT")
        if select_pos >= 0:
            # Check for DISTINCT
            distinct_pos = query_upper.find("DISTINCT", select_pos)
            if distinct_pos >= 0 and distinct_pos < query_upper.find("FROM"):
                # Insert after DISTINCT
                insert_pos = query.upper().find("DISTINCT") + 8
                return query[:insert_pos] + f" TOP {limit}" + query[insert_pos:]
            else:
                # Insert after SELECT
                insert_pos = select_pos + 6
                return query[:insert_pos] + f" TOP {limit}" + query[insert_pos:]

        # If we can't parse, return original query (will be limited by fetch size)
        return query

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

        # Ensure credentials have db_type set to mssql
        mssql_credentials = {**credentials, "db_type": "mssql"}

        try:
            pool = await self.pool_manager.get_pool(persona_id, mssql_credentials)

            async with pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    # Test basic connectivity with SELECT 1
                    await cursor.execute("SELECT 1 AS test")
                    await cursor.fetchone()

                    # Get SQL Server version
                    await cursor.execute("SELECT @@VERSION AS version")
                    version_row = await cursor.fetchone()
                    version = version_row[0] if version_row else "Unknown"

                    response_time_ms = (time.time() - start_time) * 1000

                    return {
                        "success": True,
                        "response_time_ms": response_time_ms,
                        "database_version": version,
                        "connection_pool_size": pool.size,
                        "free_connections": pool.freesize
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

        # MSSQL uses square brackets for identifiers and TOP for limiting
        query = f"SELECT TOP {sample_size} * FROM [{table_name}]"

        return await self.execute_query(
            persona_id,
            credentials,
            query,
            row_limit=sample_size
        )

    async def get_schema_info(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        database: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get database schema information.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            database: Optional database name (defaults to credentials database)

        Returns:
            Schema information including tables, columns, and relationships
        """
        db_name = database or credentials.get("database", "")

        try:
            # Get tables using INFORMATION_SCHEMA
            tables_query = """
                SELECT
                    TABLE_NAME as table_name,
                    TABLE_TYPE as table_type,
                    TABLE_SCHEMA as table_schema
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_CATALOG = ?
                    AND TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """

            tables_result = await self.execute_query(
                persona_id,
                credentials,
                tables_query,
                params=[db_name],
                row_limit=1000
            )

            if not tables_result["success"]:
                return tables_result

            # Get columns for all tables
            columns_query = """
                SELECT
                    TABLE_NAME as table_name,
                    COLUMN_NAME as column_name,
                    DATA_TYPE as data_type,
                    CHARACTER_MAXIMUM_LENGTH as max_length,
                    IS_NULLABLE as is_nullable,
                    COLUMN_DEFAULT as column_default,
                    ORDINAL_POSITION as ordinal_position
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_CATALOG = ?
                    AND TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """

            columns_result = await self.execute_query(
                persona_id,
                credentials,
                columns_query,
                params=[db_name],
                row_limit=10000
            )

            # Get indexes using sys.indexes
            indexes_query = """
                SELECT
                    t.name as table_name,
                    i.name as index_name,
                    i.type_desc as index_type,
                    i.is_unique as is_unique,
                    i.is_primary_key as is_primary_key
                FROM sys.indexes i
                INNER JOIN sys.tables t ON i.object_id = t.object_id
                WHERE i.name IS NOT NULL
                    AND t.is_ms_shipped = 0
                ORDER BY t.name, i.name
            """

            indexes_result = await self.execute_query(
                persona_id,
                credentials,
                indexes_query,
                row_limit=5000
            )

            # Get foreign keys using sys.foreign_keys
            fk_query = """
                SELECT
                    OBJECT_NAME(f.parent_object_id) as source_table,
                    COL_NAME(fc.parent_object_id, fc.parent_column_id) as source_column,
                    OBJECT_NAME(f.referenced_object_id) as target_table,
                    COL_NAME(fc.referenced_object_id, fc.referenced_column_id) as target_column,
                    f.name as constraint_name
                FROM sys.foreign_keys AS f
                INNER JOIN sys.foreign_key_columns AS fc
                    ON f.object_id = fc.constraint_object_id
                ORDER BY source_table, constraint_name
            """

            fk_result = await self.execute_query(
                persona_id,
                credentials,
                fk_query,
                row_limit=1000
            )

            # Organize columns by table
            columns_by_table = {}
            for col in columns_result.get("rows", []):
                table_name = col["table_name"]
                if table_name not in columns_by_table:
                    columns_by_table[table_name] = []
                columns_by_table[table_name].append(col)

            # Organize indexes by table
            indexes_by_table = {}
            for idx in indexes_result.get("rows", []):
                table_name = idx["table_name"]
                if table_name not in indexes_by_table:
                    indexes_by_table[table_name] = []
                indexes_by_table[table_name].append(idx)

            return {
                "success": True,
                "database": db_name,
                "tables": tables_result.get("rows", []),
                "columns_by_table": columns_by_table,
                "indexes_by_table": indexes_by_table,
                "foreign_keys": fk_result.get("rows", []),
                "table_count": len(tables_result.get("rows", []))
            }

        except Exception as e:
            logger.error(f"Failed to get schema info: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def explain_query(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        query: str
    ) -> Dict[str, Any]:
        """
        Get query execution plan using SET SHOWPLAN_XML or SET STATISTICS PROFILE.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            query: Query to explain

        Returns:
            Query execution plan
        """
        try:
            # MSSQL uses SET SHOWPLAN_XML ON for execution plans
            # Note: This returns XML plan without executing the query
            explain_queries = [
                "SET SHOWPLAN_XML ON",
                query,
                "SET SHOWPLAN_XML OFF"
            ]

            # Execute in batch
            results = await self.execute_batch(
                persona_id,
                credentials,
                [(q, None) for q in explain_queries]
            )

            if len(results) > 1 and results[1]["success"]:
                # The plan is in the second result (after SET SHOWPLAN_XML ON)
                plan_data = results[1].get("rows", [])

                return {
                    "success": True,
                    "explain": plan_data,
                    "format": "xml"
                }
            else:
                # Fallback: Try SET STATISTICS PROFILE ON (executes query and returns stats)
                profile_queries = [
                    "SET STATISTICS PROFILE ON",
                    query,
                    "SET STATISTICS PROFILE OFF"
                ]

                profile_results = await self.execute_batch(
                    persona_id,
                    credentials,
                    [(q, None) for q in profile_queries]
                )

                if len(profile_results) > 1 and profile_results[1]["success"]:
                    return {
                        "success": True,
                        "explain": profile_results[1].get("rows", []),
                        "format": "profile"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Could not retrieve execution plan"
                    }

        except Exception as e:
            logger.error(f"Failed to explain query: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def get_relationships(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        database: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get foreign key relationships for the database.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            database: Optional database name

        Returns:
            List of foreign key relationships
        """
        db_name = database or credentials.get("database", "")

        query = """
            SELECT
                f.name as constraint_name,
                OBJECT_NAME(f.parent_object_id) as source_table,
                COL_NAME(fc.parent_object_id, fc.parent_column_id) as source_column,
                OBJECT_NAME(f.referenced_object_id) as target_table,
                COL_NAME(fc.referenced_object_id, fc.referenced_column_id) as target_column,
                f.delete_referential_action_desc as delete_rule,
                f.update_referential_action_desc as update_rule
            FROM sys.foreign_keys AS f
            INNER JOIN sys.foreign_key_columns AS fc
                ON f.object_id = fc.constraint_object_id
            INNER JOIN sys.tables AS t
                ON f.parent_object_id = t.object_id
            WHERE t.is_ms_shipped = 0
            ORDER BY source_table, constraint_name
        """

        result = await self.execute_query(
            persona_id,
            credentials,
            query,
            row_limit=1000
        )

        if result["success"]:
            return {
                "success": True,
                "relationships": result["rows"],
                "relationship_count": len(result["rows"])
            }
        else:
            return result

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
        mssql_credentials = {**credentials, "db_type": "mssql"}
        cache_key = self.pool_manager._generate_cache_key(persona_id, mssql_credentials)
        await self.pool_manager._destroy_pool(cache_key)
        logger.info(f"Closed connection pool for persona {persona_id}")


# Global MSSQL connector instance
mssql_connector = MSSQLConnector()
