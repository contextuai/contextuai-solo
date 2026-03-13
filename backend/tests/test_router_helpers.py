"""
Synchronous unit tests for pure helper functions and Pydantic models
from routers/chat_sessions.py, routers/chat_messages.py, routers/personas.py,
settings.py, and database.py.

No database, no async, no mocking of external services.
"""

import sys
import os
import re
import time
from datetime import datetime, timedelta

import pytest

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# chat_sessions helpers
# ---------------------------------------------------------------------------
from routers.chat_sessions import (
    calculate_expiry_date as session_calculate_expiry_date,
    create_session_dict,
    format_session_response,
    SessionCreate,
    SessionUpdate,
    SessionResponse,
)

# ---------------------------------------------------------------------------
# chat_messages helpers
# ---------------------------------------------------------------------------
from routers.chat_messages import (
    calculate_expiry_date as message_calculate_expiry_date,
    create_message_dict,
    format_message_response,
    MessageCreate,
    MessageUpdate,
    MessageResponse,
    MessageAttachment,
)

# ---------------------------------------------------------------------------
# personas models
# ---------------------------------------------------------------------------
from routers.personas import (
    Persona,
    PersonaResponse,
    TestConnectionRequest,
)

# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------
from settings import Settings

# ---------------------------------------------------------------------------
# database utility
# ---------------------------------------------------------------------------
from database import _mask_connection_string


# ============================================================================
#  chat_sessions: calculate_expiry_date
# ============================================================================

class TestSessionCalculateExpiryDate:
    """Tests for chat_sessions.calculate_expiry_date."""

    def test_default_30_days(self):
        result = session_calculate_expiry_date()
        ts = int(result)
        expected = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        assert abs(ts - expected) < 5

    def test_custom_days(self):
        result = session_calculate_expiry_date(days=7)
        ts = int(result)
        expected = int((datetime.utcnow() + timedelta(days=7)).timestamp())
        assert abs(ts - expected) < 5

    def test_returns_string(self):
        result = session_calculate_expiry_date()
        assert isinstance(result, str)

    def test_zero_days(self):
        """Zero-day expiry should be roughly now."""
        result = session_calculate_expiry_date(days=0)
        ts = int(result)
        now_ts = int(datetime.utcnow().timestamp())
        assert abs(ts - now_ts) < 5

    def test_large_days(self):
        result = session_calculate_expiry_date(days=365)
        ts = int(result)
        expected = int((datetime.utcnow() + timedelta(days=365)).timestamp())
        assert abs(ts - expected) < 5


# ============================================================================
#  chat_sessions: create_session_dict
# ============================================================================

class TestCreateSessionDict:

    def _make_session_data(self, **kwargs):
        return SessionCreate(**kwargs)

    def test_minimal_session(self):
        sd = self._make_session_data()
        result = create_session_dict("user-1", sd)

        assert result["user_id"] == "user-1"
        assert result["status"] == "active"
        assert result["message_count"] == 0
        assert result["is_favorite"] is False
        assert "session_id" in result
        assert result["created_at"].endswith("Z")
        assert result["updated_at"].endswith("Z")
        assert "expires_at" in result

    def test_custom_session_id(self):
        sd = self._make_session_data()
        result = create_session_dict("user-1", sd, session_id="custom-id")
        assert result["session_id"] == "custom-id"

    def test_auto_generated_session_id_is_uuid(self):
        import uuid
        sd = self._make_session_data()
        result = create_session_dict("user-1", sd)
        uuid.UUID(result["session_id"])  # raises if not valid uuid

    def test_optional_fields_included(self):
        sd = self._make_session_data(
            title="Test",
            description="A session",
            persona_id="p-1",
            model_id="m-1",
            tags=["a", "b"],
        )
        result = create_session_dict("user-1", sd)
        assert result["title"] == "Test"
        assert result["description"] == "A session"
        assert result["persona_id"] == "p-1"
        assert result["model_id"] == "m-1"
        assert result["tags"] == ["a", "b"]

    def test_optional_fields_absent_when_none(self):
        sd = self._make_session_data()
        result = create_session_dict("user-1", sd)
        assert "title" not in result
        assert "description" not in result
        assert "persona_id" not in result
        assert "model_id" not in result
        assert "tags" not in result

    def test_is_favorite_true(self):
        sd = self._make_session_data(is_favorite=True)
        result = create_session_dict("user-1", sd)
        assert result["is_favorite"] is True


# ============================================================================
#  chat_sessions: format_session_response
# ============================================================================

class TestFormatSessionResponse:

    @staticmethod
    def _sample_session(**overrides):
        base = {
            "session_id": "sid-1",
            "user_id": "uid-1",
            "title": "Hello",
            "description": "desc",
            "persona_id": "p-1",
            "model_id": "m-1",
            "tags": ["tag1"],
            "is_favorite": True,
            "message_count": 5,
            "last_message_at": "2025-01-01T00:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "expires_at": "9999999999",
            "status": "active",
        }
        base.update(overrides)
        return base

    def test_basic_format(self):
        r = format_session_response(self._sample_session())
        assert isinstance(r, SessionResponse)
        assert r.session_id == "sid-1"
        assert r.user_id == "uid-1"
        assert r.title == "Hello"
        assert r.is_favorite is True
        assert r.message_count == 5

    def test_fallback_to_id_field(self):
        """When session_id is missing, fall back to id."""
        item = self._sample_session()
        del item["session_id"]
        item["id"] = "from-id"
        r = format_session_response(item)
        assert r.session_id == "from-id"

    def test_defaults_when_fields_missing(self):
        minimal = {"user_id": "u1"}
        r = format_session_response(minimal)
        assert r.session_id == ""
        assert r.is_favorite is False
        assert r.message_count == 0
        assert r.status == "active"

    def test_message_count_cast_to_int(self):
        item = self._sample_session(message_count="42")
        r = format_session_response(item)
        assert r.message_count == 42


# ============================================================================
#  chat_sessions: title generation logic (regex / truncation)
#  We extract and test the pure transformation logic from
#  update_session_title_from_first_message without the async DB parts.
# ============================================================================

def _generate_title(first_message: str, max_length: int = 20) -> str:
    """
    Pure re-implementation of the title transformation logic from
    update_session_title_from_first_message, isolated for unit testing.
    """
    title = re.sub(r'@\w+\s*', '', first_message)

    title = re.sub(r'```[\s\S]*?```', '', title)
    title = re.sub(r'`[^`]+`', '', title)

    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    title = emoji_pattern.sub('', title)
    title = re.sub(r'[^\w\s\?\!\.\,\-\:\;\'\"]', '', title)

    title = " ".join(title.split()).strip()

    if not title or len(title.strip()) == 0:
        title = "New Chat"
    elif len(title) < 3:
        title = f"Chat: {title.capitalize()}"
    else:
        title = title[0].upper() + title[1:]

    if len(title) > max_length:
        ends_with_punctuation = title[-1] in '?!.'
        original_ending = title[-1] if ends_with_punctuation else ''

        truncated = title[:max_length].rsplit(' ', 1)[0]

        if ends_with_punctuation and len(truncated) + 4 <= max_length:
            title = truncated + "..." + original_ending
        else:
            title = truncated + "..."

    return title


class TestTitleGeneration:

    def test_removes_persona_mentions(self):
        assert "get data" in _generate_title("@sales_db get data", max_length=50).lower()

    def test_removes_code_blocks(self):
        msg = "hello ```python\nprint('hi')\n``` world"
        title = _generate_title(msg, max_length=50)
        assert "print" not in title
        assert "Hello" in title

    def test_removes_inline_code(self):
        msg = "use `console.log` for debugging"
        title = _generate_title(msg, max_length=50)
        assert "console.log" not in title

    def test_removes_emojis(self):
        msg = "Hello world! \U0001F600\U0001F680"
        title = _generate_title(msg, max_length=50)
        assert "\U0001F600" not in title
        assert "Hello" in title

    def test_capitalizes_first_letter(self):
        title = _generate_title("lower case message", max_length=50)
        assert title[0] == "L"

    def test_smart_truncation_at_word_boundary(self):
        msg = "This is a long message that should be truncated"
        title = _generate_title(msg, max_length=20)
        assert title.endswith("...")
        assert len(title) <= 23  # truncated word + "..."

    def test_very_short_message_gets_prefix(self):
        title = _generate_title("Hi")
        assert title.startswith("Chat:")

    def test_single_char_message(self):
        title = _generate_title("x")
        assert title.startswith("Chat:")

    def test_empty_message_becomes_new_chat(self):
        assert _generate_title("") == "New Chat"

    def test_whitespace_only_becomes_new_chat(self):
        assert _generate_title("   ") == "New Chat"

    def test_emoji_only_becomes_new_chat(self):
        title = _generate_title("\U0001F600\U0001F600\U0001F600")
        assert title == "New Chat"

    def test_preserves_question_mark_in_truncation(self):
        msg = "How do I configure the application settings for production?"
        title = _generate_title(msg, max_length=30)
        assert title.endswith("...") or title.endswith("...?")

    def test_no_truncation_needed(self):
        title = _generate_title("Short", max_length=50)
        assert title == "Short"

    def test_multiple_persona_mentions(self):
        msg = "@db1 @db2 show tables"
        title = _generate_title(msg, max_length=50)
        assert "@" not in title
        assert "show" in title.lower()


# ============================================================================
#  chat_sessions: Pydantic model validation
# ============================================================================

class TestSessionModels:

    def test_session_create_defaults(self):
        sc = SessionCreate()
        assert sc.title is None
        assert sc.is_favorite is False

    def test_session_create_title_max_length(self):
        with pytest.raises(Exception):
            SessionCreate(title="x" * 201)

    def test_session_create_title_min_length(self):
        with pytest.raises(Exception):
            SessionCreate(title="")

    def test_session_create_valid_title(self):
        sc = SessionCreate(title="My Chat")
        assert sc.title == "My Chat"

    def test_session_update_all_none(self):
        su = SessionUpdate()
        assert su.title is None
        assert su.is_favorite is None

    def test_session_response_aliases(self):
        """SessionResponse accepts both snake_case and camelCase."""
        sr = SessionResponse(
            session_id="s1",
            user_id="u1",
            created_at="2025-01-01",
            updated_at="2025-01-01",
            expires_at="9999999999",
        )
        assert sr.session_id == "s1"

        sr2 = SessionResponse(
            sessionId="s2",
            userId="u2",
            createdAt="2025-01-01",
            updatedAt="2025-01-01",
            expiresAt="9999999999",
        )
        assert sr2.session_id == "s2"


# ============================================================================
#  chat_messages: calculate_expiry_date
# ============================================================================

class TestMessageCalculateExpiryDate:

    def test_default_90_days(self):
        result = message_calculate_expiry_date()
        ts = int(result)
        expected = int((datetime.utcnow() + timedelta(days=90)).timestamp())
        assert abs(ts - expected) < 5

    def test_custom_days(self):
        result = message_calculate_expiry_date(days=14)
        ts = int(result)
        expected = int((datetime.utcnow() + timedelta(days=14)).timestamp())
        assert abs(ts - expected) < 5

    def test_returns_string(self):
        assert isinstance(message_calculate_expiry_date(), str)


# ============================================================================
#  chat_messages: create_message_dict
# ============================================================================

class TestCreateMessageDict:

    def _make_msg(self, **kwargs):
        defaults = {"content": "Hello", "message_type": "user"}
        defaults.update(kwargs)
        return MessageCreate(**defaults)

    def test_basic_message(self):
        md = self._make_msg()
        result = create_message_dict("sess-1", md)

        assert result["session_id"] == "sess-1"
        assert result["content"] == "Hello"
        assert result["message_type"] == "user"
        assert result["is_edited"] is False
        assert result["is_deleted"] is False
        assert result["created_at"].endswith("Z")

    def test_custom_message_id(self):
        md = self._make_msg()
        result = create_message_dict("sess-1", md, message_id="custom-id")
        assert result["message_id"] == "custom-id"

    def test_auto_generated_message_id(self):
        import uuid
        md = self._make_msg()
        result = create_message_dict("sess-1", md)
        uuid.UUID(result["message_id"])

    def test_optional_parent_message_id(self):
        md = self._make_msg(parent_message_id="parent-1")
        result = create_message_dict("sess-1", md)
        assert result["parent_message_id"] == "parent-1"

    def test_optional_metadata(self):
        md = self._make_msg(metadata={"key": "value"})
        result = create_message_dict("sess-1", md)
        assert result["metadata"] == {"key": "value"}

    def test_no_optional_fields_when_none(self):
        md = self._make_msg()
        result = create_message_dict("sess-1", md)
        assert "parent_message_id" not in result
        assert "metadata" not in result


# ============================================================================
#  chat_messages: format_message_response
# ============================================================================

class TestFormatMessageResponse:

    @staticmethod
    def _sample_message(**overrides):
        base = {
            "message_id": "mid-1",
            "session_id": "sid-1",
            "content": "Hello",
            "message_type": "user",
            "timestamp": "2025-01-01T00:00:00Z",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "expires_at": "9999999999",
            "is_edited": False,
            "is_deleted": False,
        }
        base.update(overrides)
        return base

    def test_basic_format(self):
        r = format_message_response(self._sample_message())
        assert isinstance(r, MessageResponse)
        assert r.message_id == "mid-1"
        assert r.session_id == "sid-1"
        assert r.content == "Hello"

    def test_fallback_to_id(self):
        item = self._sample_message()
        del item["message_id"]
        item["id"] = "from-id"
        r = format_message_response(item)
        assert r.message_id == "from-id"

    def test_defaults_when_fields_missing(self):
        minimal = {}
        r = format_message_response(minimal)
        assert r.message_id == ""
        assert r.content == ""
        assert r.message_type == "user"
        assert r.is_edited is False

    def test_with_attachments(self):
        att = {
            "filename": "test.png",
            "file_type": "image/png",
            "file_size": 1024,
            "file_url": "https://example.com/test.png",
        }
        item = self._sample_message(attachments=[att])
        r = format_message_response(item)
        assert r.attachments is not None
        assert len(r.attachments) == 1
        assert r.attachments[0].filename == "test.png"

    def test_with_reactions(self):
        react = {"emoji": "thumbsup", "count": 2, "users": ["u1", "u2"]}
        item = self._sample_message(reactions=[react])
        r = format_message_response(item)
        assert r.reactions is not None
        assert len(r.reactions) == 1
        assert r.reactions[0].emoji == "thumbsup"

    def test_with_metadata(self):
        item = self._sample_message(metadata={"model": "gpt-4"})
        r = format_message_response(item)
        assert r.metadata == {"model": "gpt-4"}


# ============================================================================
#  chat_messages: Pydantic models
# ============================================================================

class TestMessageModels:

    def test_message_create_required_content(self):
        with pytest.raises(Exception):
            MessageCreate(content="", message_type="user")

    def test_message_create_valid_types(self):
        for mt in ("user", "assistant", "system"):
            mc = MessageCreate(content="hi", message_type=mt)
            assert mc.message_type == mt

    def test_message_create_invalid_type(self):
        with pytest.raises(Exception):
            MessageCreate(content="hi", message_type="invalid")

    def test_message_create_max_length(self):
        with pytest.raises(Exception):
            MessageCreate(content="x" * 10001, message_type="user")

    def test_message_create_camel_case_alias(self):
        mc = MessageCreate(content="hi", messageType="assistant")
        assert mc.message_type == "assistant"

    def test_message_update_optional(self):
        mu = MessageUpdate()
        assert mu.content is None
        assert mu.metadata is None

    def test_message_update_content_min_length(self):
        with pytest.raises(Exception):
            MessageUpdate(content="")

    def test_message_response_aliases(self):
        mr = MessageResponse(
            message_id="m1",
            session_id="s1",
            content="hi",
            message_type="user",
            timestamp="2025-01-01",
            created_at="2025-01-01",
            updated_at="2025-01-01",
        )
        assert mr.message_id == "m1"

        mr2 = MessageResponse(
            messageId="m2",
            sessionId="s2",
            content="hi",
            messageType="user",
            timestamp="2025-01-01",
            createdAt="2025-01-01",
            updatedAt="2025-01-01",
        )
        assert mr2.message_id == "m2"


# ============================================================================
#  chat_messages: MessageAttachment alias handling
# ============================================================================

class TestMessageAttachment:

    def test_snake_case_fields(self):
        att = MessageAttachment(
            filename="f.txt",
            file_type="text/plain",
            file_size=100,
            file_url="https://example.com/f.txt",
        )
        assert att.filename == "f.txt"
        assert att.file_type == "text/plain"

    def test_camel_case_aliases(self):
        att = MessageAttachment(
            filename="f.txt",
            fileType="text/plain",
            fileSize=100,
            fileUrl="https://example.com/f.txt",
        )
        assert att.file_type == "text/plain"
        assert att.file_size == 100
        assert att.file_url == "https://example.com/f.txt"

    def test_optional_thumbnail(self):
        att = MessageAttachment(
            filename="f.txt",
            file_type="text/plain",
            file_size=100,
            file_url="https://example.com/f.txt",
            thumbnail_url="https://example.com/thumb.png",
        )
        assert att.thumbnail_url == "https://example.com/thumb.png"

    def test_thumbnail_defaults_none(self):
        att = MessageAttachment(
            filename="f.txt",
            file_type="text/plain",
            file_size=100,
            file_url="https://example.com/f.txt",
        )
        assert att.thumbnail_url is None


# ============================================================================
#  personas: Pydantic models
# ============================================================================

class TestPersonaModels:

    def test_persona_required_fields(self):
        p = Persona(
            name="My DB",
            description="Postgres prod",
            persona_type_id="postgresql_database",
            user_id="user-1",
        )
        assert p.name == "My DB"
        assert p.status == "active"

    def test_persona_name_min_length(self):
        with pytest.raises(Exception):
            Persona(
                name="",
                description="desc",
                persona_type_id="postgresql_database",
                user_id="user-1",
            )

    def test_persona_status_pattern_valid(self):
        for s in ("active", "inactive"):
            p = Persona(
                name="Test",
                description="d",
                persona_type_id="pt",
                user_id="u",
                status=s,
            )
            assert p.status == s

    def test_persona_status_pattern_invalid(self):
        with pytest.raises(Exception):
            Persona(
                name="Test",
                description="d",
                persona_type_id="pt",
                user_id="u",
                status="disabled",
            )

    def test_persona_default_credentials(self):
        p = Persona(
            name="Test",
            description="d",
            persona_type_id="pt",
            user_id="u",
        )
        assert p.credentials == {}

    def test_persona_response_model(self):
        pr = PersonaResponse(
            success=True,
            personas=[{"id": "1", "name": "test"}],
            total_count=1,
            last_updated="2025-01-01T00:00:00Z",
        )
        assert pr.success is True
        assert pr.total_count == 1
        assert pr.source == "mongodb"

    def test_persona_response_with_error(self):
        pr = PersonaResponse(
            success=False,
            personas=[],
            total_count=0,
            last_updated="2025-01-01T00:00:00Z",
            error="Connection failed",
        )
        assert pr.error == "Connection failed"

    def test_test_connection_request_valid(self):
        tcr = TestConnectionRequest(
            persona_type_id="postgresql_database",
            credentials={"host": "localhost", "port": 5432},
        )
        assert tcr.persona_type_id == "postgresql_database"

    def test_test_connection_request_empty_type(self):
        with pytest.raises(Exception):
            TestConnectionRequest(
                persona_type_id="",
                credentials={"host": "localhost"},
            )

    def test_test_connection_request_credentials_required(self):
        with pytest.raises(Exception):
            TestConnectionRequest(persona_type_id="postgresql_database")


# ============================================================================
#  settings: Settings dataclass properties
# ============================================================================

class TestSettings:

    def test_default_port(self):
        s = Settings()
        assert s.port == int(os.getenv("PORT", "18741"))

    def test_cors_origins_list(self):
        s = Settings()
        origins = s.cors_origins_list
        assert isinstance(origins, list)
        assert len(origins) > 0

    def test_cors_origins_list_parsing(self):
        s = Settings()
        s.cors_origins = "http://a.com, http://b.com , http://c.com"
        assert s.cors_origins_list == ["http://a.com", "http://b.com", "http://c.com"]

    def test_cors_origins_list_empty_entries(self):
        s = Settings()
        s.cors_origins = "http://a.com,,http://b.com,"
        origins = s.cors_origins_list
        assert "" not in origins
        assert len(origins) == 2

    def test_is_production(self):
        s = Settings()
        s.environment = "production"
        assert s.is_production is True
        s.environment = "prod"
        assert s.is_production is True
        s.environment = "development"
        assert s.is_production is False

    def test_is_development(self):
        s = Settings()
        s.environment = "development"
        assert s.is_development is True
        s.environment = "dev"
        assert s.is_development is True
        s.environment = "local"
        assert s.is_development is True
        s.environment = "production"
        assert s.is_development is False

    def test_is_atlas(self):
        s = Settings()
        s.mongodb_url = "mongodb+srv://user:pass@cluster.mongodb.net"
        assert s.is_atlas is True
        s.mongodb_url = "mongodb://localhost:27017"
        assert s.is_atlas is False

    def test_get_mongodb_connection_string_atlas(self):
        s = Settings()
        s.mongodb_url = "mongodb+srv://user:pass@cluster.mongodb.net"
        assert s.get_mongodb_connection_string() == s.mongodb_url

    def test_get_mongodb_connection_string_local_strips_trailing_slash(self):
        s = Settings()
        s.mongodb_url = "mongodb://localhost:27017/"
        result = s.get_mongodb_connection_string()
        assert not result.endswith("/")

    def test_api_prefix_default(self):
        s = Settings()
        assert s.api_prefix == os.getenv("API_PREFIX", "/api/v1")


# ============================================================================
#  database: _mask_connection_string
# ============================================================================

class TestMaskConnectionString:

    def test_no_credentials(self):
        url = "mongodb://localhost:27017"
        assert _mask_connection_string(url) == url

    def test_with_credentials(self):
        url = "mongodb://admin:s3cret@localhost:27017"
        masked = _mask_connection_string(url)
        assert "s3cret" not in masked
        assert "admin:****" in masked
        assert masked.endswith("@localhost:27017")

    def test_atlas_url(self):
        url = "mongodb+srv://myuser:MyP@ss@cluster0.abc123.mongodb.net"
        masked = _mask_connection_string(url)
        assert "MyP@ss" not in masked
        assert "myuser:****" in masked

    def test_no_password_in_credentials(self):
        url = "mongodb://admin@localhost:27017"
        masked = _mask_connection_string(url)
        # No colon separating user:pass, so credentials returned as-is
        assert "admin" in masked

    def test_preserves_host_and_path(self):
        url = "mongodb://user:pass@host:27017/dbname?authSource=admin"
        masked = _mask_connection_string(url)
        assert "host:27017/dbname?authSource=admin" in masked
        assert "pass" not in masked
