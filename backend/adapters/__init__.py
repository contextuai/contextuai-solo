"""
ContextuAI Solo Adapters

Adapter layer for the desktop backend: SQLite, APScheduler, local filesystem.
"""

# Abstract interfaces
from adapters.database_adapter import DatabaseAdapter
from adapters.scheduler_adapter import SchedulerAdapter
from adapters.storage_adapter import StorageAdapter
from adapters.auth_adapter import AuthAdapter

# Desktop implementations
from adapters.sqlite_adapter import SQLiteAdapter
from adapters.apscheduler_adapter import APSchedulerAdapter
from adapters.local_storage_adapter import LocalStorageAdapter
from adapters.auth_adapter import DesktopAuthAdapter

# Motor compatibility layer
from adapters.motor_compat import DatabaseProxy, CollectionProxy, CursorProxy

__all__ = [
    # Interfaces
    "DatabaseAdapter",
    "SchedulerAdapter",
    "StorageAdapter",
    "AuthAdapter",
    # Desktop
    "SQLiteAdapter",
    "APSchedulerAdapter",
    "LocalStorageAdapter",
    "DesktopAuthAdapter",
    # Compatibility
    "DatabaseProxy",
    "CollectionProxy",
    "CursorProxy",
]
