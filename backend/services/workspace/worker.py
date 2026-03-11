"""
Worker Entry Point for AI Team Workspace Feature

Main entry point for the workspace worker container.
Initializes database connection and runs the orchestrator loop.
"""

import os
import sys
import signal
import asyncio
import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from services.workspace.orchestrator import WorkspaceOrchestrator, create_orchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Environment configuration
MONGODB_URI = os.getenv("MONGODB_URL", "mongodb://mongodb:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "contextuai")
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# Global orchestrator reference for signal handling
_orchestrator: Optional[WorkspaceOrchestrator] = None


async def get_database() -> AsyncIOMotorDatabase:
    """
    Initialize and return MongoDB database connection.

    Returns:
        AsyncIOMotorDatabase instance
    """
    logger.info(f"Connecting to MongoDB: {MONGODB_URI}")

    client = AsyncIOMotorClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000
    )

    # Test connection
    try:
        await client.admin.command('ping')
        logger.info("MongoDB connection successful")
    except Exception as e:
        logger.error(f"MongoDB connection failed: {e}")
        raise

    db = client[MONGODB_DATABASE]
    logger.info(f"Using database: {MONGODB_DATABASE}")

    return db


def signal_handler(signum: int, frame) -> None:
    """
    Handle shutdown signals gracefully.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    signal_name = signal.Signals(signum).name
    logger.info(f"Received signal {signal_name}, initiating graceful shutdown...")

    if _orchestrator:
        _orchestrator.stop()


async def run_worker() -> None:
    """
    Initialize and run the workspace worker.

    Sets up database connection, creates orchestrator, and runs the main loop.
    """
    global _orchestrator

    logger.info("=" * 50)
    logger.info("Workspace Worker Starting")
    logger.info(f"Environment: {ENVIRONMENT}")
    logger.info("=" * 50)

    try:
        # Initialize database
        db = await get_database()

        # Create orchestrator
        _orchestrator = create_orchestrator(db)
        logger.info(f"Orchestrator created: {_orchestrator.worker_id}")

        # Run orchestrator
        await _orchestrator.run()

    except asyncio.CancelledError:
        logger.info("Worker cancelled, shutting down...")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise
    finally:
        logger.info("Worker shutdown complete")


async def main() -> None:
    """
    Main entry point for the worker.

    Sets up signal handlers and runs the worker loop.
    """
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Run worker
    await run_worker()


if __name__ == "__main__":
    logger.info("Starting Workspace Worker...")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by keyboard")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        sys.exit(1)

    logger.info("Worker exited")
