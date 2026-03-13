"""
Comprehensive tests for the Motor compatibility layer.

Tests DatabaseProxy, CollectionProxy, CursorProxy, _AggregationCursorProxy,
result dataclasses, and helper functions (_normalize_filter, _apply_projection).
"""

import pytest
import pytest_asyncio
from bson import ObjectId

from adapters.motor_compat import (
    CollectionProxy,
    CursorProxy,
    DatabaseProxy,
    DeleteResult,
    InsertManyResult,
    InsertOneResult,
    UpdateResult,
    _apply_projection,
    _normalize_filter,
)


# ---- Convenience fixture for a named collection ----------------------------

@pytest_asyncio.fixture
async def col(db_proxy: DatabaseProxy) -> CollectionProxy:
    """Return a CollectionProxy for a test collection, cleaned after use."""
    c = db_proxy["test_col"]
    yield c
    await c.delete_many({})


# ===========================================================================
# 1. DatabaseProxy
# ===========================================================================


class TestDatabaseProxy:
    """db['name'] and db.name access, private attr guard."""

    @pytest.mark.asyncio
    async def test_getitem_returns_collection_proxy(self, db_proxy):
        col = db_proxy["widgets"]
        assert isinstance(col, CollectionProxy)

    @pytest.mark.asyncio
    async def test_getattr_returns_collection_proxy(self, db_proxy):
        col = db_proxy.widgets
        assert isinstance(col, CollectionProxy)

    @pytest.mark.asyncio
    async def test_private_attr_raises(self, db_proxy):
        with pytest.raises(AttributeError):
            _ = db_proxy._private

    @pytest.mark.asyncio
    async def test_dunder_attr_raises(self, db_proxy):
        with pytest.raises(AttributeError):
            _ = db_proxy.__missing__

    @pytest.mark.asyncio
    async def test_different_names_yield_distinct_proxies(self, db_proxy):
        a = db_proxy["alpha"]
        b = db_proxy["beta"]
        assert a._collection != b._collection


# ===========================================================================
# 2. insert_one
# ===========================================================================


class TestInsertOne:

    @pytest.mark.asyncio
    async def test_returns_insert_one_result(self, col):
        result = await col.insert_one({"name": "Alice"})
        assert isinstance(result, InsertOneResult)
        assert isinstance(result.inserted_id, str)
        assert len(result.inserted_id) > 0

    @pytest.mark.asyncio
    async def test_document_retrievable_after_insert(self, col):
        result = await col.insert_one({"key": "value1"})
        doc = await col.find_one({"_id": result.inserted_id})
        assert doc is not None
        assert doc["key"] == "value1"

    @pytest.mark.asyncio
    async def test_insert_with_explicit_id(self, col):
        custom_id = "my-custom-id-123"
        result = await col.insert_one({"_id": custom_id, "x": 1})
        assert result.inserted_id == custom_id
        doc = await col.find_one({"_id": custom_id})
        assert doc["x"] == 1


# ===========================================================================
# 3. insert_many
# ===========================================================================


class TestInsertMany:

    @pytest.mark.asyncio
    async def test_returns_insert_many_result(self, col):
        docs = [{"i": 1}, {"i": 2}, {"i": 3}]
        result = await col.insert_many(docs)
        assert isinstance(result, InsertManyResult)
        assert len(result.inserted_ids) == 3

    @pytest.mark.asyncio
    async def test_all_documents_stored(self, col):
        docs = [{"val": n} for n in range(5)]
        await col.insert_many(docs)
        count = await col.count_documents({})
        assert count == 5


# ===========================================================================
# 4. find_one
# ===========================================================================


class TestFindOne:

    @pytest.mark.asyncio
    async def test_find_one_with_filter(self, col):
        await col.insert_many([{"name": "a"}, {"name": "b"}])
        doc = await col.find_one({"name": "b"})
        assert doc is not None
        assert doc["name"] == "b"

    @pytest.mark.asyncio
    async def test_find_one_returns_none_when_missing(self, col):
        doc = await col.find_one({"name": "nonexistent"})
        assert doc is None

    @pytest.mark.asyncio
    async def test_find_one_with_inclusion_projection(self, col):
        await col.insert_one({"name": "proj", "secret": "hidden", "age": 30})
        doc = await col.find_one({"name": "proj"}, projection={"name": 1})
        assert "name" in doc
        assert "_id" in doc  # _id included by default
        assert "secret" not in doc
        assert "age" not in doc

    @pytest.mark.asyncio
    async def test_find_one_with_exclusion_projection(self, col):
        await col.insert_one({"name": "proj2", "secret": "hidden", "age": 25})
        doc = await col.find_one({"name": "proj2"}, projection={"secret": 0})
        assert "name" in doc
        assert "secret" not in doc
        assert "age" in doc

    @pytest.mark.asyncio
    async def test_find_one_projection_exclude_id(self, col):
        await col.insert_one({"name": "no_id", "val": 1})
        doc = await col.find_one({"name": "no_id"}, projection={"name": 1, "_id": 0})
        assert "_id" not in doc
        assert doc["name"] == "no_id"

    @pytest.mark.asyncio
    async def test_find_one_no_filter(self, col):
        await col.insert_one({"solo": True})
        doc = await col.find_one()
        assert doc is not None


# ===========================================================================
# 5. find() — CursorProxy with sort / skip / limit / to_list
# ===========================================================================


class TestFind:

    @pytest.mark.asyncio
    async def test_returns_cursor_proxy(self, col):
        cursor = col.find({})
        assert isinstance(cursor, CursorProxy)

    @pytest.mark.asyncio
    async def test_to_list_returns_all_docs(self, col):
        await col.insert_many([{"v": 1}, {"v": 2}, {"v": 3}])
        docs = await col.find({}).to_list(length=100)
        assert len(docs) == 3

    @pytest.mark.asyncio
    async def test_sort_ascending(self, col):
        await col.insert_many([{"n": 3}, {"n": 1}, {"n": 2}])
        docs = await col.find({}).sort([("n", 1)]).to_list(length=100)
        values = [d["n"] for d in docs]
        assert values == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_sort_descending(self, col):
        await col.insert_many([{"n": 3}, {"n": 1}, {"n": 2}])
        docs = await col.find({}).sort([("n", -1)]).to_list(length=100)
        values = [d["n"] for d in docs]
        assert values == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_sort_with_string_key(self, col):
        await col.insert_many([{"n": 2}, {"n": 1}])
        docs = await col.find({}).sort("n", 1).to_list(length=100)
        assert docs[0]["n"] == 1

    @pytest.mark.asyncio
    async def test_skip(self, col):
        await col.insert_many([{"n": i} for i in range(5)])
        docs = await col.find({}).sort([("n", 1)]).skip(3).to_list(length=100)
        assert len(docs) == 2
        assert docs[0]["n"] == 3

    @pytest.mark.asyncio
    async def test_limit(self, col):
        await col.insert_many([{"n": i} for i in range(5)])
        docs = await col.find({}).sort([("n", 1)]).limit(2).to_list(length=100)
        assert len(docs) == 2
        assert docs[0]["n"] == 0
        assert docs[1]["n"] == 1

    @pytest.mark.asyncio
    async def test_skip_and_limit_chained(self, col):
        await col.insert_many([{"n": i} for i in range(10)])
        docs = await col.find({}).sort([("n", 1)]).skip(3).limit(4).to_list(length=100)
        values = [d["n"] for d in docs]
        assert values == [3, 4, 5, 6]

    @pytest.mark.asyncio
    async def test_find_with_projection(self, col):
        await col.insert_many([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        docs = await col.find({}, projection={"a": 1, "_id": 0}).to_list(length=100)
        for d in docs:
            assert "a" in d
            assert "_id" not in d
            assert "b" not in d

    @pytest.mark.asyncio
    async def test_find_with_filter(self, col):
        await col.insert_many([{"status": "active"}, {"status": "inactive"}])
        docs = await col.find({"status": "active"}).to_list(length=100)
        assert len(docs) == 1
        assert docs[0]["status"] == "active"


# ===========================================================================
# 6. update_one
# ===========================================================================


class TestUpdateOne:

    @pytest.mark.asyncio
    async def test_returns_update_result(self, col):
        await col.insert_one({"x": 1})
        result = await col.update_one({"x": 1}, {"$set": {"x": 2}})
        assert isinstance(result, UpdateResult)
        assert result.modified_count == 1
        assert result.matched_count == 1

    @pytest.mark.asyncio
    async def test_document_updated(self, col):
        await col.insert_one({"x": 10})
        await col.update_one({"x": 10}, {"$set": {"x": 20}})
        doc = await col.find_one({"x": 20})
        assert doc is not None

    @pytest.mark.asyncio
    async def test_update_one_no_match(self, col):
        result = await col.update_one({"x": "nonexistent"}, {"$set": {"x": 1}})
        assert result.modified_count == 0

    @pytest.mark.asyncio
    async def test_update_one_upsert(self, col):
        result = await col.update_one(
            {"label": "upserted"}, {"$set": {"label": "upserted", "v": 99}}, upsert=True
        )
        doc = await col.find_one({"label": "upserted"})
        assert doc is not None
        assert doc["v"] == 99


# ===========================================================================
# 7. update_many
# ===========================================================================


class TestUpdateMany:

    @pytest.mark.asyncio
    async def test_returns_update_result(self, col):
        await col.insert_many([{"status": "old"}, {"status": "old"}, {"status": "new"}])
        result = await col.update_many({"status": "old"}, {"$set": {"status": "migrated"}})
        assert isinstance(result, UpdateResult)
        assert result.modified_count == 2

    @pytest.mark.asyncio
    async def test_all_matching_documents_updated(self, col):
        await col.insert_many([{"g": "a"}, {"g": "a"}, {"g": "b"}])
        await col.update_many({"g": "a"}, {"$set": {"g": "z"}})
        remaining_a = await col.count_documents({"g": "a"})
        count_z = await col.count_documents({"g": "z"})
        assert remaining_a == 0
        assert count_z == 2


# ===========================================================================
# 8. find_one_and_update
# ===========================================================================


class TestFindOneAndUpdate:

    @pytest.mark.asyncio
    async def test_returns_updated_doc(self, col):
        await col.insert_one({"name": "counter", "n": 0})
        doc = await col.find_one_and_update(
            {"name": "counter"}, {"$set": {"n": 1}}, return_document=True
        )
        assert doc is not None
        assert doc["n"] == 1

    @pytest.mark.asyncio
    async def test_upsert_creates_document(self, col):
        doc = await col.find_one_and_update(
            {"name": "new_thing"},
            {"$set": {"name": "new_thing", "val": 42}},
            upsert=True,
            return_document=True,
        )
        assert doc is not None
        assert doc["val"] == 42
        # Verify it persisted
        found = await col.find_one({"name": "new_thing"})
        assert found is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match_no_upsert(self, col):
        doc = await col.find_one_and_update(
            {"name": "ghost"}, {"$set": {"val": 1}}, upsert=False
        )
        assert doc is None


# ===========================================================================
# 9. delete_one
# ===========================================================================


class TestDeleteOne:

    @pytest.mark.asyncio
    async def test_returns_delete_result(self, col):
        await col.insert_one({"del": True})
        result = await col.delete_one({"del": True})
        assert isinstance(result, DeleteResult)
        assert result.deleted_count == 1

    @pytest.mark.asyncio
    async def test_document_removed(self, col):
        res = await col.insert_one({"del_check": 1})
        await col.delete_one({"_id": res.inserted_id})
        assert await col.find_one({"_id": res.inserted_id}) is None

    @pytest.mark.asyncio
    async def test_delete_one_no_match(self, col):
        result = await col.delete_one({"no": "match"})
        assert result.deleted_count == 0


# ===========================================================================
# 10. delete_many
# ===========================================================================


class TestDeleteMany:

    @pytest.mark.asyncio
    async def test_returns_delete_result(self, col):
        await col.insert_many([{"t": "rm"}, {"t": "rm"}, {"t": "keep"}])
        result = await col.delete_many({"t": "rm"})
        assert isinstance(result, DeleteResult)
        assert result.deleted_count == 2

    @pytest.mark.asyncio
    async def test_remaining_docs_intact(self, col):
        await col.insert_many([{"t": "rm"}, {"t": "keep"}])
        await col.delete_many({"t": "rm"})
        remaining = await col.count_documents({})
        assert remaining == 1

    @pytest.mark.asyncio
    async def test_delete_all(self, col):
        await col.insert_many([{"a": 1}, {"a": 2}])
        result = await col.delete_many({})
        assert result.deleted_count == 2
        assert await col.count_documents({}) == 0


# ===========================================================================
# 11. count_documents
# ===========================================================================


class TestCountDocuments:

    @pytest.mark.asyncio
    async def test_count_empty_collection(self, col):
        count = await col.count_documents({})
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_all(self, col):
        await col.insert_many([{"x": 1}, {"x": 2}, {"x": 3}])
        assert await col.count_documents({}) == 3

    @pytest.mark.asyncio
    async def test_count_with_filter(self, col):
        await col.insert_many([{"color": "red"}, {"color": "red"}, {"color": "blue"}])
        assert await col.count_documents({"color": "red"}) == 2
        assert await col.count_documents({"color": "blue"}) == 1

    @pytest.mark.asyncio
    async def test_count_with_none_filter(self, col):
        await col.insert_many([{"a": 1}, {"a": 2}])
        assert await col.count_documents(None) == 2


# ===========================================================================
# 12. distinct
# ===========================================================================


class TestDistinct:

    @pytest.mark.asyncio
    async def test_distinct_values(self, col):
        await col.insert_many([
            {"color": "red"},
            {"color": "blue"},
            {"color": "red"},
            {"color": "green"},
        ])
        values = await col.distinct("color")
        assert set(values) == {"red", "blue", "green"}

    @pytest.mark.asyncio
    async def test_distinct_with_filter(self, col):
        await col.insert_many([
            {"type": "a", "val": 1},
            {"type": "a", "val": 2},
            {"type": "b", "val": 1},
        ])
        values = await col.distinct("val", filter={"type": "a"})
        assert set(values) == {1, 2}

    @pytest.mark.asyncio
    async def test_distinct_empty(self, col):
        values = await col.distinct("missing_field")
        assert values == []


# ===========================================================================
# 13. aggregate
# ===========================================================================


class TestAggregate:

    @pytest.mark.asyncio
    async def test_match_pipeline(self, col):
        await col.insert_many([
            {"status": "active", "v": 1},
            {"status": "active", "v": 2},
            {"status": "inactive", "v": 3},
        ])
        cursor = col.aggregate([{"$match": {"status": "active"}}])
        docs = await cursor.to_list(length=100)
        assert len(docs) == 2
        assert all(d["status"] == "active" for d in docs)

    @pytest.mark.asyncio
    async def test_aggregate_returns_cursor_proxy(self, col):
        cursor = col.aggregate([])
        # _AggregationCursorProxy is a subclass of CursorProxy
        assert isinstance(cursor, CursorProxy)

    @pytest.mark.asyncio
    async def test_aggregate_async_iteration(self, col):
        await col.insert_many([{"i": 1}, {"i": 2}])
        cursor = col.aggregate([{"$match": {}}])
        collected = []
        async for doc in cursor:
            collected.append(doc)
        assert len(collected) == 2

    @pytest.mark.asyncio
    async def test_aggregate_count(self, col):
        await col.insert_many([{"cat": "a"}, {"cat": "a"}, {"cat": "b"}])
        docs = await col.aggregate([
            {"$match": {"cat": "a"}},
            {"$count": "total"},
        ]).to_list(length=100)
        assert len(docs) == 1
        assert docs[0]["total"] == 2


# ===========================================================================
# 14. create_index
# ===========================================================================


class TestCreateIndex:

    @pytest.mark.asyncio
    async def test_create_index_returns_string(self, col):
        name = await col.create_index("some_field")
        assert isinstance(name, str)

    @pytest.mark.asyncio
    async def test_create_compound_index(self, col):
        name = await col.create_index([("field_a", 1), ("field_b", -1)])
        assert isinstance(name, str)

    @pytest.mark.asyncio
    async def test_create_index_idempotent(self, col):
        name1 = await col.create_index("repeat_field")
        name2 = await col.create_index("repeat_field")
        # Should not raise; both return a valid name
        assert isinstance(name1, str)
        assert isinstance(name2, str)


# ===========================================================================
# 15. CursorProxy — chaining and async iteration
# ===========================================================================


class TestCursorProxy:

    @pytest.mark.asyncio
    async def test_chaining_returns_same_cursor(self, col):
        cursor = col.find({})
        same = cursor.sort([("x", 1)]).skip(1).limit(5)
        assert same is cursor

    @pytest.mark.asyncio
    async def test_async_for_iteration(self, col):
        await col.insert_many([{"i": n} for n in range(4)])
        collected = []
        async for doc in col.find({}).sort([("i", 1)]):
            collected.append(doc["i"])
        assert collected == [0, 1, 2, 3]

    @pytest.mark.asyncio
    async def test_to_list_with_length_acts_as_limit(self, col):
        await col.insert_many([{"i": n} for n in range(10)])
        docs = await col.find({}).to_list(length=3)
        assert len(docs) <= 3

    @pytest.mark.asyncio
    async def test_to_list_no_length(self, col):
        await col.insert_many([{"i": n} for n in range(5)])
        docs = await col.find({}).to_list(length=None)
        assert len(docs) == 5

    @pytest.mark.asyncio
    async def test_empty_result(self, col):
        docs = await col.find({"nonexistent": True}).to_list(length=100)
        assert docs == []


# ===========================================================================
# 16. _normalize_filter
# ===========================================================================


class TestNormalizeFilter:

    def test_none_returns_empty_dict(self):
        assert _normalize_filter(None) == {}

    def test_plain_dict_unchanged(self):
        f = {"name": "test", "age": 30}
        assert _normalize_filter(f) == f

    def test_objectid_converted_to_string(self):
        oid = ObjectId()
        result = _normalize_filter({"_id": oid})
        assert result == {"_id": str(oid)}

    def test_nested_objectid_in_operator(self):
        oid1 = ObjectId()
        oid2 = ObjectId()
        result = _normalize_filter({"_id": {"$in": [oid1, oid2]}})
        assert result == {"_id": {"$in": [str(oid1), str(oid2)]}}

    def test_deeply_nested_objectid(self):
        oid = ObjectId()
        result = _normalize_filter({"a": {"b": {"c": oid}}})
        assert result == {"a": {"b": {"c": str(oid)}}}

    def test_tuple_preserved_as_tuple(self):
        oid = ObjectId()
        result = _normalize_filter({"ids": {"$in": (oid, "plain")}})
        expected = {"ids": {"$in": (str(oid), "plain")}}
        assert result == expected
        assert isinstance(result["ids"]["$in"], tuple)

    def test_non_objectid_values_untouched(self):
        f = {"count": 42, "flag": True, "name": "hello"}
        assert _normalize_filter(f) == f


# ===========================================================================
# 17. _apply_projection
# ===========================================================================


class TestApplyProjection:

    def test_none_doc_returns_none(self):
        assert _apply_projection(None, {"a": 1}) is None

    def test_none_projection_returns_doc(self):
        doc = {"a": 1, "b": 2}
        assert _apply_projection(doc, None) == doc

    def test_inclusion_projection(self):
        doc = {"_id": "1", "name": "Alice", "age": 30, "email": "a@b.c"}
        result = _apply_projection(doc, {"name": 1, "age": 1})
        assert result == {"_id": "1", "name": "Alice", "age": 30}

    def test_inclusion_projection_exclude_id(self):
        doc = {"_id": "1", "name": "Alice", "age": 30}
        result = _apply_projection(doc, {"name": 1, "_id": 0})
        assert result == {"name": "Alice"}

    def test_exclusion_projection(self):
        doc = {"_id": "1", "name": "Alice", "secret": "password"}
        result = _apply_projection(doc, {"secret": 0})
        assert result == {"_id": "1", "name": "Alice"}

    def test_exclusion_projection_with_id(self):
        doc = {"_id": "1", "a": 1, "b": 2}
        result = _apply_projection(doc, {"_id": 0, "b": 0})
        assert result == {"a": 1}

    def test_empty_projection_returns_doc(self):
        doc = {"_id": "1", "a": 1}
        assert _apply_projection(doc, {}) == doc

    def test_boolean_true_inclusion(self):
        doc = {"_id": "1", "x": 10, "y": 20}
        result = _apply_projection(doc, {"x": True})
        assert result == {"_id": "1", "x": 10}

    def test_boolean_false_exclusion(self):
        doc = {"_id": "1", "x": 10, "y": 20}
        result = _apply_projection(doc, {"y": False})
        assert result == {"_id": "1", "x": 10}


# ===========================================================================
# 18. Result dataclasses — field access
# ===========================================================================


class TestResultDataclasses:

    def test_insert_one_result(self):
        r = InsertOneResult(inserted_id="abc-123")
        assert r.inserted_id == "abc-123"

    def test_insert_many_result(self):
        ids = ["a", "b", "c"]
        r = InsertManyResult(inserted_ids=ids)
        assert r.inserted_ids == ids
        assert len(r.inserted_ids) == 3

    def test_update_result_defaults(self):
        r = UpdateResult(modified_count=5)
        assert r.modified_count == 5
        assert r.matched_count == 0  # default

    def test_update_result_with_matched(self):
        r = UpdateResult(modified_count=3, matched_count=3)
        assert r.matched_count == 3

    def test_delete_result(self):
        r = DeleteResult(deleted_count=7)
        assert r.deleted_count == 7

    def test_delete_result_zero(self):
        r = DeleteResult(deleted_count=0)
        assert r.deleted_count == 0
