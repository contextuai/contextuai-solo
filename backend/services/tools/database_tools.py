"""
Database operation tools for Strands Agent.
Provides NLP-to-SQL query capabilities, schema introspection, and database operations.
"""

import os
import logging
import json
import hashlib
from typing import Dict, Any, Optional, List
from strands.tools import tool

from services.postgres_connector import postgres_connector
from services.mysql_connector import mysql_connector
from services.mssql_connector import mssql_connector
from services.snowflake_connector import snowflake_connector
from services.database_metadata_service import db_metadata_service
from services.nlp_to_sql_parser import nlp_to_sql_parser
from services.terminology_manager import terminology_manager
from services.query_cache_service import query_cache_service

logger = logging.getLogger(__name__)


class DatabaseTools:
    """
    Database operation tools for personas with NLP-to-SQL and schema introspection capabilities.

    Features:
    - Natural language to SQL query conversion
    - Schema introspection and metadata
    - Table analysis and statistics
    - Query execution plan analysis
    - Relationship mapping
    """

    def __init__(self, persona_id: str, credentials: Dict[str, Any]):
        """
        Initialize database tools with persona credentials.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
        """
        self.persona_id = persona_id
        self.credentials = credentials
        self.environment = os.getenv("ENVIRONMENT", "dev")
        self.db_type = credentials.get("db_type", "postgresql").lower()

        logger.info(f"DatabaseTools initialized for persona {persona_id}, db_type: {self.db_type}")

    def get_tools(self):
        """Return all database operation tools as a list for Strands Agent."""
        return [
            self.query_database,
            self.get_schema_info,
            self.analyze_table,
            self.explain_query,
            self.get_relationships,
            self.test_connection,
            self.get_table_sample
        ]

    @tool
    async def query_database(
        self,
        query: str,
        natural_language: Optional[str] = None,
        timeout: Optional[int] = None,
        row_limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a SQL query against the database. Can accept either SQL directly or natural language.

        For natural language queries, the system will:
        1. Load database schema
        2. Convert natural language to SQL
        3. Execute the query
        4. Return results

        Args:
            query: SQL query to execute (if natural_language not provided)
            natural_language: Natural language query to convert to SQL (optional)
            timeout: Query timeout in seconds (default: 30s)
            row_limit: Maximum rows to return (default: 1000)

        Returns:
            Dictionary with query results:
            {
                "success": bool,
                "query_type": "sql" | "natural_language",
                "sql_query": str,
                "natural_language_input": Optional[str],
                "rows": List[Dict],
                "row_count": int,
                "columns": List[str],
                "execution_time_ms": float,
                "error": Optional[str]
            }
        """
        try:
            # Determine if we're processing natural language or direct SQL
            if natural_language:
                logger.info(f"Processing natural language query: {natural_language}")

                # Load business terms for better NLP-to-SQL accuracy
                business_terms = {}
                try:
                    business_terms = await terminology_manager.get_terms_as_dict(self.persona_id)
                except Exception as term_err:
                    logger.warning(f"Failed to load business terms: {term_err}")

                # Convert natural language to SQL via NLP parser
                parse_result = await nlp_to_sql_parser.parse_to_sql(
                    natural_language_query=natural_language,
                    persona_id=self.persona_id,
                    credentials=self.credentials,
                    business_terms=business_terms or None,
                )

                if parse_result.get("success") and parse_result.get("sql"):
                    sql_query = parse_result["sql"]
                    logger.info(
                        f"NLP-to-SQL generated (confidence={parse_result.get('confidence', 'N/A')}): "
                        f"{sql_query[:200]}"
                    )
                else:
                    # Fall back to provided query if NLP parsing fails
                    sql_query = query
                    logger.warning(
                        f"NLP-to-SQL failed ({parse_result.get('error', 'unknown')}), "
                        "using provided SQL query directly."
                    )

                query_type = "natural_language"
                nl_input = natural_language
            else:
                sql_query = query
                query_type = "sql"
                nl_input = None

            # Check query cache before executing
            query_hash = hashlib.sha256(f"{self.persona_id}:{sql_query}".encode()).hexdigest()
            try:
                cached = await query_cache_service.get_cached_result(self.persona_id, query_hash)
                if cached:
                    logger.info(f"Query cache hit for hash {query_hash[:12]}")
                    return {
                        "success": True,
                        "query_type": query_type,
                        "sql_query": sql_query,
                        "natural_language_input": nl_input,
                        "rows": cached.get("data", []),
                        "row_count": len(cached.get("data", [])),
                        "columns": cached.get("columns", []),
                        "execution_time_ms": 0.0,
                        "cache_hit": True,
                    }
            except Exception as cache_err:
                logger.debug(f"Cache lookup failed (non-fatal): {cache_err}")

            # Execute query based on database type
            if self.db_type == "postgresql":
                result = await postgres_connector.execute_query(
                    self.persona_id,
                    self.credentials,
                    sql_query,
                    timeout=timeout,
                    row_limit=row_limit
                )
            elif self.db_type == "mysql":
                result = await mysql_connector.execute_query(
                    self.persona_id,
                    self.credentials,
                    sql_query,
                    timeout=timeout,
                    row_limit=row_limit
                )
            elif self.db_type in ("mssql", "sqlserver"):
                result = await mssql_connector.execute_query(
                    self.persona_id,
                    self.credentials,
                    sql_query,
                    timeout=timeout,
                    row_limit=row_limit
                )
            elif self.db_type == "snowflake":
                result = await snowflake_connector.execute_query(
                    self.persona_id,
                    self.credentials,
                    sql_query,
                    timeout=timeout,
                    row_limit=row_limit
                )
            else:
                return {
                    "success": False,
                    "error": f"Database type '{self.db_type}' not yet supported. Currently supports: postgresql, mysql, mssql, snowflake",
                    "query_type": query_type,
                    "sql_query": sql_query,
                    "natural_language_input": nl_input
                }

            # Enhance result with query metadata
            result["query_type"] = query_type
            result["sql_query"] = sql_query
            result["natural_language_input"] = nl_input
            result["cache_hit"] = False

            if result["success"]:
                logger.info(
                    f"Query executed successfully: {result['row_count']} rows "
                    f"in {result['execution_time_ms']:.2f}ms"
                )
                # Store result in cache for future requests
                try:
                    await query_cache_service.cache_result(
                        persona_id=self.persona_id,
                        query_hash=query_hash,
                        query=sql_query,
                        data=result.get("rows", []),
                        columns=result.get("columns", []),
                    )
                except Exception as cache_err:
                    logger.debug(f"Cache store failed (non-fatal): {cache_err}")
            else:
                logger.error(f"Query execution failed: {result.get('error')}")

            return result

        except Exception as e:
            logger.error(f"Error in query_database: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Query execution failed: {str(e)}",
                "query_type": query_type if 'query_type' in locals() else "unknown",
                "sql_query": sql_query if 'sql_query' in locals() else query,
                "natural_language_input": nl_input if 'nl_input' in locals() else natural_language,
                "rows": [],
                "row_count": 0,
                "columns": []
            }

    @tool
    async def get_schema_info(
        self,
        include_sample_data: bool = False,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Get cached schema information for the database.

        Returns comprehensive schema metadata including:
        - Table list with column details
        - Primary keys and indexes
        - Foreign key relationships
        - Data types and constraints

        Uses three-tier caching (memory -> DynamoDB -> database) for performance.

        Args:
            include_sample_data: Include sample data for each table (default: False)
            force_refresh: Force refresh from database, bypassing cache (default: False)

        Returns:
            Dictionary with schema information:
            {
                "success": bool,
                "database": str,
                "db_type": str,
                "schema_version": str,
                "tables": List[TableMetadata],
                "table_count": int,
                "cached_at": str,
                "expires_at": str,
                "sample_data": Optional[Dict[str, List[Dict]]],
                "error": Optional[str]
            }
        """
        try:
            logger.info(f"Retrieving schema info for persona {self.persona_id}")

            # Get schema metadata from cache or database
            schema_metadata = await db_metadata_service.get_schema_metadata(
                self.persona_id,
                self.credentials,
                force_refresh=force_refresh
            )

            # Add sample data if requested
            if include_sample_data and schema_metadata.get("tables"):
                sample_data = {}
                for table in schema_metadata["tables"][:10]:  # Limit to first 10 tables
                    table_name = table["table_name"]
                    schema = table.get("schema", "public")
                    full_table_name = f"{schema}.{table_name}"

                    sample_result = await self.get_table_sample(
                        table_name=full_table_name,
                        sample_size=5
                    )

                    if sample_result["success"]:
                        sample_data[full_table_name] = sample_result["rows"]

                schema_metadata["sample_data"] = sample_data

            schema_metadata["success"] = True
            logger.info(
                f"Schema info retrieved: {schema_metadata.get('table_count', 0)} tables, "
                f"version {schema_metadata.get('schema_version', 'unknown')}"
            )

            return schema_metadata

        except Exception as e:
            logger.error(f"Error getting schema info: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to retrieve schema information: {str(e)}",
                "database": self.credentials.get("database", ""),
                "db_type": self.db_type,
                "tables": [],
                "table_count": 0
            }

    @tool
    async def analyze_table(
        self,
        table_name: str,
        include_sample: bool = True,
        sample_size: int = 10
    ) -> Dict[str, Any]:
        """
        Analyze a specific table and return statistics and metadata.

        Provides:
        - Column metadata (names, types, constraints)
        - Index information
        - Primary and foreign keys
        - Row count estimate
        - Sample data (optional)

        Args:
            table_name: Name of table to analyze (can include schema: schema.table)
            include_sample: Include sample rows (default: True)
            sample_size: Number of sample rows to include (default: 10)

        Returns:
            Dictionary with table analysis:
            {
                "success": bool,
                "table_name": str,
                "schema": str,
                "columns": List[ColumnMetadata],
                "primary_keys": List[str],
                "indexes": List[IndexMetadata],
                "foreign_keys": List[ForeignKeyMetadata],
                "row_count_estimate": int,
                "sample_data": Optional[List[Dict]],
                "error": Optional[str]
            }
        """
        try:
            logger.info(f"Analyzing table: {table_name}")

            # Get full schema metadata
            schema_metadata = await db_metadata_service.get_schema_metadata(
                self.persona_id,
                self.credentials
            )

            # Parse table name (handle schema.table format)
            if "." in table_name:
                schema_name, table_only = table_name.split(".", 1)
            else:
                schema_name = "public"
                table_only = table_name

            # Find the table in schema metadata
            table_meta = None
            for table in schema_metadata.get("tables", []):
                if (table["table_name"] == table_only and
                    table.get("schema", "public") == schema_name):
                    table_meta = table
                    break

            if not table_meta:
                return {
                    "success": False,
                    "error": f"Table '{table_name}' not found in schema",
                    "table_name": table_name
                }

            # Get foreign keys from relationships
            foreign_keys = []
            for rel in schema_metadata.get("relationships", []):
                if (rel["source_table"] == table_only and
                    rel.get("source_schema", "public") == schema_name):
                    foreign_keys.append({
                        "constraint_name": rel["constraint_name"],
                        "column": rel["source_column"],
                        "referenced_table": rel["target_table"],
                        "referenced_schema": rel.get("target_schema", "public"),
                        "referenced_column": rel["target_column"]
                    })

            result = {
                "success": True,
                "table_name": table_only,
                "schema": schema_name,
                "columns": table_meta.get("columns", []),
                "primary_keys": table_meta.get("primary_keys", []),
                "indexes": table_meta.get("indexes", []),
                "foreign_keys": foreign_keys,
                "row_count_estimate": table_meta.get("row_count_estimate", 0),
                "table_type": table_meta.get("table_type", "BASE TABLE")
            }

            # Add sample data if requested
            if include_sample:
                sample_result = await self.get_table_sample(
                    table_name=table_name,
                    sample_size=sample_size
                )

                if sample_result["success"]:
                    result["sample_data"] = sample_result["rows"]
                    result["sample_count"] = sample_result["row_count"]

            logger.info(
                f"Table analysis complete: {len(result['columns'])} columns, "
                f"{len(result['indexes'])} indexes, {len(foreign_keys)} foreign keys"
            )

            return result

        except Exception as e:
            logger.error(f"Error analyzing table {table_name}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Table analysis failed: {str(e)}",
                "table_name": table_name
            }

    @tool
    async def explain_query(
        self,
        query: str
    ) -> Dict[str, Any]:
        """
        Get the execution plan for a SQL query without executing it.

        Useful for:
        - Understanding query performance
        - Identifying missing indexes
        - Optimizing complex queries
        - Estimating query cost

        Args:
            query: SQL query to explain

        Returns:
            Dictionary with query execution plan:
            {
                "success": bool,
                "query": str,
                "execution_plan": str,
                "estimated_cost": Optional[float],
                "estimated_rows": Optional[int],
                "analysis": Optional[str],
                "error": Optional[str]
            }
        """
        try:
            logger.info(f"Explaining query execution plan")

            if self.db_type == "postgresql":
                # Use EXPLAIN with JSON format for PostgreSQL
                explain_query = f"EXPLAIN (FORMAT JSON, VERBOSE, BUFFERS) {query}"

                result = await postgres_connector.execute_query(
                    self.persona_id,
                    self.credentials,
                    explain_query,
                    timeout=10,
                    row_limit=1
                )

                if not result["success"]:
                    return {
                        "success": False,
                        "error": f"EXPLAIN failed: {result.get('error')}",
                        "query": query
                    }

                # Parse execution plan
                if result["rows"] and len(result["rows"]) > 0:
                    plan_json = result["rows"][0].get("QUERY PLAN", {})

                    # Extract key metrics if available
                    if isinstance(plan_json, list) and len(plan_json) > 0:
                        plan_data = plan_json[0].get("Plan", {})

                        return {
                            "success": True,
                            "query": query,
                            "execution_plan": json.dumps(plan_json, indent=2),
                            "estimated_cost": plan_data.get("Total Cost"),
                            "estimated_rows": plan_data.get("Plan Rows"),
                            "node_type": plan_data.get("Node Type"),
                            "analysis": self._analyze_execution_plan(plan_data)
                        }

                return {
                    "success": True,
                    "query": query,
                    "execution_plan": str(result["rows"]),
                    "analysis": "Execution plan retrieved"
                }

            elif self.db_type == "mysql":
                # Use MySQL's EXPLAIN with JSON format
                result = await mysql_connector.explain_query(
                    self.persona_id,
                    self.credentials,
                    query
                )

                if result["success"]:
                    return {
                        "success": True,
                        "query": query,
                        "execution_plan": json.dumps(result.get("explain", {}), indent=2) if isinstance(result.get("explain"), dict) else str(result.get("explain", [])),
                        "format": result.get("format", "json"),
                        "analysis": self._analyze_mysql_execution_plan(result.get("explain", {}))
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("error", "EXPLAIN failed"),
                        "query": query
                    }

            elif self.db_type in ("mssql", "sqlserver"):
                result = await mssql_connector.explain_query(
                    self.persona_id,
                    self.credentials,
                    query
                )

                if result["success"]:
                    return {
                        "success": True,
                        "query": query,
                        "execution_plan": str(result.get("explain", [])),
                        "format": result.get("format", "xml"),
                        "analysis": self._analyze_mssql_execution_plan(result.get("explain", []))
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("error", "EXPLAIN failed"),
                        "query": query
                    }

            elif self.db_type == "snowflake":
                result = await snowflake_connector.explain_query(
                    self.persona_id,
                    self.credentials,
                    query
                )

                if result["success"]:
                    return {
                        "success": True,
                        "query": query,
                        "execution_plan": str(result.get("explain", [])),
                        "format": result.get("format", "tabular"),
                        "analysis": "Snowflake execution plan retrieved"
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("error", "EXPLAIN failed"),
                        "query": query
                    }

            else:
                return {
                    "success": False,
                    "error": f"EXPLAIN not yet supported for database type: {self.db_type}",
                    "query": query
                }

        except Exception as e:
            logger.error(f"Error explaining query: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Query explain failed: {str(e)}",
                "query": query
            }

    def _analyze_execution_plan(self, plan: Dict[str, Any]) -> str:
        """
        Analyze execution plan and provide optimization suggestions.

        Args:
            plan: Execution plan data

        Returns:
            Analysis text with suggestions
        """
        analysis = []

        # Check for sequential scans on large tables
        if plan.get("Node Type") == "Seq Scan":
            rows = plan.get("Plan Rows", 0)
            if rows > 1000:
                analysis.append(
                    f"Sequential scan detected on {rows} rows. "
                    "Consider adding an index to improve performance."
                )

        # Check for high cost
        cost = plan.get("Total Cost", 0)
        if cost > 10000:
            analysis.append(
                f"High query cost detected ({cost:.2f}). "
                "Consider optimizing joins or adding indexes."
            )

        # Check for nested loops on large datasets
        if plan.get("Node Type") == "Nested Loop":
            rows = plan.get("Plan Rows", 0)
            if rows > 100:
                analysis.append(
                    "Nested loop join on large dataset. "
                    "Consider using hash join or merge join instead."
                )

        return " ".join(analysis) if analysis else "Query plan looks reasonable."

    def _analyze_mysql_execution_plan(self, plan: Dict[str, Any]) -> str:
        """
        Analyze MySQL execution plan and provide optimization suggestions.

        Args:
            plan: MySQL execution plan data (JSON format)

        Returns:
            Analysis text with suggestions
        """
        analysis = []

        if not plan:
            return "Unable to analyze execution plan."

        # MySQL JSON EXPLAIN structure
        query_block = plan.get("query_block", {})
        select_id = query_block.get("select_id", 1)

        # Check for table scans
        if "table" in query_block:
            table_info = query_block["table"]
            access_type = table_info.get("access_type", "")
            rows_examined = table_info.get("rows_examined_per_scan", 0)

            if access_type == "ALL":
                analysis.append(
                    f"Full table scan detected on '{table_info.get('table_name', 'unknown')}' "
                    f"({rows_examined} rows). Consider adding an index."
                )
            elif access_type in ("index", "range"):
                analysis.append(
                    f"Index {access_type} access on '{table_info.get('table_name', 'unknown')}' "
                    f"using key '{table_info.get('key', 'unknown')}'."
                )

        # Check for filesort
        if query_block.get("filesort", False):
            analysis.append(
                "Filesort operation detected. Consider optimizing ORDER BY clause "
                "or adding an appropriate index."
            )

        # Check for temporary table
        if query_block.get("temporary_table", False):
            analysis.append(
                "Temporary table used. Consider optimizing GROUP BY or DISTINCT clauses."
            )

        # Check nested loop joins
        nested_loop = query_block.get("nested_loop", [])
        if len(nested_loop) > 2:
            analysis.append(
                f"Multiple nested loop joins detected ({len(nested_loop)} tables). "
                "Consider reviewing join order and indexes."
            )

        return " ".join(analysis) if analysis else "Query plan looks reasonable."

    def _analyze_mssql_execution_plan(self, plan: Any) -> str:
        """
        Analyze MSSQL execution plan and provide optimization suggestions.

        Args:
            plan: MSSQL execution plan data (XML or profile format)

        Returns:
            Analysis text with suggestions
        """
        analysis = []

        if not plan:
            return "Unable to analyze execution plan."

        # Basic analysis for MSSQL plans
        plan_str = str(plan)

        # Check for table scans
        if "Table Scan" in plan_str or "Clustered Index Scan" in plan_str:
            analysis.append(
                "Table or index scan detected. Consider adding appropriate indexes "
                "to improve query performance."
            )

        # Check for key lookups
        if "Key Lookup" in plan_str:
            analysis.append(
                "Key lookup detected. Consider creating a covering index to "
                "eliminate the lookup operation."
            )

        # Check for sorts
        if "Sort" in plan_str:
            analysis.append(
                "Sort operation detected. Consider adding an index that matches "
                "your ORDER BY clause to eliminate sorting."
            )

        # Check for hash joins
        if "Hash Match" in plan_str:
            analysis.append(
                "Hash match join detected. For large datasets, ensure statistics "
                "are up to date and consider indexing join columns."
            )

        return " ".join(analysis) if analysis else "Query plan looks reasonable."

    @tool
    async def get_relationships(
        self,
        table_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get foreign key relationships for the database or a specific table.

        Useful for:
        - Understanding data model structure
        - Building complex joins
        - Data modeling and ERD generation
        - Referential integrity validation

        Args:
            table_name: Optional table name to filter relationships (default: all)

        Returns:
            Dictionary with relationship information:
            {
                "success": bool,
                "relationships": List[RelationshipMetadata],
                "relationship_count": int,
                "tables_involved": List[str],
                "error": Optional[str]
            }
        """
        try:
            logger.info(
                f"Retrieving relationships" +
                (f" for table {table_name}" if table_name else " for entire database")
            )

            # Get schema metadata
            schema_metadata = await db_metadata_service.get_schema_metadata(
                self.persona_id,
                self.credentials
            )

            relationships = schema_metadata.get("relationships", [])

            # Filter by table if specified
            if table_name:
                # Parse table name
                if "." in table_name:
                    schema_name, table_only = table_name.split(".", 1)
                else:
                    schema_name = "public"
                    table_only = table_name

                # Filter relationships where table is source or target
                filtered_relationships = [
                    rel for rel in relationships
                    if (
                        (rel["source_table"] == table_only and
                         rel.get("source_schema", "public") == schema_name) or
                        (rel["target_table"] == table_only and
                         rel.get("target_schema", "public") == schema_name)
                    )
                ]
                relationships = filtered_relationships

            # Get unique tables involved
            tables_involved = set()
            for rel in relationships:
                source_table = f"{rel.get('source_schema', 'public')}.{rel['source_table']}"
                target_table = f"{rel.get('target_schema', 'public')}.{rel['target_table']}"
                tables_involved.add(source_table)
                tables_involved.add(target_table)

            logger.info(
                f"Found {len(relationships)} relationships "
                f"involving {len(tables_involved)} tables"
            )

            return {
                "success": True,
                "relationships": relationships,
                "relationship_count": len(relationships),
                "tables_involved": sorted(list(tables_involved)),
                "filter_table": table_name
            }

        except Exception as e:
            logger.error(f"Error getting relationships: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to retrieve relationships: {str(e)}",
                "relationships": [],
                "relationship_count": 0,
                "tables_involved": []
            }

    @tool
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test database connection health and get connection metrics.

        Useful for:
        - Verifying database connectivity
        - Monitoring connection performance
        - Troubleshooting connection issues
        - Health checks

        Returns:
            Dictionary with connection test results:
            {
                "success": bool,
                "response_time_ms": float,
                "database_version": str,
                "connection_pool_size": int,
                "idle_connections": int,
                "error": Optional[str]
            }
        """
        try:
            logger.info(f"Testing database connection for persona {self.persona_id}")

            if self.db_type == "postgresql":
                result = await postgres_connector.test_connection(
                    self.persona_id,
                    self.credentials
                )
            elif self.db_type == "mysql":
                result = await mysql_connector.test_connection(
                    self.persona_id,
                    self.credentials
                )
            elif self.db_type in ("mssql", "sqlserver"):
                result = await mssql_connector.test_connection(
                    self.persona_id,
                    self.credentials
                )
            elif self.db_type == "snowflake":
                result = await snowflake_connector.test_connection(
                    self.persona_id,
                    self.credentials
                )
            else:
                return {
                    "success": False,
                    "error": f"Connection test not yet supported for: {self.db_type}"
                }

            if result["success"]:
                logger.info(
                    f"Connection test successful: {result['response_time_ms']:.2f}ms, "
                    f"pool size: {result.get('connection_pool_size', result.get('free_connections', 'N/A'))}"
                )
            else:
                logger.error(f"Connection test failed: {result.get('error')}")

            return result

        except Exception as e:
            logger.error(f"Error testing connection: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Connection test failed: {str(e)}"
            }

    @tool
    async def get_table_sample(
        self,
        table_name: str,
        sample_size: int = 10
    ) -> Dict[str, Any]:
        """
        Get sample rows from a table.

        Useful for:
        - Understanding table data structure
        - Previewing table contents
        - Data exploration
        - Testing queries

        Args:
            table_name: Name of table to sample (can include schema: schema.table)
            sample_size: Number of rows to return (default: 10, max: 100)

        Returns:
            Dictionary with sample data:
            {
                "success": bool,
                "table_name": str,
                "rows": List[Dict],
                "row_count": int,
                "columns": List[str],
                "error": Optional[str]
            }
        """
        try:
            # Enforce maximum sample size
            sample_size = min(sample_size, 100)

            logger.info(f"Getting {sample_size} sample rows from table: {table_name}")

            if self.db_type == "postgresql":
                result = await postgres_connector.get_table_sample(
                    self.persona_id,
                    self.credentials,
                    table_name,
                    sample_size
                )
            elif self.db_type == "mysql":
                result = await mysql_connector.get_table_sample(
                    self.persona_id,
                    self.credentials,
                    table_name,
                    sample_size
                )
            elif self.db_type in ("mssql", "sqlserver"):
                result = await mssql_connector.get_table_sample(
                    self.persona_id,
                    self.credentials,
                    table_name,
                    sample_size
                )
            elif self.db_type == "snowflake":
                result = await snowflake_connector.get_table_sample(
                    self.persona_id,
                    self.credentials,
                    table_name,
                    sample_size
                )
            else:
                return {
                    "success": False,
                    "error": f"Table sampling not yet supported for: {self.db_type}",
                    "table_name": table_name
                }

            result["table_name"] = table_name

            if result["success"]:
                logger.info(
                    f"Retrieved {result['row_count']} sample rows "
                    f"with {len(result.get('columns', []))} columns"
                )

            return result

        except Exception as e:
            logger.error(f"Error getting table sample: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to get table sample: {str(e)}",
                "table_name": table_name,
                "rows": [],
                "row_count": 0,
                "columns": []
            }
