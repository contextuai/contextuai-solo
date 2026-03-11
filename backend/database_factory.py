"""
Database Factory

Returns the SQLite DatabaseAdapter for ContextuAI Solo.
Maintains a module-level singleton so only one adapter instance exists.
"""

import logging
from typing import Optional

from adapters.database_adapter import DatabaseAdapter
from adapters.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)

_adapter: Optional[DatabaseAdapter] = None


async def get_database_adapter() -> DatabaseAdapter:
    """Return the singleton SQLiteAdapter instance."""
    global _adapter

    if _adapter is not None:
        return _adapter

    logger.info("Initialising SQLite database adapter")

    adapter = SQLiteAdapter()
    await adapter.initialize()
    _adapter = adapter

    return _adapter


async def close_database_adapter() -> None:
    """Close the singleton adapter (call during shutdown)."""
    global _adapter
    if _adapter is not None:
        await _adapter.close()
        _adapter = None
