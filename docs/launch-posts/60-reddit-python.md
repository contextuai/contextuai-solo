# Reddit — r/Python

**Target:** Python developers

---

**Title:** Built a FastAPI backend with a MongoDB-to-SQLite compatibility layer — the backend for an open-source desktop AI assistant

**Body:**

Sharing the Python backend architecture for **ContextuAI Solo**, a desktop AI assistant with 93+ business agents.

**The backend runs as a sidecar** — bundled via PyInstaller into a standalone binary, spawned by a Tauri v2 (Rust) desktop shell.

**Interesting Python patterns:**

**1. MongoDB-to-SQLite compatibility layer:**

The backend was originally built on MongoDB with Motor (async driver). When I pivoted to a local desktop app, I needed SQLite. Instead of rewriting every query, I built a compatibility layer:

- `adapters/motor_compat.py` — `DatabaseProxy` and `CollectionProxy` that mimic Motor's `AsyncIOMotorDatabase` and `AsyncIOMotorCollection`
- `adapters/sqlite_adapter.py` — Async SQLite wrapper (aiosqlite) that translates MongoDB query operators to SQL/JSON

Supports: `$set`, `$in`, `$regex`, `$gt`, `$lt`, `$exists`, `$push`, `$pull`, and more.

Tables use: `_id TEXT PRIMARY KEY, data JSON NOT NULL` — documents stored as JSON blobs.

~400 lines saved rewriting ~5000 lines of backend code.

**2. Repository pattern with generics:**
```python
class BaseRepository(Generic[T]):
    # Async CRUD operations
    # All repositories inherit from this
```

**3. Service layer with FastAPI Depends():**
Services injected with repositories. Clean separation of concerns.

**4. Local inference with llama-cpp-python:**
- `asyncio.Lock` prevents concurrent model access (llama-cpp is not thread-safe)
- SSE streaming for token-by-token output
- Second request waits for first to finish/abort

**5. Agent library as markdown:**
93+ agents defined as markdown files with YAML frontmatter. Auto-seeded into SQLite on first launch. No code changes needed to add agents.

**Stack:** FastAPI + aiosqlite + llama-cpp-python + Pydantic v2 + PyInstaller

GitHub: https://github.com/contextuai/contextuai-solo
