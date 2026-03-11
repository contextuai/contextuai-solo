"""
Database Connection Management

In ContextuAI Solo, the Motor/PyMongo code paths are never used — app.py
monkey-patches get_database() and get_db() at startup to return the SQLite-
backed DatabaseProxy.  The imports are kept conditional so this module loads
cleanly without motor/pymongo installed.
"""

import os
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
    from pymongo import MongoClient
    from pymongo.database import Database as SyncDatabase
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
except ImportError:
    # motor/pymongo not installed — Solo desktop mode.
    # get_database() and get_db() are monkey-patched by app.py at startup.
    AsyncIOMotorClient = None
    AsyncIOMotorDatabase = None
    MongoClient = None
    SyncDatabase = None
    ConnectionFailure = Exception
    ServerSelectionTimeoutError = Exception
    logging.getLogger(__name__).debug(
        "motor/pymongo not installed — running in Solo desktop mode"
    )

from settings import settings

# Configure logging
logger = logging.getLogger(__name__)


def _build_tls_options() -> Dict[str, Any]:
    """Build TLS connection options from environment variables."""
    opts: Dict[str, Any] = {}

    if os.getenv("MONGODB_TLS_ENABLED", "false").lower() != "true":
        return opts

    opts["tls"] = True

    ca_cert = os.getenv("TLS_CA_CERT")
    if ca_cert:
        opts["tlsCAFile"] = ca_cert

    client_cert = os.getenv("TLS_CLIENT_CERT")
    if client_cert:
        opts["tlsCertificateKeyFile"] = client_cert

    # Allow invalid certs only in dev (self-signed)
    if os.getenv("ENVIRONMENT", "dev") == "dev":
        opts["tlsAllowInvalidCertificates"] = True
        opts["tlsAllowInvalidHostnames"] = True

    logger.info("MongoDB TLS enabled")
    return opts


# Global MongoDB client instances
_async_client: Optional[AsyncIOMotorClient] = None
_async_db: Optional[AsyncIOMotorDatabase] = None
_sync_client: Optional[MongoClient] = None
_sync_db: Optional[SyncDatabase] = None


# =============================================================================
# Async MongoDB Access (Motor)
# =============================================================================

async def get_database() -> AsyncIOMotorDatabase:
    """
    Get the async MongoDB database instance.
    Creates a new connection if one doesn't exist.

    Returns:
        AsyncIOMotorDatabase: The MongoDB database instance

    Raises:
        ConnectionFailure: If unable to connect to MongoDB
    """
    global _async_client, _async_db

    if _async_db is None:
        try:
            logger.info(f"Connecting to MongoDB at {_mask_connection_string(settings.mongodb_url)}")

            # Build connection options (includes TLS if configured)
            tls_opts = _build_tls_options()

            # Create async client with connection options
            _async_client = AsyncIOMotorClient(
                settings.mongodb_url,
                serverSelectionTimeoutMS=5000,  # 5 second timeout for server selection
                connectTimeoutMS=10000,         # 10 second connection timeout
                socketTimeoutMS=30000,          # 30 second socket timeout
                maxPoolSize=50,                 # Maximum connection pool size
                minPoolSize=5,                  # Minimum connections to maintain
                retryWrites=True,               # Retry failed writes
                retryReads=True,                # Retry failed reads
                **tls_opts,
            )

            _async_db = _async_client[settings.database_name]

            # Verify connection by running a command
            await _async_client.admin.command('ping')
            logger.info(f"Successfully connected to MongoDB database: {settings.database_name}")

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            _async_client = None
            _async_db = None
            raise

    return _async_db


async def get_async_client() -> AsyncIOMotorClient:
    """
    Get the async MongoDB client instance.
    Useful for operations that need access to multiple databases.

    Returns:
        AsyncIOMotorClient: The MongoDB client instance
    """
    global _async_client

    if _async_client is None:
        await get_database()  # This will initialize the client

    return _async_client


async def close_database() -> None:
    """
    Close the async MongoDB connection gracefully.
    Should be called during application shutdown.
    """
    global _async_client, _async_db

    if _async_client is not None:
        logger.info("Closing async MongoDB connection")
        _async_client.close()
        _async_client = None
        _async_db = None


@asynccontextmanager
async def get_database_session():
    """
    Async context manager for database sessions.
    Ensures proper connection handling for scoped operations.

    Usage:
        async with get_database_session() as db:
            await db.collection.find_one(...)
    """
    db = await get_database()
    try:
        yield db
    finally:
        # Connection pooling handles cleanup; no explicit close needed per request
        pass


# =============================================================================
# Sync MongoDB Access (PyMongo) - For non-async contexts
# =============================================================================

def get_sync_database() -> SyncDatabase:
    """
    Get the synchronous MongoDB database instance.
    Use this only when async is not available (e.g., in synchronous contexts).

    Returns:
        SyncDatabase: The synchronous MongoDB database instance

    Raises:
        ConnectionFailure: If unable to connect to MongoDB
    """
    global _sync_client, _sync_db

    if _sync_db is None:
        try:
            logger.info(f"Creating sync MongoDB connection to {_mask_connection_string(settings.mongodb_url)}")

            tls_opts = _build_tls_options()

            _sync_client = MongoClient(
                settings.mongodb_url,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=30000,
                maxPoolSize=10,  # Smaller pool for sync access
                minPoolSize=1,
                retryWrites=True,
                retryReads=True,
                **tls_opts,
            )

            _sync_db = _sync_client[settings.database_name]

            # Verify connection
            _sync_client.admin.command('ping')
            logger.info(f"Sync MongoDB connection established: {settings.database_name}")

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to create sync MongoDB connection: {e}")
            _sync_client = None
            _sync_db = None
            raise

    return _sync_db


def close_sync_database() -> None:
    """Close the synchronous MongoDB connection."""
    global _sync_client, _sync_db

    if _sync_client is not None:
        logger.info("Closing sync MongoDB connection")
        _sync_client.close()
        _sync_client = None
        _sync_db = None


# =============================================================================
# Health Check Functions
# =============================================================================

async def check_database_health() -> dict:
    """
    Check the health of the MongoDB connection.

    Returns:
        dict: Health status with details
            - healthy (bool): Whether the connection is healthy
            - latency_ms (float): Round-trip latency in milliseconds
            - database (str): Database name
            - message (str): Status message or error details
    """
    import time

    result = {
        "healthy": False,
        "latency_ms": None,
        "database": settings.database_name,
        "message": ""
    }

    try:
        start_time = time.time()

        client = await get_async_client()
        await client.admin.command('ping')

        latency = (time.time() - start_time) * 1000  # Convert to milliseconds

        result["healthy"] = True
        result["latency_ms"] = round(latency, 2)
        result["message"] = "MongoDB connection is healthy"

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        result["message"] = f"Connection failed: {str(e)}"
        logger.warning(f"Database health check failed: {e}")

    except Exception as e:
        result["message"] = f"Unexpected error: {str(e)}"
        logger.error(f"Unexpected error during health check: {e}")

    return result


async def ensure_indexes() -> None:
    """
    Ensure required database indexes exist.
    Call this during application startup to create necessary indexes.
    """
    try:
        db = await get_database()

        # Example indexes - customize based on your collections
        # Users collection
        await db.users.create_index("email", unique=True)
        await db.users.create_index("created_at")

        # Conversations collection
        await db.conversations.create_index("user_id")
        await db.conversations.create_index("created_at")
        await db.conversations.create_index([("user_id", 1), ("created_at", -1)])

        # Messages collection
        await db.messages.create_index("conversation_id")
        await db.messages.create_index("created_at")
        await db.messages.create_index([("conversation_id", 1), ("created_at", 1)])

        # Personas collection
        await db.personas.create_index("user_id")
        await db.personas.create_index("name")
        await db.personas.create_index("type")

        # API Keys collection
        await db.api_keys.create_index("key_hash", unique=True)
        await db.api_keys.create_index("key_id", unique=True)
        await db.api_keys.create_index("user_id")
        await db.api_keys.create_index([("user_id", 1), ("status", 1)])

        # Audit Logs collection
        await db.audit_logs.create_index("timestamp")
        await db.audit_logs.create_index("user_id")
        await db.audit_logs.create_index("action")
        await db.audit_logs.create_index([("action", 1), ("timestamp", -1)])
        await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)])

        # Crews collection
        await db.crews.create_index("crew_id", unique=True)
        await db.crews.create_index("user_id")
        await db.crews.create_index([("user_id", 1), ("status", 1)])
        await db.crews.create_index([("user_id", 1), ("deleted_at", 1)])

        # Event Subscriptions collection
        await db.event_subscriptions.create_index("subscription_id", unique=True)
        await db.event_subscriptions.create_index("user_id")
        await db.event_subscriptions.create_index([("user_id", 1), ("status", 1)])
        await db.event_subscriptions.create_index("event_types")
        await db.event_subscriptions.create_index([("status", 1), ("event_types", 1)])

        # Event Deliveries collection
        await db.event_deliveries.create_index("delivery_id", unique=True)
        await db.event_deliveries.create_index("subscription_id")
        await db.event_deliveries.create_index([("subscription_id", 1), ("created_at", -1)])

        # MFA Challenges collection (TTL index for auto-expiry)
        await db.mfa_challenges.create_index("challenge_id", unique=True)
        await db.mfa_challenges.create_index("user_id")
        await db.mfa_challenges.create_index("expires_at", expireAfterSeconds=0)

        # SSO Providers collection
        await db.sso_providers.create_index("provider_id", unique=True)
        await db.sso_providers.create_index("organization")
        await db.sso_providers.create_index("domain_hint")
        await db.sso_providers.create_index([("organization", 1), ("status", 1)])

        # Crew Memories collection
        await db.crew_memories.create_index("memory_id", unique=True)
        await db.crew_memories.create_index("crew_id")
        await db.crew_memories.create_index([("crew_id", 1), ("category", 1)])
        await db.crew_memories.create_index([("crew_id", 1), ("importance", -1), ("created_at", -1)])
        await db.crew_memories.create_index("expires_at")

        # Crew Runs collection
        await db.crew_runs.create_index("run_id", unique=True)
        await db.crew_runs.create_index("crew_id")
        await db.crew_runs.create_index([("crew_id", 1), ("status", 1)])
        await db.crew_runs.create_index([("crew_id", 1), ("created_at", -1)])
        await db.crew_runs.create_index("user_id")

        logger.info("Database indexes ensured successfully")

    except Exception as e:
        logger.error(f"Failed to ensure database indexes: {e}")
        raise


# =============================================================================
# Utility Functions
# =============================================================================

def _mask_connection_string(url: str) -> str:
    """
    Mask sensitive parts of the connection string for logging.
    Hides passwords and credentials from logs.
    """
    if "@" in url:
        # Has credentials - mask the password portion
        protocol_end = url.find("://") + 3
        at_pos = url.find("@")

        # Find the colon separating username from password
        credentials = url[protocol_end:at_pos]
        if ":" in credentials:
            username = credentials.split(":")[0]
            masked_credentials = f"{username}:****"
        else:
            masked_credentials = credentials

        return url[:protocol_end] + masked_credentials + url[at_pos:]

    return url


# =============================================================================
# FastAPI Dependency
# =============================================================================

async def get_db():
    """
    FastAPI dependency for database access.

    Usage in routes:
        @router.get("/items")
        async def get_items(db = Depends(get_db)):
            return await db.items.find().to_list(100)
    """
    return await get_database()
