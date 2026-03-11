"""
SQLite Adapter

Provides a MongoDB-compatible interface on top of SQLite + JSON1, enabling
the ContextuAI Solo desktop app to run without MongoDB.

Design
------
* Each MongoDB "collection" becomes a SQLite table with the schema:
    ``_id TEXT PRIMARY KEY, data JSON, created_at TEXT, updated_at TEXT``
* Documents are stored as JSON blobs in the ``data`` column.
* MongoDB query operators (``$set``, ``$in``, ``$regex``, etc.) are translated
  to SQL / ``json_extract`` expressions.
* Tables are auto-created on first access (schema-less, like MongoDB).
"""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import aiosqlite

from adapters.database_adapter import DatabaseAdapter

logger = logging.getLogger(__name__)

# Default database path
_DEFAULT_DB_DIR = os.path.expanduser("~/.contextuai-solo/data")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "contextuai.db")


class SQLiteAdapter(DatabaseAdapter):
    """DatabaseAdapter backed by SQLite via ``aiosqlite``.

    Parameters
    ----------
    db_path : str, optional
        Path to the SQLite database file.  Defaults to
        ``~/.contextuai-solo/data/contextuai.db``.
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._ensured_tables: Set[str] = set()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the database connection and enable WAL mode / JSON1."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        # Verify JSON1 is available
        try:
            async with self._db.execute(
                "SELECT json_extract('{\"a\":1}', '$.a')"
            ) as cur:
                row = await cur.fetchone()
                assert row is not None
        except Exception:
            raise RuntimeError(
                "SQLite JSON1 extension is required but not available"
            )
        logger.info("SQLiteAdapter initialised at %s", self.db_path)

    async def _ensure_table(self, collection: str) -> None:
        """Create the table for *collection* if it does not exist yet."""
        if collection in self._ensured_tables:
            return
        safe_name = self._safe_table_name(collection)
        await self._db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS [{safe_name}] (
                _id       TEXT PRIMARY KEY,
                data      JSON NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        await self._db.commit()
        self._ensured_tables.add(collection)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def find(
        self,
        collection: str,
        filter: dict,
        sort: list = None,
        limit: int = 0,
        skip: int = 0,
        projection: dict = None,
    ) -> list:
        await self._ensure_table(collection)
        where, params = self._build_where(filter)
        order_by = self._build_order_by(sort)
        sql = f"SELECT _id, data FROM [{self._safe_table_name(collection)}]"
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        if skip:
            sql += f" OFFSET {int(skip)}"
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        docs = [self._row_to_doc(row) for row in rows]
        if projection:
            docs = [self._apply_projection(doc, projection) for doc in docs]
        return docs

    async def find_one(
        self, collection: str, filter: dict, projection: dict = None
    ) -> Optional[dict]:
        results = await self.find(
            collection, filter, limit=1, projection=projection
        )
        return results[0] if results else None

    async def insert_one(self, collection: str, document: dict) -> str:
        await self._ensure_table(collection)
        doc = document.copy()
        doc_id = str(doc.pop("_id", None) or uuid.uuid4())
        doc["_id"] = doc_id
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(doc, default=str)
        await self._db.execute(
            f"INSERT INTO [{self._safe_table_name(collection)}] (_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (doc_id, data_json, now, now),
        )
        await self._db.commit()
        return doc_id

    async def insert_many(self, collection: str, documents: list) -> list:
        await self._ensure_table(collection)
        ids: List[str] = []
        now = datetime.now(timezone.utc).isoformat()
        table = self._safe_table_name(collection)
        for doc in documents:
            doc = doc.copy()
            doc_id = str(doc.pop("_id", None) or uuid.uuid4())
            doc["_id"] = doc_id
            data_json = json.dumps(doc, default=str)
            await self._db.execute(
                f"INSERT INTO [{table}] (_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (doc_id, data_json, now, now),
            )
            ids.append(doc_id)
        await self._db.commit()
        return ids

    async def update_one(
        self,
        collection: str,
        filter: dict,
        update: dict,
        upsert: bool = False,
    ) -> int:
        await self._ensure_table(collection)
        doc = await self.find_one(collection, filter)
        if doc is None:
            if upsert:
                merged = self._apply_update_operators(filter.copy(), update)
                await self.insert_one(collection, merged)
                return 1
            return 0
        updated_doc = self._apply_update_operators(doc, update)
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(updated_doc, default=str)
        await self._db.execute(
            f"UPDATE [{self._safe_table_name(collection)}] SET data = ?, updated_at = ? WHERE _id = ?",
            (data_json, now, doc["_id"]),
        )
        await self._db.commit()
        return 1

    async def update_many(
        self, collection: str, filter: dict, update: dict
    ) -> int:
        await self._ensure_table(collection)
        docs = await self.find(collection, filter)
        if not docs:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        table = self._safe_table_name(collection)
        count = 0
        for doc in docs:
            updated_doc = self._apply_update_operators(doc, update)
            data_json = json.dumps(updated_doc, default=str)
            await self._db.execute(
                f"UPDATE [{table}] SET data = ?, updated_at = ? WHERE _id = ?",
                (data_json, now, doc["_id"]),
            )
            count += 1
        await self._db.commit()
        return count

    async def delete_one(self, collection: str, filter: dict) -> int:
        await self._ensure_table(collection)
        doc = await self.find_one(collection, filter)
        if doc is None:
            return 0
        await self._db.execute(
            f"DELETE FROM [{self._safe_table_name(collection)}] WHERE _id = ?",
            (doc["_id"],),
        )
        await self._db.commit()
        return 1

    async def delete_many(self, collection: str, filter: dict) -> int:
        await self._ensure_table(collection)
        where, params = self._build_where(filter)
        sql = f"DELETE FROM [{self._safe_table_name(collection)}]"
        if where:
            sql += f" WHERE {where}"
        async with self._db.execute(sql, params) as cursor:
            count = cursor.rowcount
        await self._db.commit()
        return count

    async def count(self, collection: str, filter: dict = None) -> int:
        await self._ensure_table(collection)
        where, params = self._build_where(filter or {})
        sql = f"SELECT COUNT(*) FROM [{self._safe_table_name(collection)}]"
        if where:
            sql += f" WHERE {where}"
        async with self._db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def distinct(
        self, collection: str, field: str, filter: dict = None
    ) -> list:
        await self._ensure_table(collection)
        json_path = self._field_to_json_path(field)
        where, params = self._build_where(filter or {})
        sql = f"SELECT DISTINCT json_extract(data, ?) FROM [{self._safe_table_name(collection)}]"
        all_params = [json_path] + params
        if where:
            sql += f" WHERE {where}"
        async with self._db.execute(sql, all_params) as cursor:
            rows = await cursor.fetchall()
        values = []
        for row in rows:
            val = row[0]
            if val is not None:
                # Try to deserialise JSON values (arrays, objects)
                try:
                    val = json.loads(val) if isinstance(val, str) and val.startswith(("{", "[")) else val
                except (json.JSONDecodeError, TypeError):
                    pass
                values.append(val)
        return values

    async def find_one_and_update(
        self,
        collection: str,
        filter: dict,
        update: dict,
        upsert: bool = False,
        return_document: bool = True,
    ) -> Optional[dict]:
        await self._ensure_table(collection)
        doc = await self.find_one(collection, filter)
        if doc is None and not upsert:
            return None
        if doc is None:
            # upsert — create
            merged = self._apply_update_operators(filter.copy(), update)
            doc_id = await self.insert_one(collection, merged)
            return await self.find_one(collection, {"_id": doc_id})
        # update in place
        updated_doc = self._apply_update_operators(doc, update)
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(updated_doc, default=str)
        await self._db.execute(
            f"UPDATE [{self._safe_table_name(collection)}] SET data = ?, updated_at = ? WHERE _id = ?",
            (data_json, now, doc["_id"]),
        )
        await self._db.commit()
        if return_document:
            return updated_doc
        return doc  # return the *before* image

    async def aggregate(self, collection: str, pipeline: list) -> list:
        """Execute a basic aggregation pipeline.

        Supported stages: ``$match``, ``$group``, ``$sort``, ``$limit``,
        ``$skip``, ``$project``, ``$count``.  Complex pipelines that cannot
        be translated will raise ``NotImplementedError``.
        """
        await self._ensure_table(collection)
        # Start with all docs
        docs = await self.find(collection, {})

        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if self._doc_matches(d, stage["$match"])]

            elif "$sort" in stage:
                sort_spec = stage["$sort"]
                for key, direction in reversed(list(sort_spec.items())):
                    docs.sort(
                        key=lambda d, k=key: self._get_nested(d, k) or "",
                        reverse=(direction == -1),
                    )

            elif "$limit" in stage:
                docs = docs[: stage["$limit"]]

            elif "$skip" in stage:
                docs = docs[stage["$skip"] :]

            elif "$project" in stage:
                docs = [self._apply_projection(d, stage["$project"]) for d in docs]

            elif "$count" in stage:
                field_name = stage["$count"]
                docs = [{field_name: len(docs)}]

            elif "$group" in stage:
                docs = self._execute_group(docs, stage["$group"])

            elif "$unwind" in stage:
                docs = self._execute_unwind(docs, stage["$unwind"])

            else:
                supported = "$match, $sort, $limit, $skip, $project, $count, $group, $unwind"
                raise NotImplementedError(
                    f"Unsupported aggregation stage: {list(stage.keys())}. "
                    f"Supported stages: {supported}"
                )

        return docs

    async def create_index(self, collection: str, keys, **kwargs) -> str:
        """Create a SQLite index on ``json_extract`` expressions.

        *keys* may be:
        - A string (single field name)
        - A list of ``(field, direction)`` tuples (compound index)
        """
        await self._ensure_table(collection)
        table = self._safe_table_name(collection)

        if isinstance(keys, str):
            fields = [(keys, 1)]
        elif isinstance(keys, list):
            fields = keys
        else:
            # single key with direction
            fields = [(keys, 1)]

        parts: List[str] = []
        name_parts: List[str] = []
        for field, _direction in fields:
            if field == "_id":
                parts.append("_id")
            else:
                parts.append(f"json_extract(data, '{self._field_to_json_path(field)}')")
            name_parts.append(field.replace(".", "_"))

        unique = "UNIQUE" if kwargs.get("unique") else ""
        idx_name = f"idx_{table}_{'_'.join(name_parts)}"
        cols = ", ".join(parts)

        sql = f"CREATE {unique} INDEX IF NOT EXISTS [{idx_name}] ON [{table}] ({cols})"
        try:
            await self._db.execute(sql)
            await self._db.commit()
        except Exception as exc:
            # Non-fatal — indexes are performance aids, not requirements
            logger.warning("Failed to create index %s: %s", idx_name, exc)
        return idx_name

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("SQLiteAdapter connection closed")

    async def health_check(self) -> dict:
        try:
            start = time.time()
            async with self._db.execute("SELECT 1") as cur:
                await cur.fetchone()
            latency = (time.time() - start) * 1000
            return {
                "healthy": True,
                "latency_ms": round(latency, 2),
                "backend": "sqlite",
                "db_path": self.db_path,
                "message": "SQLite connection is healthy",
            }
        except Exception as exc:
            return {
                "healthy": False,
                "backend": "sqlite",
                "message": f"SQLite health check failed: {exc}",
            }

    # ==================================================================
    # Private helpers — MongoDB operator translation
    # ==================================================================

    @staticmethod
    def _safe_table_name(collection: str) -> str:
        """Sanitise collection name for use as a SQLite table name."""
        return re.sub(r"[^a-zA-Z0-9_]", "_", collection)

    @staticmethod
    def _field_to_json_path(field: str) -> str:
        """Convert a dot-notation field to a ``json_extract`` path.

        ``"user.name"`` → ``"$.user.name"``
        ``"_id"`` → ``"$._id"``
        """
        return "$." + field

    # ------------------------------------------------------------------
    # WHERE clause builder
    # ------------------------------------------------------------------

    def _build_where(self, filter: dict) -> Tuple[str, list]:
        """Translate a MongoDB-style filter dict into a SQL WHERE clause.

        Returns ``(clause, params)`` where *clause* is a SQL expression
        (without the ``WHERE`` keyword) and *params* is a list of bind values.
        """
        if not filter:
            return "", []

        clauses: List[str] = []
        params: List[Any] = []

        for key, value in filter.items():
            if key == "$and":
                sub_clauses = []
                for sub_filter in value:
                    c, p = self._build_where(sub_filter)
                    if c:
                        sub_clauses.append(f"({c})")
                        params.extend(p)
                if sub_clauses:
                    clauses.append("(" + " AND ".join(sub_clauses) + ")")

            elif key == "$or":
                sub_clauses = []
                for sub_filter in value:
                    c, p = self._build_where(sub_filter)
                    if c:
                        sub_clauses.append(f"({c})")
                        params.extend(p)
                if sub_clauses:
                    clauses.append("(" + " OR ".join(sub_clauses) + ")")

            elif key == "$nor":
                sub_clauses = []
                for sub_filter in value:
                    c, p = self._build_where(sub_filter)
                    if c:
                        sub_clauses.append(f"({c})")
                        params.extend(p)
                if sub_clauses:
                    clauses.append("NOT (" + " OR ".join(sub_clauses) + ")")

            elif key == "_id":
                if isinstance(value, dict):
                    c, p = self._build_operator_clause("_id", value, use_json=False)
                    clauses.append(c)
                    params.extend(p)
                else:
                    clauses.append("_id = ?")
                    params.append(str(value))

            elif isinstance(value, dict) and any(
                k.startswith("$") for k in value
            ):
                # Operator expression: { field: { $gte: 5, $lt: 10 } }
                c, p = self._build_operator_clause(key, value)
                clauses.append(c)
                params.extend(p)

            else:
                # Simple equality
                json_path = self._field_to_json_path(key)
                if value is None:
                    clauses.append(
                        f"(json_extract(data, ?) IS NULL)"
                    )
                    params.append(json_path)
                elif isinstance(value, bool):
                    clauses.append(f"json_extract(data, ?) = ?")
                    params.extend([json_path, int(value)])
                elif isinstance(value, (int, float)):
                    clauses.append(f"json_extract(data, ?) = ?")
                    params.extend([json_path, value])
                else:
                    clauses.append(f"json_extract(data, ?) = ?")
                    params.extend([json_path, str(value) if not isinstance(value, str) else value])

        return " AND ".join(clauses), params

    def _build_operator_clause(
        self, field: str, ops: dict, use_json: bool = True
    ) -> Tuple[str, list]:
        """Build SQL clause for a single field with MongoDB comparison operators."""
        clauses: List[str] = []
        params: List[Any] = []

        if use_json:
            json_path = self._field_to_json_path(field)
            col_expr = f"json_extract(data, ?)"
        else:
            col_expr = field
            json_path = None

        def _add_path_param():
            if json_path is not None:
                params.append(json_path)

        for op, val in ops.items():
            if op == "$eq":
                _add_path_param()
                clauses.append(f"{col_expr} = ?")
                params.append(self._bind_value(val))

            elif op == "$ne":
                _add_path_param()
                clauses.append(f"({col_expr} != ? OR {col_expr} IS NULL)")
                if json_path is not None:
                    params.append(json_path)
                params.append(self._bind_value(val))

            elif op == "$gt":
                _add_path_param()
                clauses.append(f"{col_expr} > ?")
                params.append(self._bind_value(val))

            elif op == "$gte":
                _add_path_param()
                clauses.append(f"{col_expr} >= ?")
                params.append(self._bind_value(val))

            elif op == "$lt":
                _add_path_param()
                clauses.append(f"{col_expr} < ?")
                params.append(self._bind_value(val))

            elif op == "$lte":
                _add_path_param()
                clauses.append(f"{col_expr} <= ?")
                params.append(self._bind_value(val))

            elif op == "$in":
                if not val:
                    clauses.append("0")  # empty $in matches nothing
                else:
                    _add_path_param()
                    placeholders = ", ".join("?" for _ in val)
                    clauses.append(f"{col_expr} IN ({placeholders})")
                    params.extend(self._bind_value(v) for v in val)

            elif op == "$nin":
                if not val:
                    pass  # empty $nin matches everything — no clause needed
                else:
                    _add_path_param()
                    placeholders = ", ".join("?" for _ in val)
                    clauses.append(f"({col_expr} NOT IN ({placeholders}) OR {col_expr} IS NULL)")
                    if json_path is not None:
                        params.append(json_path)
                    params.extend(self._bind_value(v) for v in val)

            elif op == "$exists":
                _add_path_param()
                if val:
                    clauses.append(f"{col_expr} IS NOT NULL")
                else:
                    clauses.append(f"{col_expr} IS NULL")

            elif op == "$regex":
                _add_path_param()
                # Convert basic regex to LIKE when possible, else use GLOB
                pattern = val
                options = ops.get("$options", "")
                if "i" in options:
                    clauses.append(f"{col_expr} LIKE ?")
                    # Convert simple .* patterns
                    like_pattern = self._regex_to_like(pattern)
                    params.append(like_pattern)
                else:
                    clauses.append(f"{col_expr} LIKE ?")
                    like_pattern = self._regex_to_like(pattern)
                    params.append(like_pattern)

            elif op == "$not":
                sub_c, sub_p = self._build_operator_clause(field, val, use_json)
                clauses.append(f"NOT ({sub_c})")
                params.extend(sub_p)

            elif op == "$options":
                # Handled alongside $regex
                pass

            else:
                logger.warning("Unsupported MongoDB operator: %s (treating as no-op)", op)

        return " AND ".join(clauses) if clauses else "1", params

    # ------------------------------------------------------------------
    # ORDER BY builder
    # ------------------------------------------------------------------

    def _build_order_by(self, sort: Optional[list]) -> str:
        if not sort:
            return ""
        parts: List[str] = []
        for field, direction in sort:
            if field == "_id":
                expr = "_id"
            else:
                expr = f"json_extract(data, '{self._field_to_json_path(field)}')"
            parts.append(f"{expr} {'ASC' if direction == 1 else 'DESC'}")
        return ", ".join(parts)

    # ------------------------------------------------------------------
    # Row / document helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_doc(row) -> dict:
        """Convert a SQLite row (with ``_id`` and ``data`` columns) to a dict."""
        data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        data["_id"] = row["_id"]
        return data

    @staticmethod
    def _apply_projection(doc: dict, projection: dict) -> dict:
        """Apply a MongoDB-style projection to a document."""
        if not projection:
            return doc
        # If any value is 1, it's an inclusion projection
        include = any(v == 1 for k, v in projection.items() if k != "_id")
        if include:
            result = {}
            # _id is included by default unless explicitly excluded
            if projection.get("_id", 1) != 0:
                result["_id"] = doc.get("_id")
            for key, val in projection.items():
                if val == 1 and key != "_id":
                    result[key] = doc.get(key)
            return result
        else:
            # Exclusion projection
            result = doc.copy()
            for key, val in projection.items():
                if val == 0:
                    result.pop(key, None)
            return result

    # ------------------------------------------------------------------
    # Update operator application
    # ------------------------------------------------------------------

    def _apply_update_operators(self, doc: dict, update: dict) -> dict:
        """Apply MongoDB update operators to a document in-memory."""
        doc = doc.copy()

        if "$set" in update:
            for key, value in update["$set"].items():
                self._set_nested(doc, key, value)

        if "$unset" in update:
            for key in update["$unset"]:
                self._unset_nested(doc, key)

        if "$inc" in update:
            for key, amount in update["$inc"].items():
                current = self._get_nested(doc, key) or 0
                self._set_nested(doc, key, current + amount)

        if "$push" in update:
            for key, value in update["$push"].items():
                current = self._get_nested(doc, key)
                if current is None:
                    current = []
                if not isinstance(current, list):
                    current = [current]
                if isinstance(value, dict) and "$each" in value:
                    current.extend(value["$each"])
                else:
                    current.append(value)
                self._set_nested(doc, key, current)

        if "$pull" in update:
            for key, condition in update["$pull"].items():
                current = self._get_nested(doc, key)
                if isinstance(current, list):
                    if isinstance(condition, dict):
                        current = [
                            item
                            for item in current
                            if not self._doc_matches(
                                item if isinstance(item, dict) else {key: item},
                                condition,
                            )
                        ]
                    else:
                        current = [item for item in current if item != condition]
                    self._set_nested(doc, key, current)

        if "$addToSet" in update:
            for key, value in update["$addToSet"].items():
                current = self._get_nested(doc, key)
                if current is None:
                    current = []
                if not isinstance(current, list):
                    current = [current]
                if isinstance(value, dict) and "$each" in value:
                    for v in value["$each"]:
                        if v not in current:
                            current.append(v)
                else:
                    if value not in current:
                        current.append(value)
                self._set_nested(doc, key, current)

        if "$setOnInsert" in update:
            for key, value in update["$setOnInsert"].items():
                if self._get_nested(doc, key) is None:
                    self._set_nested(doc, key, value)

        if "$min" in update:
            for key, value in update["$min"].items():
                current = self._get_nested(doc, key)
                if current is None or value < current:
                    self._set_nested(doc, key, value)

        if "$max" in update:
            for key, value in update["$max"].items():
                current = self._get_nested(doc, key)
                if current is None or value > current:
                    self._set_nested(doc, key, value)

        # If none of the above operators were found, treat the entire update
        # as a replacement document (MongoDB behaviour for non-operator updates)
        has_operators = any(k.startswith("$") for k in update)
        if not has_operators:
            _id = doc.get("_id")
            doc = update.copy()
            if _id:
                doc["_id"] = _id

        return doc

    # ------------------------------------------------------------------
    # Aggregation stage helpers
    # ------------------------------------------------------------------

    def _execute_group(self, docs: list, group_spec: dict) -> list:
        """Execute a ``$group`` aggregation stage in-memory."""
        group_key = group_spec["_id"]
        accumulators = {
            k: v for k, v in group_spec.items() if k != "_id"
        }

        groups: Dict[Any, list] = {}
        for doc in docs:
            if group_key is None:
                key = None
            elif isinstance(group_key, str) and group_key.startswith("$"):
                key = self._get_nested(doc, group_key[1:])
            elif isinstance(group_key, dict):
                key = tuple(
                    (k, self._get_nested(doc, v[1:]) if isinstance(v, str) and v.startswith("$") else v)
                    for k, v in group_key.items()
                )
            else:
                key = group_key
            groups.setdefault(key, []).append(doc)

        results = []
        for key, group_docs in groups.items():
            result: Dict[str, Any] = {}
            if isinstance(key, tuple):
                result["_id"] = dict(key)
            else:
                result["_id"] = key

            for acc_field, acc_spec in accumulators.items():
                if isinstance(acc_spec, dict):
                    op = list(acc_spec.keys())[0]
                    field_ref = acc_spec[op]
                    values = self._extract_field_values(group_docs, field_ref)

                    if op == "$sum":
                        if isinstance(field_ref, (int, float)):
                            result[acc_field] = field_ref * len(group_docs)
                        else:
                            result[acc_field] = sum(
                                v for v in values if isinstance(v, (int, float))
                            )
                    elif op == "$avg":
                        nums = [v for v in values if isinstance(v, (int, float))]
                        result[acc_field] = (
                            sum(nums) / len(nums) if nums else 0
                        )
                    elif op == "$min":
                        nums = [v for v in values if v is not None]
                        result[acc_field] = min(nums) if nums else None
                    elif op == "$max":
                        nums = [v for v in values if v is not None]
                        result[acc_field] = max(nums) if nums else None
                    elif op == "$first":
                        result[acc_field] = values[0] if values else None
                    elif op == "$last":
                        result[acc_field] = values[-1] if values else None
                    elif op == "$push":
                        result[acc_field] = values
                    elif op == "$addToSet":
                        seen = []
                        for v in values:
                            if v not in seen:
                                seen.append(v)
                        result[acc_field] = seen
                    else:
                        raise NotImplementedError(
                            f"Unsupported accumulator: {op}"
                        )
                else:
                    result[acc_field] = acc_spec

            results.append(result)
        return results

    def _execute_unwind(self, docs: list, unwind_spec) -> list:
        """Execute a ``$unwind`` aggregation stage."""
        if isinstance(unwind_spec, str):
            field = unwind_spec.lstrip("$")
            preserve_null = False
        else:
            field = unwind_spec["path"].lstrip("$")
            preserve_null = unwind_spec.get("preserveNullAndEmptyArrays", False)

        results = []
        for doc in docs:
            arr = self._get_nested(doc, field)
            if arr is None or (isinstance(arr, list) and len(arr) == 0):
                if preserve_null:
                    results.append(doc)
                continue
            if not isinstance(arr, list):
                new_doc = doc.copy()
                self._set_nested(new_doc, field, arr)
                results.append(new_doc)
                continue
            for item in arr:
                new_doc = doc.copy()
                self._set_nested(new_doc, field, item)
                results.append(new_doc)
        return results

    # ------------------------------------------------------------------
    # Utility: nested field access
    # ------------------------------------------------------------------

    @staticmethod
    def _get_nested(doc: Any, field: str) -> Any:
        """Resolve a dot-notation field path against a document."""
        if doc is None:
            return None
        parts = field.split(".")
        current = doc
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current

    @staticmethod
    def _set_nested(doc: dict, field: str, value: Any) -> None:
        """Set a dot-notation field path in a document."""
        parts = field.split(".")
        current = doc
        for part in parts[:-1]:
            if part not in current or not isinstance(current.get(part), dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    @staticmethod
    def _unset_nested(doc: dict, field: str) -> None:
        """Remove a dot-notation field path from a document."""
        parts = field.split(".")
        current = doc
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                return
            current = current[part]
        if isinstance(current, dict):
            current.pop(parts[-1], None)

    # ------------------------------------------------------------------
    # Utility: in-memory document matching (for aggregate $match, $pull)
    # ------------------------------------------------------------------

    def _doc_matches(self, doc: dict, filter: dict) -> bool:
        """Check whether *doc* matches a MongoDB-style filter in-memory."""
        for key, condition in filter.items():
            if key == "$and":
                if not all(self._doc_matches(doc, f) for f in condition):
                    return False
            elif key == "$or":
                if not any(self._doc_matches(doc, f) for f in condition):
                    return False
            elif key == "$nor":
                if any(self._doc_matches(doc, f) for f in condition):
                    return False
            elif isinstance(condition, dict) and any(
                k.startswith("$") for k in condition
            ):
                val = self._get_nested(doc, key)
                if not self._value_matches_operators(val, condition):
                    return False
            else:
                val = self._get_nested(doc, key)
                if val != condition:
                    return False
        return True

    def _value_matches_operators(self, val: Any, ops: dict) -> bool:
        """Check if *val* satisfies MongoDB comparison operators."""
        for op, expected in ops.items():
            if op == "$eq" and val != expected:
                return False
            elif op == "$ne" and val == expected:
                return False
            elif op == "$gt" and (val is None or val <= expected):
                return False
            elif op == "$gte" and (val is None or val < expected):
                return False
            elif op == "$lt" and (val is None or val >= expected):
                return False
            elif op == "$lte" and (val is None or val > expected):
                return False
            elif op == "$in" and val not in expected:
                return False
            elif op == "$nin" and val in expected:
                return False
            elif op == "$exists":
                if expected and val is None:
                    return False
                if not expected and val is not None:
                    return False
            elif op == "$regex":
                options = ops.get("$options", "")
                flags = re.IGNORECASE if "i" in options else 0
                if val is None or not re.search(expected, str(val), flags):
                    return False
            elif op == "$not":
                if self._value_matches_operators(val, expected):
                    return False
            elif op == "$options":
                pass
        return True

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def _extract_field_values(self, docs: list, field_ref) -> list:
        """Extract values for an accumulator field reference like ``"$price"``."""
        if isinstance(field_ref, str) and field_ref.startswith("$"):
            return [self._get_nested(d, field_ref[1:]) for d in docs]
        return [field_ref for _ in docs]

    @staticmethod
    def _bind_value(val: Any) -> Any:
        """Convert a Python value into a SQLite-compatible bind parameter."""
        if isinstance(val, bool):
            return int(val)
        if isinstance(val, (int, float)):
            return val
        if val is None:
            return None
        return str(val)

    @staticmethod
    def _regex_to_like(pattern: str) -> str:
        """Best-effort conversion of a simple regex pattern to a SQL LIKE pattern."""
        # Handle common MongoDB regex patterns
        like = pattern
        like = like.replace(".*", "%")
        like = like.replace(".+", "_%")
        like = like.replace(".", "_")
        # Anchors
        if like.startswith("^"):
            like = like[1:]
        else:
            like = "%" + like
        if like.endswith("$"):
            like = like[:-1]
        else:
            like = like + "%"
        return like
