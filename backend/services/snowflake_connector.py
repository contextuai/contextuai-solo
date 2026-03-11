"""
Snowflake Connector Service
Provides async Snowflake data warehouse connectivity with connection pooling,
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


class SnowflakeConnector:
    """
    Snowflake data warehouse connector with async connection pooling.

    Features:
    - Async connection pooling using snowflake-connector-python with asyncio
    - Connection health monitoring with automatic reconnection
    - Query timeout enforcement
    - Row limit enforcement
    - Connection pool metrics tracking
    - Integration with ConnectionPoolManager
    - Support for VARIANT, ARRAY, OBJECT data types
    """

    def __init__(self):
        """Initialize Snowflake connector"""
        self.pool_manager = connection_pool_manager
        self.pool_config = get_pool_config("snowflake")
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
        Execute a SQL query against Snowflake data warehouse.

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

        # Ensure credentials have db_type set to snowflake
        snowflake_credentials = {**credentials, "db_type": "snowflake"}

        try:
            # Get connection pool
            pool = await self.pool_manager.get_pool(persona_id, snowflake_credentials)

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
            cache_key = self.pool_manager._generate_cache_key(persona_id, snowflake_credentials)
            if cache_key in self.pool_manager.pool_metrics:
                metrics = self.pool_manager.pool_metrics[cache_key]
                metrics.total_queries += 1
                metrics.last_used = time.time()

                # Update average query time
                total_time = metrics.avg_query_time_ms * (metrics.total_queries - 1)
                metrics.avg_query_time_ms = (total_time + execution_time_ms) / metrics.total_queries

            logger.info(
                f"❄️ Query executed successfully for persona {persona_id}: "
                f"{result['row_count']} rows in {execution_time_ms:.2f}ms"
            )

            result["execution_time_ms"] = execution_time_ms
            return result

        except asyncio.TimeoutError:
            self.metrics["failed_queries"] += 1
            execution_time_ms = (time.time() - start_time) * 1000

            logger.error(
                f"❄️ Query timeout after {timeout}s for persona {persona_id}"
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
            snowflake_credentials = {**credentials, "db_type": "snowflake"}
            cache_key = self.pool_manager._generate_cache_key(persona_id, snowflake_credentials)
            if cache_key in self.pool_manager.pool_metrics:
                self.pool_manager.pool_metrics[cache_key].connection_errors += 1

            logger.error(
                f"❄️ Query execution failed for persona {persona_id}: {str(e)}",
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
            pool: Snowflake connection pool
            query: SQL query
            params: Query parameters
            row_limit: Maximum rows to fetch

        Returns:
            Query result dictionary
        """
        # Snowflake connector doesn't have async context manager, wrap in thread
        import snowflake.connector

        def execute_sync():
            conn = pool.acquire()
            try:
                cursor = conn.cursor()
                try:
                    # Add row limit clause if not present
                    limited_query = self._add_limit_clause(query, row_limit)

                    # Execute query
                    if params:
                        cursor.execute(limited_query, params)
                    else:
                        cursor.execute(limited_query)

                    # Get column names from cursor description
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []

                    # Fetch all rows
                    rows = cursor.fetchall()

                    # Convert tuples to dictionaries
                    result_rows = [
                        {col: self._convert_snowflake_type(val) for col, val in zip(columns, row)}
                        for row in rows
                    ]

                    return {
                        "success": True,
                        "rows": result_rows,
                        "row_count": len(result_rows),
                        "columns": columns
                    }
                finally:
                    cursor.close()
            finally:
                pool.release(conn)

        # Run synchronous Snowflake code in thread pool
        return await asyncio.to_thread(execute_sync)

    def _convert_snowflake_type(self, val: Any) -> Any:
        """
        Convert Snowflake-specific data types to Python native types.

        Args:
            val: Value from Snowflake query result

        Returns:
            Converted value
        """
        # Handle datetime objects
        if isinstance(val, datetime):
            return val.isoformat()

        # Handle VARIANT, ARRAY, OBJECT types (returned as strings)
        # These are already JSON-compatible
        return val

    def _add_limit_clause(self, query: str, limit: int) -> str:
        """
        Add row limit to query using Snowflake LIMIT syntax.

        Snowflake uses standard SQL LIMIT clause:
        SELECT ... LIMIT n

        Args:
            query: SQL query
            limit: Row limit

        Returns:
            Modified query with limit clause
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
                    else:
                        # Replace existing LIMIT with our limit
                        return re.sub(r'LIMIT\s+\d+', f'LIMIT {limit}', query, flags=re.IGNORECASE)
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
            logger.error(f"❄️ Batch execution timeout after {timeout}s")
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
                "connection_pool_size": int,
                "error": Optional[str]
            }
        """
        start_time = time.time()

        # Ensure credentials have db_type set to snowflake
        snowflake_credentials = {**credentials, "db_type": "snowflake"}

        try:
            pool = await self.pool_manager.get_pool(persona_id, snowflake_credentials)

            def test_sync():
                conn = pool.acquire()
                try:
                    cursor = conn.cursor()
                    try:
                        # Test basic connectivity with SELECT 1
                        cursor.execute("SELECT 1 AS test")
                        cursor.fetchone()

                        # Get Snowflake version
                        cursor.execute("SELECT CURRENT_VERSION() AS version")
                        version_row = cursor.fetchone()
                        version = version_row[0] if version_row else "Unknown"

                        return version
                    finally:
                        cursor.close()
                finally:
                    pool.release(conn)

            version = await asyncio.to_thread(test_sync)
            response_time_ms = (time.time() - start_time) * 1000

            return {
                "success": True,
                "response_time_ms": response_time_ms,
                "database_version": version,
                "connection_pool_size": pool.size,
                "warehouse": credentials.get("warehouse", "N/A"),
                "account": credentials.get("account", "N/A")
            }

        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000

            logger.error(f"❄️ Connection test failed: {str(e)}")

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
            table_name: Table to sample (can include database.schema.table)
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

        # Snowflake uses standard SQL LIMIT
        query = f"SELECT * FROM {table_name} LIMIT {sample_size}"

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
        database: Optional[str] = None,
        schema: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get database schema information.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            database: Optional database name (defaults to credentials database)
            schema: Optional schema name (defaults to PUBLIC)

        Returns:
            Schema information including tables, columns, and relationships
        """
        db_name = database or credentials.get("database", "")
        schema_name = schema or credentials.get("schema", "PUBLIC")

        try:
            # Get tables using INFORMATION_SCHEMA
            tables_query = """
                SELECT
                    TABLE_NAME as table_name,
                    TABLE_TYPE as table_type,
                    TABLE_SCHEMA as table_schema,
                    TABLE_CATALOG as table_catalog,
                    ROW_COUNT as row_count,
                    BYTES as bytes,
                    COMMENT as table_comment
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_CATALOG = ?
                    AND TABLE_SCHEMA = ?
                ORDER BY TABLE_SCHEMA, TABLE_NAME
            """

            tables_result = await self.execute_query(
                persona_id,
                credentials,
                tables_query,
                params=[db_name.upper(), schema_name.upper()],
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
                    NUMERIC_PRECISION as numeric_precision,
                    NUMERIC_SCALE as numeric_scale,
                    IS_NULLABLE as is_nullable,
                    COLUMN_DEFAULT as column_default,
                    ORDINAL_POSITION as ordinal_position,
                    COMMENT as column_comment
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_CATALOG = ?
                    AND TABLE_SCHEMA = ?
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """

            columns_result = await self.execute_query(
                persona_id,
                credentials,
                columns_query,
                params=[db_name.upper(), schema_name.upper()],
                row_limit=10000
            )

            # Get primary keys
            pk_query = """
                SELECT
                    TABLE_NAME as table_name,
                    COLUMN_NAME as column_name,
                    CONSTRAINT_NAME as constraint_name
                FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                    AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                    AND tc.TABLE_CATALOG = kcu.TABLE_CATALOG
                WHERE tc.TABLE_CATALOG = ?
                    AND tc.TABLE_SCHEMA = ?
                    AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """

            pk_result = await self.execute_query(
                persona_id,
                credentials,
                pk_query,
                params=[db_name.upper(), schema_name.upper()],
                row_limit=5000
            )

            # Get foreign keys
            fk_query = """
                SELECT
                    rc.CONSTRAINT_NAME as constraint_name,
                    kcu1.TABLE_NAME as source_table,
                    kcu1.COLUMN_NAME as source_column,
                    kcu2.TABLE_NAME as target_table,
                    kcu2.COLUMN_NAME as target_column,
                    rc.UPDATE_RULE as update_rule,
                    rc.DELETE_RULE as delete_rule
                FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu1
                    ON rc.CONSTRAINT_NAME = kcu1.CONSTRAINT_NAME
                    AND rc.CONSTRAINT_SCHEMA = kcu1.CONSTRAINT_SCHEMA
                    AND rc.CONSTRAINT_CATALOG = kcu1.CONSTRAINT_CATALOG
                JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
                    ON rc.UNIQUE_CONSTRAINT_NAME = kcu2.CONSTRAINT_NAME
                    AND rc.UNIQUE_CONSTRAINT_SCHEMA = kcu2.CONSTRAINT_SCHEMA
                    AND rc.UNIQUE_CONSTRAINT_CATALOG = kcu2.CONSTRAINT_CATALOG
                WHERE rc.CONSTRAINT_CATALOG = ?
                    AND rc.CONSTRAINT_SCHEMA = ?
                ORDER BY source_table, constraint_name
            """

            fk_result = await self.execute_query(
                persona_id,
                credentials,
                fk_query,
                params=[db_name.upper(), schema_name.upper()],
                row_limit=1000
            )

            # Organize columns by table
            columns_by_table = {}
            for col in columns_result.get("rows", []):
                table_name = col["table_name"]
                if table_name not in columns_by_table:
                    columns_by_table[table_name] = []
                columns_by_table[table_name].append(col)

            # Organize primary keys by table
            pk_by_table = {}
            for pk in pk_result.get("rows", []):
                table_name = pk["table_name"]
                if table_name not in pk_by_table:
                    pk_by_table[table_name] = []
                pk_by_table[table_name].append(pk)

            return {
                "success": True,
                "database": db_name,
                "schema": schema_name,
                "tables": tables_result.get("rows", []),
                "columns_by_table": columns_by_table,
                "primary_keys_by_table": pk_by_table,
                "foreign_keys": fk_result.get("rows", []),
                "table_count": len(tables_result.get("rows", []))
            }

        except Exception as e:
            logger.error(f"❄️ Failed to get schema info: {e}", exc_info=True)
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
        Get query execution plan using EXPLAIN.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            query: Query to explain

        Returns:
            Query execution plan
        """
        try:
            # Snowflake uses EXPLAIN for execution plans
            explain_query = f"EXPLAIN {query}"

            result = await self.execute_query(
                persona_id,
                credentials,
                explain_query,
                row_limit=1000
            )

            if result["success"]:
                return {
                    "success": True,
                    "explain": result.get("rows", []),
                    "format": "tabular"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "EXPLAIN failed")
                }

        except Exception as e:
            logger.error(f"❄️ Failed to explain query: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def get_relationships(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        database: Optional[str] = None,
        schema: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get foreign key relationships for the database.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            database: Optional database name
            schema: Optional schema name

        Returns:
            List of foreign key relationships
        """
        db_name = database or credentials.get("database", "")
        schema_name = schema or credentials.get("schema", "PUBLIC")

        query = """
            SELECT
                rc.CONSTRAINT_NAME as constraint_name,
                kcu1.TABLE_NAME as source_table,
                kcu1.COLUMN_NAME as source_column,
                kcu2.TABLE_NAME as target_table,
                kcu2.COLUMN_NAME as target_column,
                rc.UPDATE_RULE as update_rule,
                rc.DELETE_RULE as delete_rule
            FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu1
                ON rc.CONSTRAINT_NAME = kcu1.CONSTRAINT_NAME
                AND rc.CONSTRAINT_SCHEMA = kcu1.CONSTRAINT_SCHEMA
                AND rc.CONSTRAINT_CATALOG = kcu1.CONSTRAINT_CATALOG
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
                ON rc.UNIQUE_CONSTRAINT_NAME = kcu2.CONSTRAINT_NAME
                AND rc.UNIQUE_CONSTRAINT_SCHEMA = kcu2.CONSTRAINT_SCHEMA
                AND rc.UNIQUE_CONSTRAINT_CATALOG = kcu2.CONSTRAINT_CATALOG
            WHERE rc.CONSTRAINT_CATALOG = ?
                AND rc.CONSTRAINT_SCHEMA = ?
            ORDER BY source_table, constraint_name
        """

        result = await self.execute_query(
            persona_id,
            credentials,
            query,
            params=[db_name.upper(), schema_name.upper()],
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

        Snowflake supports three-level naming: database.schema.table

        Args:
            identifier: Identifier to validate

        Returns:
            True if valid, False otherwise
        """
        import re
        # Allow alphanumeric, underscore, dot (for database.schema.table)
        # Can have up to 3 parts separated by dots
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*){0,2}$'
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
        snowflake_credentials = {**credentials, "db_type": "snowflake"}
        cache_key = self.pool_manager._generate_cache_key(persona_id, snowflake_credentials)
        await self.pool_manager._destroy_pool(cache_key)
        logger.info(f"❄️ Closed connection pool for persona {persona_id}")


# Global Snowflake connector instance
snowflake_connector = SnowflakeConnector()
