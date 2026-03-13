"""
Tests for FastAPI endpoints using the test_app fixture (TestClient + temp SQLite DB).

All tests are synchronous — TestClient handles async internally.
"""

import uuid
import pytest


# ============================================================================
# Health / Root Endpoints
# ============================================================================

class TestRootEndpoint:
    """GET / — application root health check."""

    def test_root_returns_200(self, test_app):
        resp = test_app.get("/")
        assert resp.status_code == 200

    def test_root_contains_service_name(self, test_app):
        data = test_app.get("/").json()
        assert data["service"] == "contextuai-solo"

    def test_root_status_healthy(self, test_app):
        data = test_app.get("/").json()
        assert data["status"] == "healthy"

    def test_root_mode_desktop(self, test_app):
        data = test_app.get("/").json()
        assert data["mode"] == "desktop"

    def test_root_has_version(self, test_app):
        data = test_app.get("/").json()
        assert "version" in data

    def test_root_has_uptime(self, test_app):
        data = test_app.get("/").json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], int)

    def test_root_has_timestamp(self, test_app):
        data = test_app.get("/").json()
        assert "timestamp" in data


class TestHealthEndpoint:
    """GET /health — health check endpoint."""

    def test_health_returns_200(self, test_app):
        resp = test_app.get("/health")
        assert resp.status_code == 200

    def test_health_status_healthy(self, test_app):
        data = test_app.get("/health").json()
        assert data["status"] == "healthy"

    def test_health_mode_desktop(self, test_app):
        data = test_app.get("/health").json()
        assert data["mode"] == "desktop"

    def test_health_has_service_name(self, test_app):
        data = test_app.get("/health").json()
        assert data["service"] == "contextuai-solo"


# ============================================================================
# Reseed Endpoint
# ============================================================================

class TestReseedEndpoint:
    """POST /api/v1/desktop/reseed — re-seed persona types and agents."""

    def test_reseed_returns_200(self, test_app):
        resp = test_app.post("/api/v1/desktop/reseed")
        assert resp.status_code == 200

    def test_reseed_status_success(self, test_app):
        data = test_app.post("/api/v1/desktop/reseed").json()
        assert data["status"] == "success"

    def test_reseed_seeds_persona_types(self, test_app):
        data = test_app.post("/api/v1/desktop/reseed").json()
        assert data["persona_types_seeded"] > 0

    def test_reseed_idempotent(self, test_app):
        """Running reseed twice should produce the same persona type count."""
        data1 = test_app.post("/api/v1/desktop/reseed").json()
        data2 = test_app.post("/api/v1/desktop/reseed").json()
        assert data1["persona_types_seeded"] == data2["persona_types_seeded"]


# ============================================================================
# Persona Types
# ============================================================================

class TestPersonaTypes:
    """GET /api/v1/persona-types — list persona types (after reseed)."""

    def test_list_persona_types_after_reseed(self, test_app):
        test_app.post("/api/v1/desktop/reseed")
        resp = test_app.get("/api/v1/persona-types")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total_count"] > 0

    def test_persona_types_include_generic(self, test_app):
        test_app.post("/api/v1/desktop/reseed")
        data = test_app.get("/api/v1/persona-types").json()
        ids = [pt.get("id") for pt in data["persona_types"]]
        assert "generic" in ids

    def test_persona_types_include_postgresql(self, test_app):
        test_app.post("/api/v1/desktop/reseed")
        data = test_app.get("/api/v1/persona-types").json()
        ids = [pt.get("id") for pt in data["persona_types"]]
        assert "postgresql" in ids

    def test_persona_types_have_credential_fields(self, test_app):
        test_app.post("/api/v1/desktop/reseed")
        data = test_app.get("/api/v1/persona-types").json()
        for pt in data["persona_types"]:
            assert "credentialFields" in pt, f"Persona type {pt.get('id')} missing credentialFields"

    def test_get_single_persona_type(self, test_app):
        test_app.post("/api/v1/desktop/reseed")
        resp = test_app.get("/api/v1/persona-types/generic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Nexus Agent"

    def test_get_nonexistent_persona_type_404(self, test_app):
        test_app.post("/api/v1/desktop/reseed")
        resp = test_app.get("/api/v1/persona-types/nonexistent_type")
        assert resp.status_code == 404


# ============================================================================
# Personas CRUD
# ============================================================================

class TestPersonasCRUD:
    """Full CRUD lifecycle for personas."""

    def _reseed(self, client):
        """Ensure persona types exist."""
        client.post("/api/v1/desktop/reseed")

    def _create_persona(self, client, name="Test Persona", persona_type_id="generic"):
        return client.post("/api/v1/personas/", json={
            "name": name,
            "description": "A test persona",
            "persona_type_id": persona_type_id,
            "user_id": "test-user",
            "credentials": {"system_instructions": "You are a helpful assistant."},
        })

    def test_create_persona(self, test_app):
        self._reseed(test_app)
        resp = self._create_persona(test_app)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Persona"
        assert "id" in data or "_id" in data

    def test_create_persona_invalid_type_returns_400(self, test_app):
        self._reseed(test_app)
        resp = test_app.post("/api/v1/personas/", json={
            "name": "Bad Persona",
            "description": "Invalid type",
            "persona_type_id": "nonexistent_type_xyz",
            "user_id": "test-user",
            "credentials": {},
        })
        assert resp.status_code == 400

    def test_list_personas(self, test_app):
        self._reseed(test_app)
        self._create_persona(test_app, name="List Test")
        resp = test_app.get("/api/v1/personas")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total_count"] >= 1

    def test_get_persona_by_id(self, test_app):
        self._reseed(test_app)
        create_resp = self._create_persona(test_app, name="Get By ID")
        created = create_resp.json()
        persona_id = created.get("id") or created.get("_id")

        resp = test_app.get(f"/api/v1/personas/{persona_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Get By ID"

    def test_get_nonexistent_persona_returns_404(self, test_app):
        resp = test_app.get(f"/api/v1/personas/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_update_persona(self, test_app):
        self._reseed(test_app)
        create_resp = self._create_persona(test_app, name="Before Update")
        created = create_resp.json()
        persona_id = created.get("id") or created.get("_id")

        resp = test_app.put(f"/api/v1/personas/{persona_id}", json={
            "name": "After Update",
            "description": "Updated description",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "After Update"

    def test_update_nonexistent_persona_returns_404(self, test_app):
        resp = test_app.put(f"/api/v1/personas/{uuid.uuid4()}", json={
            "name": "Ghost",
        })
        assert resp.status_code == 404

    def test_delete_persona(self, test_app):
        self._reseed(test_app)
        create_resp = self._create_persona(test_app, name="To Delete")
        created = create_resp.json()
        persona_id = created.get("id") or created.get("_id")

        resp = test_app.delete(f"/api/v1/personas/{persona_id}")
        assert resp.status_code == 200

        # Confirm it is gone
        get_resp = test_app.get(f"/api/v1/personas/{persona_id}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_persona_returns_404(self, test_app):
        resp = test_app.delete(f"/api/v1/personas/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_create_persona_missing_name_returns_422(self, test_app):
        """Pydantic validation: name is required."""
        self._reseed(test_app)
        resp = test_app.post("/api/v1/personas/", json={
            "description": "No name",
            "persona_type_id": "generic",
            "user_id": "test-user",
        })
        assert resp.status_code == 422


# ============================================================================
# Chat Sessions CRUD
# ============================================================================

class TestChatSessionsCRUD:
    """Full CRUD lifecycle for chat sessions."""

    def _create_session(self, client, user_id="test-user", title=None):
        body = {"userId": user_id}
        if title:
            body["title"] = title
        return client.post("/api/v1/chat-sessions/", json=body)

    def test_create_session(self, test_app):
        resp = self._create_session(test_app)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "session" in data
        assert data["session"]["userId"] == "test-user"

    def test_create_session_with_title(self, test_app):
        resp = self._create_session(test_app, title="My Chat")
        data = resp.json()
        assert data["session"]["title"] == "My Chat"

    def test_create_session_default_user(self, test_app):
        """When userId is omitted, the endpoint defaults to desktop-user."""
        resp = test_app.post("/api/v1/chat-sessions/", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"]["userId"] == "desktop-user"

    def test_get_session(self, test_app):
        create_data = self._create_session(test_app).json()
        session_id = create_data["session"]["sessionId"]

        resp = test_app.get(f"/api/v1/chat-sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessionId"] == session_id

    def test_get_nonexistent_session_returns_404(self, test_app):
        resp = test_app.get(f"/api/v1/chat-sessions/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_list_user_sessions(self, test_app):
        self._create_session(test_app, user_id="session-list-user")
        self._create_session(test_app, user_id="session-list-user")

        resp = test_app.get("/api/v1/chat-sessions/user/session-list-user")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["totalCount"] >= 2

    def test_list_user_sessions_empty(self, test_app):
        resp = test_app.get(f"/api/v1/chat-sessions/user/{uuid.uuid4()}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalCount"] == 0

    def test_update_session(self, test_app):
        create_data = self._create_session(test_app, title="Original").json()
        session_id = create_data["session"]["sessionId"]

        resp = test_app.put(f"/api/v1/chat-sessions/{session_id}", json={
            "title": "Renamed",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Renamed"

    def test_update_nonexistent_session_returns_404(self, test_app):
        resp = test_app.put(f"/api/v1/chat-sessions/{uuid.uuid4()}", json={
            "title": "Ghost",
        })
        assert resp.status_code == 404

    def test_delete_session_soft(self, test_app):
        create_data = self._create_session(test_app).json()
        session_id = create_data["session"]["sessionId"]

        resp = test_app.delete(f"/api/v1/chat-sessions/{session_id}")
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_delete_session_hard(self, test_app):
        create_data = self._create_session(test_app).json()
        session_id = create_data["session"]["sessionId"]

        resp = test_app.delete(f"/api/v1/chat-sessions/{session_id}?hard_delete=true")
        assert resp.status_code == 200

        # Confirm it is truly gone
        get_resp = test_app.get(f"/api/v1/chat-sessions/{session_id}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent_session_returns_404(self, test_app):
        resp = test_app.delete(f"/api/v1/chat-sessions/{uuid.uuid4()}")
        assert resp.status_code == 404


# ============================================================================
# Chat Messages
# ============================================================================

class TestChatMessages:
    """CRUD for chat messages (requires a session to exist first).

    Uses the REST endpoint POST /api/v1/chat-messages/{session_id}/messages
    which resolves sessions by both session_id field and MongoDB _id.
    """

    def _create_session(self, client):
        data = client.post("/api/v1/chat-sessions/", json={"userId": "test-user"}).json()
        return data["session"]["sessionId"]

    def _create_message(self, client, session_id, content="Hello", message_type="user"):
        """Create a message via the REST endpoint that uses find_session()."""
        return client.post(
            f"/api/v1/chat-messages/{session_id}/messages",
            json={
                "content": content,
                "messageType": message_type,
            },
        )

    def test_create_message(self, test_app):
        session_id = self._create_session(test_app)
        resp = self._create_message(test_app, session_id)
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Hello"

    def test_create_message_missing_session_returns_404(self, test_app):
        fake_session = str(uuid.uuid4())
        resp = self._create_message(test_app, fake_session)
        assert resp.status_code == 404

    def test_create_message_missing_content_returns_422(self, test_app):
        """Pydantic validation requires content (min_length=1)."""
        session_id = self._create_session(test_app)
        resp = test_app.post(
            f"/api/v1/chat-messages/{session_id}/messages",
            json={"messageType": "user"},
        )
        assert resp.status_code == 422

    def test_get_messages_by_session(self, test_app):
        session_id = self._create_session(test_app)
        self._create_message(test_app, session_id, content="First")
        self._create_message(test_app, session_id, content="Second")

        resp = test_app.get(f"/api/v1/chat-messages/{session_id}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["totalCount"] == 2

    def test_get_messages_nonexistent_session_returns_404(self, test_app):
        resp = test_app.get(f"/api/v1/chat-messages/{uuid.uuid4()}/messages")
        assert resp.status_code == 404

    def test_create_assistant_message(self, test_app):
        session_id = self._create_session(test_app)
        resp = self._create_message(test_app, session_id, content="I can help.", message_type="assistant")
        assert resp.status_code == 200
        data = resp.json()
        assert data["messageType"] == "assistant"

    def test_messages_belong_to_correct_session(self, test_app):
        session_a = self._create_session(test_app)
        session_b = self._create_session(test_app)
        self._create_message(test_app, session_a, content="In session A")
        self._create_message(test_app, session_b, content="In session B")

        resp_a = test_app.get(f"/api/v1/chat-messages/{session_a}/messages")
        resp_b = test_app.get(f"/api/v1/chat-messages/{session_b}/messages")
        assert resp_a.json()["totalCount"] == 1
        assert resp_b.json()["totalCount"] == 1


# ============================================================================
# Error Cases
# ============================================================================

class TestErrorCases:
    """Miscellaneous error-handling checks."""

    def test_nonexistent_route_returns_404(self, test_app):
        resp = test_app.get("/api/v1/does-not-exist")
        assert resp.status_code == 404

    def test_persona_invalid_json_returns_422(self, test_app):
        resp = test_app.post("/api/v1/personas/", content="not json", headers={
            "Content-Type": "application/json",
        })
        assert resp.status_code == 422

    def test_session_put_invalid_body(self, test_app):
        """Sending a non-object body to update should fail."""
        resp = test_app.put(f"/api/v1/chat-sessions/{uuid.uuid4()}", content="bad", headers={
            "Content-Type": "application/json",
        })
        assert resp.status_code in (400, 404, 422)
