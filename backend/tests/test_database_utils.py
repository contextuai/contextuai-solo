"""
Tests for database utility modules: SQLiteAdapter static helpers,
database_factory singleton, and motor_compat helpers.
"""

import asyncio
import os
import sys
import tempfile

import pytest
import pytest_asyncio

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from adapters.sqlite_adapter import SQLiteAdapter
from adapters.motor_compat import (
    _normalize_filter,
    _deep_convert,
    _apply_projection as mc_apply_projection,
)
from bson import ObjectId


# =====================================================================
# 1. database_factory.py
# =====================================================================


class TestDatabaseFactory:
    """Test get_database_adapter / close_database_adapter singleton."""

    @pytest.mark.asyncio
    async def test_get_database_adapter_returns_sqlite_adapter(self, tmp_path):
        """get_database_adapter() returns a SQLiteAdapter instance."""
        import database_factory as df

        # Reset global state
        df._adapter = None

        # Patch SQLiteAdapter to use a temp path
        original_init = SQLiteAdapter.__init__

        def patched_init(self, db_path=None):
            original_init(self, db_path=str(tmp_path / "test.db"))

        SQLiteAdapter.__init__ = patched_init
        try:
            adapter = await df.get_database_adapter()
            assert isinstance(adapter, SQLiteAdapter)
        finally:
            SQLiteAdapter.__init__ = original_init
            await df.close_database_adapter()

    @pytest.mark.asyncio
    async def test_get_database_adapter_singleton(self, tmp_path):
        """Calling get_database_adapter twice returns the same instance."""
        import database_factory as df

        df._adapter = None
        original_init = SQLiteAdapter.__init__

        def patched_init(self, db_path=None):
            original_init(self, db_path=str(tmp_path / "test.db"))

        SQLiteAdapter.__init__ = patched_init
        try:
            a1 = await df.get_database_adapter()
            a2 = await df.get_database_adapter()
            assert a1 is a2
        finally:
            SQLiteAdapter.__init__ = original_init
            await df.close_database_adapter()

    @pytest.mark.asyncio
    async def test_close_database_adapter_sets_none(self, tmp_path):
        """close_database_adapter() sets _adapter to None."""
        import database_factory as df

        df._adapter = None
        original_init = SQLiteAdapter.__init__

        def patched_init(self, db_path=None):
            original_init(self, db_path=str(tmp_path / "test.db"))

        SQLiteAdapter.__init__ = patched_init
        try:
            await df.get_database_adapter()
            assert df._adapter is not None
            await df.close_database_adapter()
            assert df._adapter is None
        finally:
            SQLiteAdapter.__init__ = original_init


# =====================================================================
# 2. SQLiteAdapter static/private helpers
# =====================================================================


class TestSafeTableName:
    def test_hyphens_replaced(self):
        assert SQLiteAdapter._safe_table_name("my-collection") == "my_collection"

    def test_normal_name_unchanged(self):
        assert SQLiteAdapter._safe_table_name("normal_name") == "normal_name"

    def test_dots_replaced(self):
        assert SQLiteAdapter._safe_table_name("a.b.c") == "a_b_c"

    def test_spaces_replaced(self):
        assert SQLiteAdapter._safe_table_name("my collection") == "my_collection"


class TestFieldToJsonPath:
    def test_dotted_field(self):
        assert SQLiteAdapter._field_to_json_path("user.name") == "$.user.name"

    def test_underscore_id(self):
        assert SQLiteAdapter._field_to_json_path("_id") == "$._id"

    def test_simple_field(self):
        assert SQLiteAdapter._field_to_json_path("status") == "$.status"


class TestGetNested:
    def test_deep_nested(self):
        doc = {"a": {"b": {"c": 42}}}
        assert SQLiteAdapter._get_nested(doc, "a.b.c") == 42

    def test_array_index(self):
        doc = {"arr": [10, 20, 30]}
        assert SQLiteAdapter._get_nested(doc, "arr.0") == 10
        assert SQLiteAdapter._get_nested(doc, "arr.2") == 30

    def test_none_doc(self):
        assert SQLiteAdapter._get_nested(None, "a") is None

    def test_missing_key(self):
        doc = {"a": 1}
        assert SQLiteAdapter._get_nested(doc, "b") is None

    def test_missing_deep_key(self):
        doc = {"a": {"b": 1}}
        assert SQLiteAdapter._get_nested(doc, "a.c.d") is None

    def test_array_index_out_of_range(self):
        doc = {"arr": [1, 2]}
        assert SQLiteAdapter._get_nested(doc, "arr.5") is None


class TestSetNested:
    def test_creates_intermediate_dicts(self):
        doc = {}
        SQLiteAdapter._set_nested(doc, "a.b", 99)
        assert doc == {"a": {"b": 99}}

    def test_set_top_level(self):
        doc = {"x": 1}
        SQLiteAdapter._set_nested(doc, "x", 2)
        assert doc == {"x": 2}

    def test_overwrites_existing_nested(self):
        doc = {"a": {"b": 1}}
        SQLiteAdapter._set_nested(doc, "a.b", 2)
        assert doc["a"]["b"] == 2

    def test_creates_deep_path(self):
        doc = {}
        SQLiteAdapter._set_nested(doc, "a.b.c.d", "deep")
        assert doc == {"a": {"b": {"c": {"d": "deep"}}}}


class TestUnsetNested:
    def test_removes_nested_key(self):
        doc = {"a": {"b": 1, "c": 2}}
        SQLiteAdapter._unset_nested(doc, "a.b")
        assert doc == {"a": {"c": 2}}

    def test_nonexistent_key_no_error(self):
        doc = {"a": 1}
        SQLiteAdapter._unset_nested(doc, "nonexistent.key")
        assert doc == {"a": 1}

    def test_removes_top_level(self):
        doc = {"a": 1, "b": 2}
        SQLiteAdapter._unset_nested(doc, "a")
        assert doc == {"b": 2}

    def test_deeply_nonexistent(self):
        doc = {"a": {"b": 1}}
        SQLiteAdapter._unset_nested(doc, "x.y.z")
        assert doc == {"a": {"b": 1}}


class TestBindValue:
    def test_bool_true(self):
        assert SQLiteAdapter._bind_value(True) == 1
        assert isinstance(SQLiteAdapter._bind_value(True), int)

    def test_bool_false(self):
        assert SQLiteAdapter._bind_value(False) == 0
        assert isinstance(SQLiteAdapter._bind_value(False), int)

    def test_int(self):
        assert SQLiteAdapter._bind_value(42) == 42

    def test_float(self):
        assert SQLiteAdapter._bind_value(3.14) == 3.14

    def test_string(self):
        assert SQLiteAdapter._bind_value("hello") == "hello"

    def test_none(self):
        assert SQLiteAdapter._bind_value(None) is None

    def test_object_id_becomes_string(self):
        oid = ObjectId()
        result = SQLiteAdapter._bind_value(oid)
        assert result == str(oid)


class TestRegexToLike:
    def test_caret_anchor(self):
        assert SQLiteAdapter._regex_to_like("^hello") == "hello%"

    def test_dollar_anchor(self):
        assert SQLiteAdapter._regex_to_like("world$") == "%world"

    def test_both_anchors(self):
        assert SQLiteAdapter._regex_to_like("^hello$") == "hello"

    def test_dot_star(self):
        result = SQLiteAdapter._regex_to_like("he.*llo")
        assert result == "%he%llo%"

    def test_single_dot(self):
        result = SQLiteAdapter._regex_to_like("h.llo")
        assert result == "%h_llo%"

    def test_no_anchors(self):
        result = SQLiteAdapter._regex_to_like("mid")
        assert result == "%mid%"


class TestApplyProjection:
    def test_inclusion(self):
        doc = {"_id": "1", "name": "Alice", "age": 30, "email": "a@b.c"}
        result = SQLiteAdapter._apply_projection(doc, {"name": 1})
        assert result == {"_id": "1", "name": "Alice"}

    def test_exclusion(self):
        doc = {"_id": "1", "name": "Alice", "password": "secret"}
        result = SQLiteAdapter._apply_projection(doc, {"password": 0})
        assert "password" not in result
        assert result["name"] == "Alice"
        assert result["_id"] == "1"

    def test_exclude_id_with_inclusion(self):
        doc = {"_id": "1", "name": "Alice", "age": 30}
        result = SQLiteAdapter._apply_projection(doc, {"_id": 0, "name": 1})
        assert result == {"name": "Alice"}

    def test_empty_projection(self):
        doc = {"_id": "1", "name": "Alice"}
        result = SQLiteAdapter._apply_projection(doc, {})
        assert result == doc

    def test_none_projection(self):
        doc = {"_id": "1", "name": "Alice"}
        result = SQLiteAdapter._apply_projection(doc, None)
        assert result == doc


class TestApplyUpdateOperators:
    """Test _apply_update_operators (instance method, but no DB needed)."""

    def _adapter(self):
        """Create an uninitialized adapter (no DB connection needed for these tests)."""
        adapter = object.__new__(SQLiteAdapter)
        return adapter

    def test_set(self):
        doc = {"_id": "1", "a": 0}
        result = self._adapter()._apply_update_operators(doc, {"$set": {"a": 1}})
        assert result["a"] == 1

    def test_set_nested(self):
        doc = {"_id": "1"}
        result = self._adapter()._apply_update_operators(doc, {"$set": {"a.b": 99}})
        assert result["a"]["b"] == 99

    def test_inc(self):
        doc = {"_id": "1", "count": 10}
        result = self._adapter()._apply_update_operators(doc, {"$inc": {"count": 5}})
        assert result["count"] == 15

    def test_inc_missing_field(self):
        doc = {"_id": "1"}
        result = self._adapter()._apply_update_operators(doc, {"$inc": {"count": 5}})
        assert result["count"] == 5

    def test_push(self):
        doc = {"_id": "1", "tags": ["a", "b"]}
        result = self._adapter()._apply_update_operators(doc, {"$push": {"tags": "new"}})
        assert result["tags"] == ["a", "b", "new"]

    def test_push_creates_list(self):
        doc = {"_id": "1"}
        result = self._adapter()._apply_update_operators(doc, {"$push": {"tags": "first"}})
        assert result["tags"] == ["first"]

    def test_pull(self):
        doc = {"_id": "1", "tags": ["a", "old", "b"]}
        result = self._adapter()._apply_update_operators(doc, {"$pull": {"tags": "old"}})
        assert result["tags"] == ["a", "b"]

    def test_pull_missing_value(self):
        doc = {"_id": "1", "tags": ["a", "b"]}
        result = self._adapter()._apply_update_operators(doc, {"$pull": {"tags": "nonexistent"}})
        assert result["tags"] == ["a", "b"]

    def test_add_to_set_new(self):
        doc = {"_id": "1", "tags": ["a", "b"]}
        result = self._adapter()._apply_update_operators(doc, {"$addToSet": {"tags": "unique"}})
        assert "unique" in result["tags"]
        assert len(result["tags"]) == 3

    def test_add_to_set_duplicate(self):
        doc = {"_id": "1", "tags": ["a", "b"]}
        result = self._adapter()._apply_update_operators(doc, {"$addToSet": {"tags": "a"}})
        assert result["tags"] == ["a", "b"]

    def test_unset(self):
        doc = {"_id": "1", "temp": "val", "keep": "yes"}
        result = self._adapter()._apply_update_operators(doc, {"$unset": {"temp": ""}})
        assert "temp" not in result
        assert result["keep"] == "yes"

    def test_min_lower(self):
        doc = {"_id": "1", "score": 10}
        result = self._adapter()._apply_update_operators(doc, {"$min": {"score": 5}})
        assert result["score"] == 5

    def test_min_higher(self):
        doc = {"_id": "1", "score": 10}
        result = self._adapter()._apply_update_operators(doc, {"$min": {"score": 20}})
        assert result["score"] == 10

    def test_max_higher(self):
        doc = {"_id": "1", "score": 10}
        result = self._adapter()._apply_update_operators(doc, {"$max": {"score": 100}})
        assert result["score"] == 100

    def test_max_lower(self):
        doc = {"_id": "1", "score": 10}
        result = self._adapter()._apply_update_operators(doc, {"$max": {"score": 3}})
        assert result["score"] == 10

    def test_replacement_update(self):
        doc = {"_id": "1", "old": "field"}
        result = self._adapter()._apply_update_operators(doc, {"name": "new"})
        assert result["name"] == "new"
        assert result["_id"] == "1"
        assert "old" not in result

    def test_replacement_preserves_id(self):
        doc = {"_id": "abc", "x": 1}
        result = self._adapter()._apply_update_operators(doc, {"y": 2})
        assert result["_id"] == "abc"
        assert result["y"] == 2


class TestDocMatches:
    """Test _doc_matches (in-memory document matching)."""

    def _adapter(self):
        adapter = object.__new__(SQLiteAdapter)
        return adapter

    def test_simple_equality(self):
        a = self._adapter()
        assert a._doc_matches({"name": "Alice"}, {"name": "Alice"}) is True
        assert a._doc_matches({"name": "Bob"}, {"name": "Alice"}) is False

    def test_nested_field(self):
        a = self._adapter()
        doc = {"user": {"age": 25}}
        assert a._doc_matches(doc, {"user.age": 25}) is True
        assert a._doc_matches(doc, {"user.age": 30}) is False

    def test_and_operator(self):
        a = self._adapter()
        doc = {"a": 1, "b": 2}
        assert a._doc_matches(doc, {"$and": [{"a": 1}, {"b": 2}]}) is True
        assert a._doc_matches(doc, {"$and": [{"a": 1}, {"b": 3}]}) is False

    def test_or_operator(self):
        a = self._adapter()
        doc = {"a": 1}
        assert a._doc_matches(doc, {"$or": [{"a": 1}, {"a": 2}]}) is True
        assert a._doc_matches(doc, {"$or": [{"a": 2}, {"a": 3}]}) is False

    def test_nor_operator(self):
        a = self._adapter()
        doc = {"a": 1}
        assert a._doc_matches(doc, {"$nor": [{"a": 2}, {"a": 3}]}) is True
        assert a._doc_matches(doc, {"$nor": [{"a": 1}, {"a": 2}]}) is False

    def test_comparison_operators(self):
        a = self._adapter()
        doc = {"score": 50}
        assert a._doc_matches(doc, {"score": {"$gt": 40}}) is True
        assert a._doc_matches(doc, {"score": {"$gt": 60}}) is False
        assert a._doc_matches(doc, {"score": {"$gte": 50}}) is True
        assert a._doc_matches(doc, {"score": {"$lt": 60}}) is True
        assert a._doc_matches(doc, {"score": {"$lte": 50}}) is True


class TestValueMatchesOperators:
    """Test _value_matches_operators."""

    def _adapter(self):
        return object.__new__(SQLiteAdapter)

    def test_eq(self):
        a = self._adapter()
        assert a._value_matches_operators(5, {"$eq": 5}) is True
        assert a._value_matches_operators(5, {"$eq": 6}) is False

    def test_ne(self):
        a = self._adapter()
        assert a._value_matches_operators(5, {"$ne": 6}) is True
        assert a._value_matches_operators(5, {"$ne": 5}) is False

    def test_gt_gte(self):
        a = self._adapter()
        assert a._value_matches_operators(10, {"$gt": 5}) is True
        assert a._value_matches_operators(10, {"$gt": 10}) is False
        assert a._value_matches_operators(10, {"$gte": 10}) is True

    def test_lt_lte(self):
        a = self._adapter()
        assert a._value_matches_operators(5, {"$lt": 10}) is True
        assert a._value_matches_operators(5, {"$lt": 5}) is False
        assert a._value_matches_operators(5, {"$lte": 5}) is True

    def test_in(self):
        a = self._adapter()
        assert a._value_matches_operators("a", {"$in": ["a", "b"]}) is True
        assert a._value_matches_operators("c", {"$in": ["a", "b"]}) is False

    def test_nin(self):
        a = self._adapter()
        assert a._value_matches_operators("c", {"$nin": ["a", "b"]}) is True
        assert a._value_matches_operators("a", {"$nin": ["a", "b"]}) is False

    def test_exists(self):
        a = self._adapter()
        assert a._value_matches_operators("val", {"$exists": True}) is True
        assert a._value_matches_operators(None, {"$exists": True}) is False
        assert a._value_matches_operators(None, {"$exists": False}) is True
        assert a._value_matches_operators("val", {"$exists": False}) is False

    def test_regex(self):
        a = self._adapter()
        assert a._value_matches_operators("hello world", {"$regex": "hello"}) is True
        assert a._value_matches_operators("goodbye", {"$regex": "hello"}) is False

    def test_regex_case_insensitive(self):
        a = self._adapter()
        assert a._value_matches_operators(
            "Hello", {"$regex": "hello", "$options": "i"}
        ) is True

    def test_none_with_comparison(self):
        a = self._adapter()
        assert a._value_matches_operators(None, {"$gt": 5}) is False
        assert a._value_matches_operators(None, {"$lt": 5}) is False

    def test_not_operator(self):
        a = self._adapter()
        assert a._value_matches_operators(5, {"$not": {"$gt": 10}}) is True
        assert a._value_matches_operators(15, {"$not": {"$gt": 10}}) is False


# =====================================================================
# 3. motor_compat helpers
# =====================================================================


class TestNormalizeFilter:
    def test_none_returns_empty_dict(self):
        assert _normalize_filter(None) == {}

    def test_object_id_converted(self):
        oid = ObjectId()
        result = _normalize_filter({"_id": oid})
        assert result == {"_id": str(oid)}
        assert isinstance(result["_id"], str)

    def test_plain_dict_unchanged(self):
        f = {"status": "active", "count": 5}
        assert _normalize_filter(f) == f

    def test_nested_object_id(self):
        oid = ObjectId()
        f = {"_id": {"$in": [oid]}}
        result = _normalize_filter(f)
        assert result == {"_id": {"$in": [str(oid)]}}


class TestDeepConvert:
    def test_object_id(self):
        oid = ObjectId()
        assert _deep_convert(oid) == str(oid)

    def test_nested_dict(self):
        oid = ObjectId()
        result = _deep_convert({"a": {"b": oid}})
        assert result == {"a": {"b": str(oid)}}

    def test_list(self):
        oid = ObjectId()
        result = _deep_convert([oid, "plain", 42])
        assert result == [str(oid), "plain", 42]

    def test_tuple(self):
        oid = ObjectId()
        result = _deep_convert((oid, "plain"))
        assert result == (str(oid), "plain")
        assert isinstance(result, tuple)

    def test_plain_values(self):
        assert _deep_convert("hello") == "hello"
        assert _deep_convert(42) == 42
        assert _deep_convert(None) is None
        assert _deep_convert(True) is True


class TestMotorCompatApplyProjection:
    def test_inclusion(self):
        doc = {"_id": "1", "name": "Alice", "age": 30, "email": "a@b.c"}
        result = mc_apply_projection(doc, {"name": 1})
        assert result == {"_id": "1", "name": "Alice"}

    def test_exclusion(self):
        doc = {"_id": "1", "name": "Alice", "password": "secret"}
        result = mc_apply_projection(doc, {"password": 0})
        assert "password" not in result
        assert result["name"] == "Alice"
        assert result["_id"] == "1"

    def test_exclude_id(self):
        doc = {"_id": "1", "name": "Alice", "age": 30}
        result = mc_apply_projection(doc, {"_id": 0, "name": 1})
        assert "_id" not in result
        assert result == {"name": "Alice"}

    def test_none_projection_returns_doc(self):
        doc = {"_id": "1", "name": "Alice"}
        result = mc_apply_projection(doc, None)
        assert result == doc

    def test_none_doc_returns_none(self):
        result = mc_apply_projection(None, {"name": 1})
        assert result is None

    def test_none_both(self):
        result = mc_apply_projection(None, None)
        assert result is None

    def test_inclusion_with_bool_true(self):
        doc = {"_id": "1", "name": "Alice", "age": 30}
        result = mc_apply_projection(doc, {"name": True})
        assert result == {"_id": "1", "name": "Alice"}

    def test_exclusion_with_bool_false(self):
        doc = {"_id": "1", "name": "Alice", "password": "secret"}
        result = mc_apply_projection(doc, {"password": False})
        assert "password" not in result
        assert result["name"] == "Alice"
