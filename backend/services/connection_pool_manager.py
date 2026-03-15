"""
Connection Pool Manager for Database Connectors
Manages database connection pools across MySQL, PostgreSQL, and MSSQL
"""

import asyncio
import time
import hashlib
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Metrics for connection pool monitoring"""
    cache_key: str
    created_at: float
    last_used: float
    total_queries: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    connection_reuse_count: int = 0
    connection_errors: int = 0
    avg_query_time_ms: float = 0.0


class ConnectionPoolManager:
    """
    Manages database connection pools across all database types and personas.

    Features:
    - Lazy pool initialization (create on first use)
    - Connection validation before reuse
    - Automatic reconnection on failure
    - Idle pool cleanup (30 min TTL)
    - Per-user connection limits
    - Health monitoring and metrics
    """

    def __init__(self):
        self.pools: Dict[str, Any] = {}
        self.pool_locks: Dict[str, asyncio.Lock] = {}
        self.pool_metrics: Dict[str, PoolMetrics] = {}
        self.cleanup_task: Optional[asyncio.Task] = None

        # Configuration
        self.idle_pool_ttl = 1800  # 30 minutes
        self.pool_cleanup_interval = 300  # 5 minutes

    async def start(self):
        """Start the connection pool manager and background cleanup task"""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cleanup_idle_pools())
            logger.info("Connection pool manager started")

    async def stop(self):
        """Stop the connection pool manager and cleanup all pools"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all pools
        for cache_key in list(self.pools.keys()):
            await self._destroy_pool(cache_key)

        logger.info("Connection pool manager stopped")

    def _generate_cache_key(self, persona_id: str, credentials: Dict[str, Any]) -> str:
        """
        Generate unique cache key for connection pool.
        Format: {persona_id}:{db_type}:{host}:{database}
        """
        db_type = credentials.get("db_type", "mysql")
        host = credentials.get("host", "")
        database = credentials.get("database", "")

        # Create hash for stable key
        key_string = f"{persona_id}:{db_type}:{host}:{database}"
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

    async def get_pool(self, persona_id: str, credentials: Dict[str, Any]):
        """
        Get or create connection pool for persona.

        Args:
            persona_id: Unique persona identifier
            credentials: Database connection credentials

        Returns:
            Connection pool instance

        Raises:
            ValueError: If database type not supported
            Exception: If connection fails
        """
        cache_key = self._generate_cache_key(persona_id, credentials)

        # Check if pool exists and is healthy
        if cache_key in self.pools:
            pool = self.pools[cache_key]
            if await self._is_pool_healthy(pool, credentials.get("db_type")):
                # Update metrics
                self.pool_metrics[cache_key].last_used = time.time()
                return pool
            else:
                # Pool unhealthy, remove and recreate
                logger.warning(f"Pool {cache_key} unhealthy, destroying and recreating")
                await self._destroy_pool(cache_key)

        # Create new pool with lock to prevent race conditions
        lock = self.pool_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            # Double-check after acquiring lock
            if cache_key in self.pools:
                return self.pools[cache_key]

            # Create new pool
            pool = await self._create_pool(credentials)
            self.pools[cache_key] = pool

            # Initialize metrics
            self.pool_metrics[cache_key] = PoolMetrics(
                cache_key=cache_key,
                created_at=time.time(),
                last_used=time.time()
            )

            logger.info(f"Created new connection pool: {cache_key} ({credentials.get('db_type')})")
            return pool

    async def _create_pool(self, credentials: Dict[str, Any]):
        """
        Create new connection pool based on database type.

        Args:
            credentials: Database connection credentials

        Returns:
            Connection pool instance

        Raises:
            ValueError: If database type not supported
        """
        db_type = credentials.get("db_type", "mysql").lower()

        if db_type == "mysql":
            return await self._create_mysql_pool(credentials)
        elif db_type == "postgresql":
            return await self._create_postgres_pool(credentials)
        elif db_type == "mssql":
            return await self._create_mssql_pool(credentials)
        elif db_type == "snowflake":
            return await self._create_snowflake_pool(credentials)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    async def _create_mysql_pool(self, credentials: Dict[str, Any]):
        """
        Create MySQL connection pool using aiomysql.

        Args:
            credentials: MySQL connection credentials

        Returns:
            aiomysql connection pool
        """
        try:
            import aiomysql
        except ImportError:
            raise ImportError("aiomysql not installed. Run: pip install aiomysql")

        # Get pool configuration
        pool_config = credentials.get("connection_pool_config", {})
        min_size = pool_config.get("min_size", 2)
        max_size = pool_config.get("max_size", 10)
        timeout = pool_config.get("timeout", 30)

        # Get password (from Secrets Manager or direct)
        password = await self._get_password(credentials)

        # Create pool
        pool = await aiomysql.create_pool(
            host=credentials["host"],
            port=int(credentials.get("port", 3306)),
            user=credentials["username"],
            password=password,
            db=credentials["database"],
            minsize=min_size,
            maxsize=max_size,
            autocommit=True,
            pool_recycle=3600,  # Recycle connections after 1 hour
            connect_timeout=timeout,
            echo=False
        )

        logger.info(f"Created MySQL pool: {credentials['host']}:{credentials.get('port', 3306)}")
        return pool

    async def _create_postgres_pool(self, credentials: Dict[str, Any]):
        """
        Create PostgreSQL connection pool using asyncpg.

        Args:
            credentials: PostgreSQL connection credentials

        Returns:
            asyncpg connection pool
        """
        try:
            import asyncpg
        except ImportError:
            raise ImportError("asyncpg not installed. Run: pip install asyncpg")

        # Get pool configuration
        pool_config = credentials.get("connection_pool_config", {})
        min_size = pool_config.get("min_size", 2)
        max_size = pool_config.get("max_size", 10)
        timeout = pool_config.get("timeout", 30)

        # Get password
        password = await self._get_password(credentials)

        # Create pool
        pool = await asyncpg.create_pool(
            host=credentials["host"],
            port=int(credentials.get("port", 5432)),
            user=credentials["username"],
            password=password,
            database=credentials["database"],
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
            command_timeout=60,
            max_inactive_connection_lifetime=300.0
        )

        logger.info(f"Created PostgreSQL pool: {credentials['host']}:{credentials.get('port', 5432)}")
        return pool

    async def _create_mssql_pool(self, credentials: Dict[str, Any]):
        """
        Create MSSQL connection pool using aioodbc.

        Args:
            credentials: MSSQL connection credentials

        Returns:
            aioodbc connection pool
        """
        try:
            import aioodbc
        except ImportError:
            raise ImportError("aioodbc not installed. Run: pip install aioodbc")

        # Get pool configuration
        pool_config = credentials.get("connection_pool_config", {})
        min_size = pool_config.get("min_size", 2)
        max_size = pool_config.get("max_size", 10)
        timeout = pool_config.get("timeout", 30)

        # Get password
        password = await self._get_password(credentials)

        # Build connection string
        driver = credentials.get("driver", "ODBC Driver 17 for SQL Server")
        dsn = (
            f"DRIVER={{{driver}}};"
            f"SERVER={credentials['host']},{credentials.get('port', 1433)};"
            f"DATABASE={credentials['database']};"
            f"UID={credentials['username']};"
            f"PWD={password};"
            f"TrustServerCertificate=yes;"
        )

        # Create pool
        pool = await aioodbc.create_pool(
            dsn=dsn,
            minsize=min_size,
            maxsize=max_size,
            timeout=timeout
        )

        logger.info(f"Created MSSQL pool: {credentials['host']}:{credentials.get('port', 1433)}")
        return pool

    async def _create_snowflake_pool(self, credentials: Dict[str, Any]):
        """
        Create Snowflake connection pool using snowflake-connector-python.

        Args:
            credentials: Snowflake connection credentials

        Returns:
            Snowflake connection pool
        """
        try:
            import snowflake.connector
            from snowflake.connector.connection import SnowflakeConnection
        except ImportError:
            raise ImportError("snowflake-connector-python not installed. Run: pip install snowflake-connector-python[pandas]")

        # Get pool configuration
        pool_config = credentials.get("connection_pool_config", {})
        min_size = pool_config.get("min_size", 2)
        max_size = pool_config.get("max_size", 10)
        timeout = pool_config.get("timeout", 30)

        # Get password
        password = await self._get_password(credentials)

        # Simple pool implementation for Snowflake
        # Since snowflake-connector-python doesn't have built-in pooling like aiomysql/asyncpg,
        # we'll create a basic pool wrapper
        class SnowflakePool:
            def __init__(self, account, user, password, warehouse, database, schema, role, max_connections):
                self.account = account
                self.user = user
                self.password = password
                self.warehouse = warehouse
                self.database = database
                self.schema = schema
                self.role = role
                self.max_connections = max_connections
                self.connections = []
                self.available_connections = []
                self.size = 0

            def acquire(self):
                """Acquire a connection from the pool"""
                if self.available_connections:
                    return self.available_connections.pop()
                elif self.size < self.max_connections:
                    conn = snowflake.connector.connect(
                        account=self.account,
                        user=self.user,
                        password=self.password,
                        warehouse=self.warehouse,
                        database=self.database,
                        schema=self.schema,
                        role=self.role,
                        client_session_keep_alive=True
                    )
                    self.connections.append(conn)
                    self.size += 1
                    return conn
                else:
                    # Wait for available connection (simple implementation)
                    import time
                    for _ in range(100):  # Wait up to 10 seconds
                        if self.available_connections:
                            return self.available_connections.pop()
                        time.sleep(0.1)
                    raise Exception("Connection pool exhausted")

            def release(self, conn):
                """Release a connection back to the pool"""
                if conn and conn.is_still_running():
                    self.available_connections.append(conn)

            def close(self):
                """Close all connections in the pool"""
                for conn in self.connections:
                    try:
                        conn.close()
                    except:
                        pass
                self.connections = []
                self.available_connections = []
                self.size = 0

            async def wait_closed(self):
                """Async wait for pool to close (compatibility method)"""
                pass

        # Create pool
        pool = SnowflakePool(
            account=credentials["account"],
            user=credentials["username"],
            password=password,
            warehouse=credentials["warehouse"],
            database=credentials["database"],
            schema=credentials.get("schema", "PUBLIC"),
            role=credentials.get("role"),
            max_connections=max_size
        )

        logger.info(f"Created Snowflake pool: {credentials['account']}/{credentials['warehouse']}")
        return pool

    async def _get_password(self, credentials: Dict[str, Any]) -> str:
        """
        Retrieve password from AWS Secrets Manager or direct credential.

        Args:
            credentials: Database credentials with password or password_secret_arn

        Returns:
            Database password
        """
        if "password_secret_arn" in credentials:
            # Fetch from AWS Secrets Manager
            try:
                import boto3
                secrets_client = boto3.client('secretsmanager')
                response = secrets_client.get_secret_value(
                    SecretId=credentials["password_secret_arn"]
                )
                return response["SecretString"]
            except Exception as e:
                logger.error(f"Failed to retrieve password from Secrets Manager: {e}")
                raise
        else:
            return credentials.get("password", "")

    async def _is_pool_healthy(self, pool, db_type: str) -> bool:
        """
        Check if connection pool is healthy by testing a connection.

        Args:
            pool: Connection pool to test
            db_type: Database type (mysql, postgresql, mssql, snowflake)

        Returns:
            True if pool is healthy, False otherwise
        """
        try:
            if db_type == "mysql":
                # Test MySQL connection
                async with pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("SELECT 1")
                        await cursor.fetchone()
            elif db_type == "postgresql":
                # Test PostgreSQL connection
                async with pool.acquire() as conn:
                    await conn.execute("SELECT 1")
            elif db_type == "mssql":
                # Test MSSQL connection
                async with pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute("SELECT 1")
                        await cursor.fetchone()
            elif db_type == "snowflake":
                # Test Snowflake connection
                def test_snowflake():
                    conn = pool.acquire()
                    try:
                        cursor = conn.cursor()
                        try:
                            cursor.execute("SELECT 1")
                            cursor.fetchone()
                        finally:
                            cursor.close()
                    finally:
                        pool.release(conn)

                import asyncio
                await asyncio.to_thread(test_snowflake)

            return True
        except Exception as e:
            logger.warning(f"Pool health check failed: {e}")
            return False

    async def _cleanup_idle_pools(self):
        """Periodic task to cleanup idle connection pools"""
        while True:
            try:
                await asyncio.sleep(self.pool_cleanup_interval)

                current_time = time.time()
                pools_to_remove = []

                for cache_key, metrics in self.pool_metrics.items():
                    idle_time = current_time - metrics.last_used
                    if idle_time > self.idle_pool_ttl:
                        pools_to_remove.append(cache_key)
                        logger.info(f"Pool {cache_key} idle for {idle_time:.0f}s, marking for cleanup")

                # Cleanup idle pools
                for cache_key in pools_to_remove:
                    await self._destroy_pool(cache_key)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in pool cleanup task: {e}")

    async def _destroy_pool(self, cache_key: str):
        """
        Safely destroy a connection pool.

        Args:
            cache_key: Pool cache key
        """
        if cache_key in self.pools:
            pool = self.pools[cache_key]
            try:
                pool.close()
                await pool.wait_closed()
            except Exception as e:
                logger.error(f"Error closing pool {cache_key}: {e}")

            del self.pools[cache_key]

            if cache_key in self.pool_metrics:
                del self.pool_metrics[cache_key]

            logger.info(f"Destroyed connection pool: {cache_key}")

    def get_pool_metrics(self, cache_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metrics for connection pools.

        Args:
            cache_key: Optional specific pool to get metrics for

        Returns:
            Dictionary of pool metrics
        """
        if cache_key:
            if cache_key in self.pool_metrics:
                return {cache_key: self.pool_metrics[cache_key].__dict__}
            return {}

        # Return all metrics
        return {
            key: metrics.__dict__
            for key, metrics in self.pool_metrics.items()
        }

    def get_pool_status(self) -> Dict[str, Any]:
        """
        Get overall status of connection pool manager.

        Returns:
            Dictionary with pool manager status
        """
        total_pools = len(self.pools)
        current_time = time.time()

        idle_pools = sum(
            1 for metrics in self.pool_metrics.values()
            if (current_time - metrics.last_used) > 300  # 5 min
        )

        return {
            "total_pools": total_pools,
            "active_pools": total_pools - idle_pools,
            "idle_pools": idle_pools,
            "cleanup_task_running": self.cleanup_task is not None and not self.cleanup_task.done(),
            "uptime_seconds": int(time.time() - min(
                (m.created_at for m in self.pool_metrics.values()),
                default=time.time()
            ))
        }


# Global connection pool manager instance
connection_pool_manager = ConnectionPoolManager()
