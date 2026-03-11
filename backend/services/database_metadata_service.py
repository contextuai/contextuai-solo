"""
Database Metadata Service
Provides schema introspection, metadata extraction, and caching for database connectors.
Supports PostgreSQL with extensible architecture for MySQL and MSSQL.
"""

import time
import json
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError

from config.database_config import get_cache_config
from services.postgres_connector import postgres_connector
from services.mysql_connector import mysql_connector
from services.mssql_connector import mssql_connector
from services.snowflake_connector import snowflake_connector

logger = logging.getLogger(__name__)


class DatabaseMetadataService:
    """
    Database schema introspection and metadata management service.

    Features:
    - Schema introspection for PostgreSQL (MySQL/MSSQL extensible)
    - Table and column metadata extraction
    - Foreign key relationship mapping
    - Index information gathering
    - Three-tier caching (memory, DynamoDB, database)
    - Schema versioning and refresh
    """

    def __init__(self):
        """Initialize database metadata service"""
        self.cache_config = get_cache_config("schema")
        self._dynamodb = None  # Lazy initialization
        self._dynamodb_available = None  # Track if DynamoDB is available
        self.environment = self._get_environment()

        # DynamoDB table for schema cache
        self.metadata_table_name = f"contextuai-backend-db-metadata-{self.environment}"

        # In-memory cache
        self.memory_cache: Dict[str, Dict[str, Any]] = {}
        self.memory_cache_timestamps: Dict[str, float] = {}

    @property
    def dynamodb(self):
        """Lazy initialization of DynamoDB resource with region fallback."""
        if self._dynamodb is None and self._dynamodb_available is not False:
            try:
                import os
                region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
                self._dynamodb = boto3.resource('dynamodb', region_name=region)
                self._dynamodb_available = True
                logger.debug(f"DynamoDB resource initialized with region: {region}")
            except Exception as e:
                logger.warning(f"DynamoDB not available: {e}. Schema caching will use memory only.")
                self._dynamodb_available = False
        return self._dynamodb

    def _get_environment(self) -> str:
        """Get current environment from env vars"""
        import os
        return os.getenv("ENVIRONMENT", "dev")

    async def get_schema_metadata(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Get complete schema metadata for a database.

        Three-tier caching strategy:
        1. Check memory cache (10-30 min TTL)
        2. Check DynamoDB cache (30 min - 2 hour TTL)
        3. Query database and cache results

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials
            force_refresh: Force refresh from database

        Returns:
            Schema metadata dictionary:
            {
                "persona_id": str,
                "database": str,
                "schema_version": str,
                "tables": List[TableMetadata],
                "relationships": List[RelationshipMetadata],
                "cached_at": str,
                "expires_at": str
            }
        """
        cache_key = self._generate_cache_key(persona_id, credentials)

        # Check memory cache first
        if not force_refresh:
            cached = self._get_from_memory_cache(cache_key)
            if cached:
                logger.debug(f"Schema metadata retrieved from memory cache: {cache_key}")
                return cached

            # Check DynamoDB cache
            cached = await self._get_from_dynamodb_cache(cache_key)
            if cached:
                logger.debug(f"Schema metadata retrieved from DynamoDB cache: {cache_key}")
                # Store in memory cache
                self._store_in_memory_cache(cache_key, cached)
                return cached

        # Cache miss - introspect database
        logger.info(f"Schema cache miss, introspecting database: {cache_key}")
        metadata = await self._introspect_database(persona_id, credentials)

        # Store in caches
        self._store_in_memory_cache(cache_key, metadata)
        await self._store_in_dynamodb_cache(cache_key, metadata)

        return metadata

    async def _introspect_database(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Introspect database to extract schema metadata.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials

        Returns:
            Complete schema metadata
        """
        db_type = credentials.get("db_type", "postgresql").lower()

        if db_type == "postgresql":
            return await self._introspect_postgresql(persona_id, credentials)
        elif db_type == "mysql":
            return await self._introspect_mysql(persona_id, credentials)
        elif db_type == "mssql":
            return await self._introspect_mssql(persona_id, credentials)
        elif db_type == "snowflake":
            return await self._introspect_snowflake(persona_id, credentials)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    async def _introspect_postgresql(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Introspect PostgreSQL database schema.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials

        Returns:
            PostgreSQL schema metadata
        """
        # Get table list
        tables = await self._get_postgresql_tables(persona_id, credentials)

        # Get detailed metadata for each table
        table_metadata = []
        for table in tables:
            schema = table.get("schema", "public")
            table_name = table["table_name"]

            # Get columns
            columns = await self._get_postgresql_columns(
                persona_id, credentials, schema, table_name
            )

            # Get indexes
            indexes = await self._get_postgresql_indexes(
                persona_id, credentials, schema, table_name
            )

            # Get primary keys
            primary_keys = await self._get_postgresql_primary_keys(
                persona_id, credentials, schema, table_name
            )

            table_metadata.append({
                "schema": schema,
                "table_name": table_name,
                "table_type": table.get("table_type", "BASE TABLE"),
                "columns": columns,
                "indexes": indexes,
                "primary_keys": primary_keys,
                "row_count_estimate": table.get("row_count", 0)
            })

        # Get foreign key relationships
        relationships = await self._get_postgresql_relationships(persona_id, credentials)

        # Generate schema version hash
        schema_version = self._generate_schema_version(table_metadata)

        # Calculate cache expiry
        ttl_seconds = self.cache_config["schema_cache_ttl"]
        cached_at = datetime.utcnow()
        expires_at = cached_at + timedelta(seconds=ttl_seconds)

        return {
            "persona_id": persona_id,
            "database": credentials.get("database", ""),
            "db_type": "postgresql",
            "schema_version": schema_version,
            "tables": table_metadata,
            "relationships": relationships,
            "cached_at": cached_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "table_count": len(table_metadata)
        }

    async def _get_postgresql_tables(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get list of tables from PostgreSQL database"""
        query = """
        SELECT
            schemaname as schema,
            tablename as table_name,
            'BASE TABLE' as table_type,
            n_live_tup as row_count
        FROM pg_stat_user_tables
        ORDER BY schemaname, tablename
        """

        result = await postgres_connector.execute_query(
            persona_id, credentials, query, row_limit=10000
        )

        return result.get("rows", [])

    async def _get_postgresql_columns(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        schema: str,
        table_name: str
    ) -> List[Dict[str, Any]]:
        """Get column metadata for PostgreSQL table"""
        query = """
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default,
            ordinal_position
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
        """

        result = await postgres_connector.execute_query(
            persona_id, credentials, query, params=[schema, table_name], row_limit=1000
        )

        columns = []
        for row in result.get("rows", []):
            columns.append({
                "column_name": row["column_name"],
                "data_type": row["data_type"],
                "max_length": row.get("character_maximum_length"),
                "nullable": row["is_nullable"] == "YES",
                "default_value": row.get("column_default"),
                "position": row["ordinal_position"]
            })

        return columns

    async def _get_postgresql_indexes(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        schema: str,
        table_name: str
    ) -> List[Dict[str, Any]]:
        """Get index metadata for PostgreSQL table"""
        query = """
        SELECT
            i.relname as index_name,
            a.attname as column_name,
            ix.indisunique as is_unique,
            ix.indisprimary as is_primary
        FROM pg_index ix
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = $1 AND t.relname = $2
        ORDER BY i.relname, a.attnum
        """

        result = await postgres_connector.execute_query(
            persona_id, credentials, query, params=[schema, table_name], row_limit=1000
        )

        # Group indexes by name
        indexes_dict = {}
        for row in result.get("rows", []):
            index_name = row["index_name"]
            if index_name not in indexes_dict:
                indexes_dict[index_name] = {
                    "index_name": index_name,
                    "columns": [],
                    "is_unique": row["is_unique"],
                    "is_primary": row["is_primary"]
                }
            indexes_dict[index_name]["columns"].append(row["column_name"])

        return list(indexes_dict.values())

    async def _get_postgresql_primary_keys(
        self,
        persona_id: str,
        credentials: Dict[str, Any],
        schema: str,
        table_name: str
    ) -> List[str]:
        """Get primary key columns for PostgreSQL table"""
        query = """
        SELECT a.attname as column_name
        FROM pg_index ix
        JOIN pg_class t ON t.oid = ix.indrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = $1 AND t.relname = $2 AND ix.indisprimary
        ORDER BY a.attnum
        """

        result = await postgres_connector.execute_query(
            persona_id, credentials, query, params=[schema, table_name], row_limit=100
        )

        return [row["column_name"] for row in result.get("rows", [])]

    async def _get_postgresql_relationships(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get foreign key relationships for PostgreSQL database"""
        query = """
        SELECT
            tc.table_schema as source_schema,
            tc.table_name as source_table,
            kcu.column_name as source_column,
            ccu.table_schema as target_schema,
            ccu.table_name as target_table,
            ccu.column_name as target_column,
            tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        ORDER BY tc.table_schema, tc.table_name
        """

        result = await postgres_connector.execute_query(
            persona_id, credentials, query, row_limit=10000
        )

        relationships = []
        for row in result.get("rows", []):
            relationships.append({
                "constraint_name": row["constraint_name"],
                "source_schema": row["source_schema"],
                "source_table": row["source_table"],
                "source_column": row["source_column"],
                "target_schema": row["target_schema"],
                "target_table": row["target_table"],
                "target_column": row["target_column"]
            })

        return relationships

    async def _introspect_mysql(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Introspect MySQL database schema.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials

        Returns:
            MySQL schema metadata
        """
        database = credentials.get("database", "")
        tables = []
        relationships = []

        try:
            # Get schema info using mysql_connector
            schema_result = await mysql_connector.get_schema_info(
                persona_id,
                credentials,
                database
            )

            if not schema_result.get("success"):
                logger.error(f"Failed to get MySQL schema info: {schema_result.get('error')}")
                return {
                    "persona_id": persona_id,
                    "database": database,
                    "db_type": "mysql",
                    "tables": [],
                    "relationships": [],
                    "cached_at": datetime.utcnow().isoformat(),
                    "error": schema_result.get("error", "Failed to introspect MySQL schema")
                }

            # Process tables
            for table_row in schema_result.get("tables", []):
                table_name = table_row.get("table_name")
                columns = schema_result.get("columns_by_table", {}).get(table_name, [])
                indexes = schema_result.get("indexes_by_table", {}).get(table_name, [])

                # Find primary keys from indexes
                primary_keys = []
                processed_indexes = []

                for idx in indexes:
                    if idx.get("index_name") == "PRIMARY":
                        primary_keys.append(idx.get("column_name"))
                    else:
                        processed_indexes.append({
                            "index_name": idx.get("index_name"),
                            "column_name": idx.get("column_name"),
                            "is_unique": idx.get("non_unique") == 0
                        })

                # Process columns
                processed_columns = []
                for col in columns:
                    processed_columns.append({
                        "column_name": col.get("column_name"),
                        "data_type": col.get("data_type"),
                        "column_type": col.get("column_type"),
                        "is_nullable": col.get("is_nullable") == "YES",
                        "column_default": col.get("column_default"),
                        "is_primary_key": col.get("column_name") in primary_keys,
                        "column_key": col.get("column_key"),
                        "extra": col.get("extra"),
                        "comment": col.get("column_comment")
                    })

                tables.append({
                    "schema": database,
                    "table_name": table_name,
                    "table_type": table_row.get("table_type", "BASE TABLE"),
                    "row_count_estimate": table_row.get("row_count", 0),
                    "data_length": table_row.get("data_length", 0),
                    "columns": processed_columns,
                    "primary_keys": primary_keys,
                    "indexes": processed_indexes,
                    "comment": table_row.get("table_comment")
                })

            # Process foreign keys
            for fk in schema_result.get("foreign_keys", []):
                relationships.append({
                    "constraint_name": fk.get("constraint_name"),
                    "source_schema": database,
                    "source_table": fk.get("source_table"),
                    "source_column": fk.get("source_column"),
                    "target_schema": fk.get("target_table", database),
                    "target_table": fk.get("target_table"),
                    "target_column": fk.get("target_column")
                })

            # Generate schema version
            schema_version = self._generate_schema_version(tables)

            # Calculate cache expiry
            cache_ttl = self.cache_config.get("dynamodb_cache_ttl", 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=cache_ttl)

            return {
                "persona_id": persona_id,
                "database": database,
                "db_type": "mysql",
                "schema_version": schema_version,
                "tables": tables,
                "relationships": relationships,
                "table_count": len(tables),
                "cached_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Error introspecting MySQL schema: {e}", exc_info=True)
            return {
                "persona_id": persona_id,
                "database": database,
                "db_type": "mysql",
                "tables": [],
                "relationships": [],
                "cached_at": datetime.utcnow().isoformat(),
                "error": f"MySQL introspection failed: {str(e)}"
            }

    async def _introspect_mssql(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Introspect MSSQL database schema.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials

        Returns:
            MSSQL schema metadata
        """
        database = credentials.get("database", "")
        tables = []
        relationships = []

        try:
            # Get schema info using mssql_connector
            schema_result = await mssql_connector.get_schema_info(
                persona_id,
                credentials,
                database
            )

            if not schema_result.get("success"):
                logger.error(f"Failed to get MSSQL schema info: {schema_result.get('error')}")
                return {
                    "persona_id": persona_id,
                    "database": database,
                    "db_type": "mssql",
                    "tables": [],
                    "relationships": [],
                    "cached_at": datetime.utcnow().isoformat(),
                    "error": schema_result.get("error", "Failed to introspect MSSQL schema")
                }

            # Process tables
            for table_row in schema_result.get("tables", []):
                table_name = table_row.get("table_name")
                table_schema = table_row.get("table_schema", "dbo")
                columns = schema_result.get("columns_by_table", {}).get(table_name, [])
                indexes = schema_result.get("indexes_by_table", {}).get(table_name, [])

                # Find primary keys from indexes
                primary_keys = []
                processed_indexes = []

                for idx in indexes:
                    if idx.get("is_primary_key"):
                        # Primary key index found - we'd need to join with sys.index_columns to get column names
                        # For now, mark that there is a primary key
                        pass
                    processed_indexes.append({
                        "index_name": idx.get("index_name"),
                        "index_type": idx.get("index_type"),
                        "is_unique": idx.get("is_unique"),
                        "is_primary": idx.get("is_primary_key")
                    })

                # Process columns
                processed_columns = []
                for col in columns:
                    processed_columns.append({
                        "column_name": col.get("column_name"),
                        "data_type": col.get("data_type"),
                        "max_length": col.get("max_length"),
                        "is_nullable": col.get("is_nullable") == "YES",
                        "column_default": col.get("column_default"),
                        "ordinal_position": col.get("ordinal_position")
                    })

                tables.append({
                    "schema": table_schema,
                    "table_name": table_name,
                    "table_type": table_row.get("table_type", "BASE TABLE"),
                    "columns": processed_columns,
                    "primary_keys": primary_keys,
                    "indexes": processed_indexes
                })

            # Process foreign keys
            for fk in schema_result.get("foreign_keys", []):
                relationships.append({
                    "constraint_name": fk.get("constraint_name"),
                    "source_schema": "dbo",  # MSSQL default schema
                    "source_table": fk.get("source_table"),
                    "source_column": fk.get("source_column"),
                    "target_schema": "dbo",
                    "target_table": fk.get("target_table"),
                    "target_column": fk.get("target_column")
                })

            # Generate schema version
            schema_version = self._generate_schema_version(tables)

            # Calculate cache expiry
            cache_ttl = self.cache_config.get("dynamodb_cache_ttl", 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=cache_ttl)

            return {
                "persona_id": persona_id,
                "database": database,
                "db_type": "mssql",
                "schema_version": schema_version,
                "tables": tables,
                "relationships": relationships,
                "table_count": len(tables),
                "cached_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Error introspecting MSSQL schema: {e}", exc_info=True)
            return {
                "persona_id": persona_id,
                "database": database,
                "db_type": "mssql",
                "tables": [],
                "relationships": [],
                "cached_at": datetime.utcnow().isoformat(),
                "error": f"MSSQL introspection failed: {str(e)}"
            }

    async def _introspect_snowflake(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Introspect Snowflake database schema.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials

        Returns:
            Snowflake schema metadata
        """
        database = credentials.get("database", "")
        schema = credentials.get("schema", "PUBLIC")
        tables = []
        relationships = []

        try:
            # Get schema info using snowflake_connector
            schema_result = await snowflake_connector.get_schema_info(
                persona_id,
                credentials,
                database,
                schema
            )

            if not schema_result.get("success"):
                logger.error(f"Failed to get Snowflake schema info: {schema_result.get('error')}")
                return {
                    "persona_id": persona_id,
                    "database": database,
                    "schema": schema,
                    "db_type": "snowflake",
                    "tables": [],
                    "relationships": [],
                    "cached_at": datetime.utcnow().isoformat(),
                    "error": schema_result.get("error", "Failed to introspect Snowflake schema")
                }

            # Process tables
            for table_row in schema_result.get("tables", []):
                table_name = table_row.get("table_name")
                table_schema = table_row.get("table_schema", schema)
                columns = schema_result.get("columns_by_table", {}).get(table_name, [])
                primary_keys_data = schema_result.get("primary_keys_by_table", {}).get(table_name, [])

                # Extract primary key column names
                primary_keys = [pk.get("column_name") for pk in primary_keys_data]

                # Process columns
                processed_columns = []
                for col in columns:
                    processed_columns.append({
                        "column_name": col.get("column_name"),
                        "data_type": col.get("data_type"),
                        "max_length": col.get("max_length"),
                        "numeric_precision": col.get("numeric_precision"),
                        "numeric_scale": col.get("numeric_scale"),
                        "is_nullable": col.get("is_nullable") == "YES",
                        "column_default": col.get("column_default"),
                        "ordinal_position": col.get("ordinal_position"),
                        "is_primary_key": col.get("column_name") in primary_keys,
                        "comment": col.get("column_comment")
                    })

                tables.append({
                    "schema": table_schema,
                    "table_name": table_name,
                    "table_type": table_row.get("table_type", "BASE TABLE"),
                    "table_catalog": table_row.get("table_catalog", database),
                    "row_count_estimate": table_row.get("row_count", 0),
                    "bytes": table_row.get("bytes", 0),
                    "columns": processed_columns,
                    "primary_keys": primary_keys,
                    "comment": table_row.get("table_comment")
                })

            # Process foreign keys
            for fk in schema_result.get("foreign_keys", []):
                relationships.append({
                    "constraint_name": fk.get("constraint_name"),
                    "source_schema": schema,
                    "source_table": fk.get("source_table"),
                    "source_column": fk.get("source_column"),
                    "target_schema": schema,
                    "target_table": fk.get("target_table"),
                    "target_column": fk.get("target_column"),
                    "update_rule": fk.get("update_rule"),
                    "delete_rule": fk.get("delete_rule")
                })

            # Generate schema version
            schema_version = self._generate_schema_version(tables)

            # Calculate cache expiry
            cache_ttl = self.cache_config.get("dynamodb_cache_ttl", 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=cache_ttl)

            return {
                "persona_id": persona_id,
                "database": database,
                "schema": schema,
                "db_type": "snowflake",
                "schema_version": schema_version,
                "tables": tables,
                "relationships": relationships,
                "table_count": len(tables),
                "cached_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Error introspecting Snowflake schema: {e}", exc_info=True)
            return {
                "persona_id": persona_id,
                "database": database,
                "schema": schema,
                "db_type": "snowflake",
                "tables": [],
                "relationships": [],
                "cached_at": datetime.utcnow().isoformat(),
                "error": f"Snowflake introspection failed: {str(e)}"
            }

    def _generate_schema_version(self, table_metadata: List[Dict[str, Any]]) -> str:
        """
        Generate schema version hash from table metadata.

        Args:
            table_metadata: List of table metadata dictionaries

        Returns:
            MD5 hash of schema structure
        """
        import hashlib

        # Create stable string representation of schema
        schema_str = json.dumps(table_metadata, sort_keys=True)
        return hashlib.md5(schema_str.encode()).hexdigest()[:16]

    def _generate_cache_key(self, persona_id: str, credentials: Dict[str, Any]) -> str:
        """Generate unique cache key for schema metadata"""
        import hashlib

        db_type = credentials.get("db_type", "postgresql")
        host = credentials.get("host", "")
        database = credentials.get("database", "")

        key_string = f"{persona_id}:{db_type}:{host}:{database}"
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

    def _get_from_memory_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get schema metadata from memory cache"""
        if cache_key not in self.memory_cache:
            return None

        # Check if cache is expired
        cached_at = self.memory_cache_timestamps.get(cache_key, 0)
        ttl = self.cache_config.get("memory_cache_ttl", 600)

        if time.time() - cached_at > ttl:
            # Cache expired
            del self.memory_cache[cache_key]
            del self.memory_cache_timestamps[cache_key]
            return None

        return self.memory_cache[cache_key]

    def _store_in_memory_cache(self, cache_key: str, metadata: Dict[str, Any]):
        """Store schema metadata in memory cache"""
        self.memory_cache[cache_key] = metadata
        self.memory_cache_timestamps[cache_key] = time.time()

        # Limit cache size
        max_items = self.cache_config.get("max_memory_cache_items", 100)
        if len(self.memory_cache) > max_items:
            # Remove oldest entries
            sorted_keys = sorted(
                self.memory_cache_timestamps.items(),
                key=lambda x: x[1]
            )
            for key, _ in sorted_keys[:len(sorted_keys) // 2]:
                del self.memory_cache[key]
                del self.memory_cache_timestamps[key]

    async def _get_from_dynamodb_cache(
        self,
        cache_key: str
    ) -> Optional[Dict[str, Any]]:
        """Get schema metadata from DynamoDB cache"""
        if not self.cache_config.get("enable_dynamodb_cache", True):
            return None

        # Check if DynamoDB is available
        if self.dynamodb is None:
            return None

        try:
            table = self.dynamodb.Table(self.metadata_table_name)
            response = table.get_item(Key={"cache_key": cache_key})

            if "Item" not in response:
                return None

            item = response["Item"]

            # Check if cache is expired
            expires_at = datetime.fromisoformat(item.get("expires_at", ""))
            if datetime.utcnow() > expires_at:
                # Cache expired, delete item
                table.delete_item(Key={"cache_key": cache_key})
                return None

            # Return cached metadata
            return json.loads(item["metadata"])

        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.warning(f"DynamoDB table not found: {self.metadata_table_name}")
            else:
                logger.error(f"Error reading from DynamoDB cache: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error reading from DynamoDB cache: {str(e)}")
            return None

    async def _store_in_dynamodb_cache(
        self,
        cache_key: str,
        metadata: Dict[str, Any]
    ):
        """Store schema metadata in DynamoDB cache"""
        if not self.cache_config.get("enable_dynamodb_cache", True):
            return

        # Check if DynamoDB is available
        if self.dynamodb is None:
            return

        try:
            table = self.dynamodb.Table(self.metadata_table_name)

            # Calculate TTL for DynamoDB item expiration
            ttl_seconds = self.cache_config["schema_cache_ttl"]
            ttl_timestamp = int(time.time() + ttl_seconds)

            # Compress metadata if configured
            metadata_json = json.dumps(metadata)
            if self.cache_config.get("cache_compression", False):
                import gzip
                import base64
                compressed = gzip.compress(metadata_json.encode())
                metadata_str = base64.b64encode(compressed).decode()
                is_compressed = True
            else:
                metadata_str = metadata_json
                is_compressed = False

            # Store in DynamoDB
            table.put_item(
                Item={
                    "cache_key": cache_key,
                    "persona_id": metadata.get("persona_id", ""),
                    "database": metadata.get("database", ""),
                    "db_type": metadata.get("db_type", ""),
                    "schema_version": metadata.get("schema_version", ""),
                    "metadata": metadata_str,
                    "is_compressed": is_compressed,
                    "cached_at": metadata.get("cached_at", ""),
                    "expires_at": metadata.get("expires_at", ""),
                    "ttl": ttl_timestamp,
                    "table_count": metadata.get("table_count", 0)
                }
            )

            logger.debug(f"Stored schema metadata in DynamoDB: {cache_key}")

        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.warning(f"DynamoDB table not found: {self.metadata_table_name}")
            else:
                logger.error(f"Error storing in DynamoDB cache: {str(e)}")
        except Exception as e:
            logger.error(f"Error storing in DynamoDB cache: {str(e)}")

    async def refresh_schema_cache(
        self,
        persona_id: str,
        credentials: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Force refresh of schema metadata cache.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials

        Returns:
            Refreshed schema metadata
        """
        logger.info(f"Force refreshing schema cache for persona {persona_id}")
        return await self.get_schema_metadata(persona_id, credentials, force_refresh=True)

    async def clear_cache(self, persona_id: Optional[str] = None):
        """
        Clear schema metadata cache.

        Args:
            persona_id: Optional persona ID to clear specific cache, otherwise clear all
        """
        if persona_id:
            # Clear specific persona cache
            keys_to_remove = [
                key for key in self.memory_cache.keys()
                if persona_id in key
            ]
            for key in keys_to_remove:
                del self.memory_cache[key]
                if key in self.memory_cache_timestamps:
                    del self.memory_cache_timestamps[key]

            logger.info(f"Cleared schema cache for persona {persona_id}")
        else:
            # Clear all cache
            self.memory_cache.clear()
            self.memory_cache_timestamps.clear()
            logger.info("Cleared all schema metadata cache")


# Global database metadata service instance
db_metadata_service = DatabaseMetadataService()
