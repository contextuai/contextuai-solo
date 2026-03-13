"""
Shared test fixtures for ContextuAI Solo backend tests.

Provides an in-memory SQLite adapter, DatabaseProxy, and FastAPI TestClient.
All test data is automatically cleaned up after each test.
"""

import asyncio
import os
import sys
import tempfile
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.sqlite_adapter import SQLiteAdapter
from adapters.motor_compat import DatabaseProxy


# ---------------------------------------------------------------------------
# Event-loop fixture (session-scoped)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# SQLite adapter — fresh temp DB per test
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def sqlite_adapter() -> AsyncGenerator[SQLiteAdapter, None]:
    """Yield an initialised SQLiteAdapter backed by a temp file.

    The temp database is deleted after the test completes.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    adapter = SQLiteAdapter(db_path=tmp.name)
    await adapter.initialize()
    yield adapter
    await adapter.close()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    # Also clean WAL / SHM files
    for ext in ("-wal", "-shm"):
        try:
            os.unlink(tmp.name + ext)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# DatabaseProxy (Motor-compat layer)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def db_proxy(sqlite_adapter: SQLiteAdapter) -> DatabaseProxy:
    """Return a DatabaseProxy wrapping the temp SQLite adapter."""
    return DatabaseProxy(sqlite_adapter)


# ---------------------------------------------------------------------------
# FastAPI test client with dependency overrides
# ---------------------------------------------------------------------------
@pytest.fixture
def test_app(db_proxy: DatabaseProxy):
    """Create a FastAPI test app with the temp database injected.

    The startup event will run (creating real adapters), then we overwrite
    app.state.db, database module globals, and FastAPI dependency overrides
    so every code path uses the temp db_proxy.
    """
    from fastapi.testclient import TestClient
    import database
    from app import app

    # Override dependency for the test
    from database import get_db, get_database
    from services.auth_service import get_current_user, get_current_user_optional

    _DESKTOP_USER = {
        "user_id": "test-user",
        "email": "test@contextuai-solo.local",
        "role": "admin",
        "organization": "solo",
        "department": None,
        "auth_type": "desktop",
        "scopes": ["*"],
    }

    async def _test_get_db():
        return db_proxy

    async def _test_get_user():
        return _DESKTOP_USER

    app.dependency_overrides[get_db] = _test_get_db
    app.dependency_overrides[get_database] = _test_get_db
    app.dependency_overrides[get_current_user] = _test_get_user
    app.dependency_overrides[get_current_user_optional] = _test_get_user

    # Create the TestClient — this triggers startup_event which creates
    # real DB adapters and monkey-patches database.get_database.
    client = TestClient(app)

    # AFTER startup, overwrite everything to point at the temp db_proxy.
    # This ensures all code paths (Depends, direct get_database() calls,
    # app.state.db reads) use the test database.
    async def _test_get_database():
        return db_proxy

    database.get_database = _test_get_database
    database.get_db = _test_get_database
    database._async_db = db_proxy
    app.state.db = db_proxy

    yield client

    # Teardown — clear overrides and reset module globals so the next
    # test's startup_event can run cleanly.
    database._async_db = None
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Desktop user constant
# ---------------------------------------------------------------------------
@pytest.fixture
def desktop_user() -> dict:
    return {
        "user_id": "test-user",
        "email": "test@contextuai-solo.local",
        "role": "admin",
        "organization": "solo",
    }
