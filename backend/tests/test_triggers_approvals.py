"""
Tests for the trigger system and approval queue.

Covers:
- Trigger CRUD (repository + API)
- Approval CRUD (repository + API)
- Think-tag parser (unit tests)
- Channel message dispatch flow
"""

import pytest
import pytest_asyncio


# ── Think Tag Parser Tests ─────────────────────────────────────────────

class TestThinkTagParser:
    """Unit tests for the think-tag parser (no DB needed)."""

    def test_parse_no_tags(self):
        from services.think_tag_parser import parse_think_tags
        result = parse_think_tags("Just a normal response")
        assert result.content == "Just a normal response"
        assert result.reasoning == ""

    def test_parse_with_tags(self):
        from services.think_tag_parser import parse_think_tags
        result = parse_think_tags(
            "<think>Let me think about this...</think>The answer is 42."
        )
        assert result.content == "The answer is 42."
        assert "think about this" in result.reasoning

    def test_parse_multiple_tags(self):
        from services.think_tag_parser import parse_think_tags
        result = parse_think_tags(
            "<think>Step 1</think>First part. <think>Step 2</think>Second part."
        )
        assert "Step 1" in result.reasoning
        assert "Step 2" in result.reasoning
        assert "<think>" not in result.content

    def test_streaming_parser_basic(self):
        from services.think_tag_parser import StreamingThinkParser
        parser = StreamingThinkParser()

        segs = parser.feed("<think>hello</think>world")
        kinds = [(s[0], s[1]) for s in segs]
        assert ("thinking", "hello") in kinds
        assert ("content", "world") in kinds

    def test_streaming_parser_partial_tags(self):
        from services.think_tag_parser import StreamingThinkParser
        parser = StreamingThinkParser()

        # Feed partial <think> tag
        segs1 = parser.feed("hello<thi")
        segs2 = parser.feed("nk>inside")
        segs3 = parser.feed("</think>outside")
        segs4 = parser.finish()

        all_segs = segs1 + segs2 + segs3 + segs4
        content = "".join(s[1] for s in all_segs if s[0] == "content")
        thinking = "".join(s[1] for s in all_segs if s[0] == "thinking")

        assert "hello" in content
        assert "outside" in content
        assert "inside" in thinking

    def test_streaming_parser_no_tags(self):
        from services.think_tag_parser import StreamingThinkParser
        parser = StreamingThinkParser()

        segs = parser.feed("just plain text")
        segs += parser.finish()

        content = "".join(s[1] for s in segs if s[0] == "content")
        thinking = "".join(s[1] for s in segs if s[0] == "thinking")
        assert content == "just plain text"
        assert thinking == ""


# ── Trigger Repository Tests ──────────────────────────────────────────

@pytest.mark.asyncio
class TestTriggerRepository:
    async def test_create_and_get(self, db_proxy):
        from repositories.trigger_repository import TriggerRepository
        repo = TriggerRepository(db_proxy)

        trigger = await repo.create({
            "channel_type": "telegram",
            "channel_id": "*",
            "crew_id": "crew-123",
            "enabled": True,
            "approval_required": False,
            "cooldown_seconds": 60,
        })

        assert trigger["channel_type"] == "telegram"
        assert trigger["crew_id"] == "crew-123"
        assert trigger["enabled"] is True

        fetched = await repo.get_by_id(trigger["trigger_id"])
        assert fetched is not None
        assert fetched["crew_id"] == "crew-123"

    async def test_find_for_channel_wildcard(self, db_proxy):
        from repositories.trigger_repository import TriggerRepository
        repo = TriggerRepository(db_proxy)

        await repo.create({
            "channel_type": "discord",
            "channel_id": "*",
            "enabled": True,
        })

        found = await repo.find_for_channel("discord", "any-chat-id")
        assert found is not None
        assert found["channel_type"] == "discord"

    async def test_find_for_channel_exact_match(self, db_proxy):
        from repositories.trigger_repository import TriggerRepository
        repo = TriggerRepository(db_proxy)

        await repo.create({
            "channel_type": "whatsapp",
            "channel_id": "specific-chat",
            "enabled": True,
            "crew_id": "exact-crew",
        })
        await repo.create({
            "channel_type": "whatsapp",
            "channel_id": "*",
            "enabled": True,
            "crew_id": "wildcard-crew",
        })

        found = await repo.find_for_channel("whatsapp", "specific-chat")
        assert found is not None
        assert found["crew_id"] == "exact-crew"  # exact match takes priority

    async def test_update_and_delete(self, db_proxy):
        from repositories.trigger_repository import TriggerRepository
        repo = TriggerRepository(db_proxy)

        trigger = await repo.create({
            "channel_type": "teams",
            "enabled": True,
        })
        tid = trigger["trigger_id"]

        updated = await repo.update(tid, {"enabled": False})
        assert updated["enabled"] is False

        deleted = await repo.delete(tid)
        assert deleted is True

        gone = await repo.get_by_id(tid)
        assert gone is None

    async def test_record_fire(self, db_proxy):
        from repositories.trigger_repository import TriggerRepository
        repo = TriggerRepository(db_proxy)

        trigger = await repo.create({
            "channel_type": "slack",
            "enabled": True,
        })
        tid = trigger["trigger_id"]
        assert trigger["fire_count"] == 0

        await repo.record_fire(tid)
        updated = await repo.get_by_id(tid)
        assert updated["fire_count"] == 1
        assert updated["last_fired_at"] is not None


# ── Approval Repository Tests ─────────────────────────────────────────

@pytest.mark.asyncio
class TestApprovalRepository:
    async def test_create_and_list_pending(self, db_proxy):
        from repositories.approval_repository import ApprovalRepository
        repo = ApprovalRepository(db_proxy)

        approval = await repo.create({
            "trigger_id": "trig-1",
            "channel_type": "telegram",
            "channel_id": "chat-42",
            "sender_name": "Alice",
            "sender_id": "alice-1",
            "inbound_text": "Hello!",
            "draft_response": "Hi Alice!",
            "session_id": "sess-1",
        })

        assert approval["status"] == "pending"
        assert approval["draft_response"] == "Hi Alice!"

        pending = await repo.list_pending()
        assert len(pending) >= 1
        assert any(a["approval_id"] == approval["approval_id"] for a in pending)

    async def test_approve(self, db_proxy):
        from repositories.approval_repository import ApprovalRepository
        repo = ApprovalRepository(db_proxy)

        approval = await repo.create({
            "channel_type": "discord",
            "channel_id": "ch-1",
            "inbound_text": "Help!",
            "draft_response": "Sure!",
        })

        approved = await repo.approve(approval["approval_id"])
        assert approved["status"] == "approved"
        assert approved["final_response"] == "Sure!"
        assert approved["reviewed_by"] == "desktop-user"

    async def test_approve_with_edit(self, db_proxy):
        from repositories.approval_repository import ApprovalRepository
        repo = ApprovalRepository(db_proxy)

        approval = await repo.create({
            "channel_type": "telegram",
            "channel_id": "ch-2",
            "inbound_text": "Price?",
            "draft_response": "It costs $10",
        })

        approved = await repo.approve(
            approval["approval_id"],
            edited_response="It costs $9.99!",
        )
        assert approved["status"] == "edited"
        assert approved["final_response"] == "It costs $9.99!"

    async def test_reject(self, db_proxy):
        from repositories.approval_repository import ApprovalRepository
        repo = ApprovalRepository(db_proxy)

        approval = await repo.create({
            "channel_type": "whatsapp",
            "channel_id": "ch-3",
            "inbound_text": "Spam",
            "draft_response": "Thanks!",
        })

        rejected = await repo.reject(approval["approval_id"])
        assert rejected["status"] == "rejected"

    async def test_count_pending(self, db_proxy):
        from repositories.approval_repository import ApprovalRepository
        repo = ApprovalRepository(db_proxy)

        before = await repo.count_pending()

        await repo.create({
            "channel_type": "telegram",
            "channel_id": "ch-count",
            "inbound_text": "Count test",
            "draft_response": "Response",
        })

        after = await repo.count_pending()
        assert after == before + 1


# ── Trigger Service Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
class TestTriggerService:
    async def test_cooldown_check(self, db_proxy):
        from services.trigger_service import TriggerService
        svc = TriggerService(db_proxy)

        # No last_fired_at — should pass
        assert svc._check_cooldown({"cooldown_seconds": 60, "last_fired_at": None}) is True

        # Zero cooldown — always passes
        assert svc._check_cooldown({"cooldown_seconds": 0, "last_fired_at": "2020-01-01T00:00:00"}) is True

        # Fired very recently with 999s cooldown — should fail
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        assert svc._check_cooldown({"cooldown_seconds": 999, "last_fired_at": now}) is False

        # Fired long ago — should pass
        assert svc._check_cooldown({"cooldown_seconds": 1, "last_fired_at": "2020-01-01T00:00:00"}) is True


# ── API Endpoint Tests ────────────────────────────────────────────────

class TestTriggersAPI:
    def test_list_triggers_empty(self, test_app):
        resp = test_app.get("/api/v1/triggers/")
        assert resp.status_code == 200
        data = resp.json()
        assert "triggers" in data

    def test_create_and_list_trigger(self, test_app):
        resp = test_app.post("/api/v1/triggers/", json={
            "channel_type": "telegram",
            "approval_required": True,
        })
        assert resp.status_code == 200
        trigger = resp.json()["trigger"]
        assert trigger["channel_type"] == "telegram"
        assert trigger["approval_required"] is True

        resp = test_app.get("/api/v1/triggers/")
        triggers = resp.json()["triggers"]
        assert any(t["trigger_id"] == trigger["trigger_id"] for t in triggers)

    def test_update_trigger(self, test_app):
        resp = test_app.post("/api/v1/triggers/", json={
            "channel_type": "discord",
        })
        tid = resp.json()["trigger"]["trigger_id"]

        resp = test_app.put(f"/api/v1/triggers/{tid}", json={
            "enabled": False,
        })
        assert resp.status_code == 200
        assert resp.json()["trigger"]["enabled"] is False

    def test_delete_trigger(self, test_app):
        resp = test_app.post("/api/v1/triggers/", json={
            "channel_type": "telegram",
        })
        tid = resp.json()["trigger"]["trigger_id"]

        resp = test_app.delete(f"/api/v1/triggers/{tid}")
        assert resp.status_code == 200

        resp = test_app.get(f"/api/v1/triggers/{tid}")
        assert resp.status_code == 404


class TestApprovalsAPI:
    def test_count_pending(self, test_app):
        resp = test_app.get("/api/v1/approvals/count")
        assert resp.status_code == 200
        assert "pending_count" in resp.json()

    def test_list_empty(self, test_app):
        resp = test_app.get("/api/v1/approvals/")
        assert resp.status_code == 200
        assert "approvals" in resp.json()

    def test_approve_not_found(self, test_app):
        resp = test_app.post("/api/v1/approvals/nonexistent/approve")
        assert resp.status_code == 404

    def test_reject_not_found(self, test_app):
        resp = test_app.post("/api/v1/approvals/nonexistent/reject")
        assert resp.status_code == 404
