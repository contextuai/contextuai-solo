"""
ContextuAI Adapters

Adapter layer enabling the same FastAPI backend to run with different
infrastructure backends:

- **Enterprise mode** (``CONTEXTUAI_MODE=enterprise``): MongoDB, Celery + Redis, S3
- **Desktop mode** (``CONTEXTUAI_MODE=desktop``): SQLite, APScheduler, local filesystem

Select the mode by setting the ``CONTEXTUAI_MODE`` environment variable.
"""

# Abstract interfaces
from adapters.database_adapter import DatabaseAdapter
from adapters.scheduler_adapter import SchedulerAdapter
from adapters.storage_adapter import StorageAdapter
from adapters.auth_adapter import AuthAdapter

# Enterprise implementations
from adapters.mongo_adapter import MongoAdapter
from adapters.celery_adapter import CelerySchedulerAdapter
from adapters.s3_adapter import S3StorageAdapter
from adapters.auth_adapter import EnterpriseAuthAdapter

# Desktop implementations
from adapters.sqlite_adapter import SQLiteAdapter
from adapters.apscheduler_adapter import APSchedulerAdapter
from adapters.local_storage_adapter import LocalStorageAdapter
from adapters.auth_adapter import DesktopAuthAdapter

# Motor compatibility layer (for desktop mode)
from adapters.motor_compat import DatabaseProxy, CollectionProxy, CursorProxy

__all__ = [
    # Interfaces
    "DatabaseAdapter",
    "SchedulerAdapter",
    "StorageAdapter",
    "AuthAdapter",
    # Enterprise
    "MongoAdapter",
    "CelerySchedulerAdapter",
    "S3StorageAdapter",
    "EnterpriseAuthAdapter",
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
