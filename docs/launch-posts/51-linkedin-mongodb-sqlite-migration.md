# LinkedIn — Technical Deep Dive: MongoDB to SQLite Migration

**Target:** Post targeting backend engineers, database architects, technical leaders

---

**I migrated a production app from MongoDB to SQLite without rewriting a single query.**

Here's how.

**The problem:** ContextuAI Solo started as a cloud app with MongoDB. When I pivoted to a local-first desktop app, I needed everything in a single file on the user's machine. SQLite was the obvious choice — but the entire backend was written against MongoDB's Motor async driver.

**The solution:** A compatibility layer that makes SQLite look like MongoDB.

**`motor_compat.py`** — Two classes:
- `DatabaseProxy` mimics `AsyncIOMotorDatabase`
- `CollectionProxy` mimics `AsyncIOMotorCollection`

**`sqlite_adapter.py`** — Async SQLite wrapper (aiosqlite) that translates:
- MongoDB query operators (`$set`, `$in`, `$regex`, `$gt`, `$lt`, `$exists`) → SQL/JSON expressions
- Document structure → `_id TEXT PRIMARY KEY, data JSON NOT NULL` pattern
- `find()`, `find_one()`, `insert_one()`, `update_one()`, `delete_many()` → equivalent SQL

**What stayed the same:**
- Every repository file — zero changes
- Every service file — zero changes
- Every router file — zero changes
- All query patterns — `{"status": {"$in": ["active", "pending"]}}`

**What changed:**
- Database initialization (one file)
- Connection setup (one file)

**The tradeoff:** JSON blob storage means no column-level indexing. For a single-user desktop app with <100K documents, this is fine. For a multi-tenant SaaS, you'd want proper schema.

**Lines of code:** ~400 for the entire compatibility layer. Saved rewriting ~5000 lines of backend code.

GitHub: https://github.com/contextuai/contextuai-solo

#MongoDB #SQLite #DatabaseMigration #Python #SoftwareArchitecture #Backend
