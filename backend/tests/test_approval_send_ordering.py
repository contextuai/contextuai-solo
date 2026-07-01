"""Approve-and-send must post BEFORE marking approved.

A failed channel send (e.g. an expired LinkedIn token) must leave the approval
``pending`` to retry — not falsely mark it ``approved`` while nothing was posted.
"""

import pytest

from services.approval_service import ApprovalService


def _pending(approval_id="a1"):
    return {
        "_id": approval_id,
        "approval_id": approval_id,
        "status": "pending",
        "type": "crew_publish",
        "channel_type": "linkedin",
        "channel_id": "c1",
        "draft_response": "hello world",
        "content": "hello world",
    }


@pytest.mark.asyncio
async def test_failed_send_leaves_pending(db_proxy, monkeypatch):
    svc = ApprovalService(db_proxy)
    await db_proxy["approval_queue"].insert_one(_pending("a1"))

    async def boom(*_a, **_k):
        raise RuntimeError("EXPIRED_ACCESS_TOKEN")

    monkeypatch.setattr(svc, "_send_via_channel", boom)

    with pytest.raises(RuntimeError):
        await svc.approve_and_send("a1")

    doc = await db_proxy["approval_queue"].find_one({"approval_id": "a1"})
    assert doc["status"] == "pending"  # not falsely approved


@pytest.mark.asyncio
async def test_successful_send_marks_approved(db_proxy, monkeypatch):
    svc = ApprovalService(db_proxy)
    await db_proxy["approval_queue"].insert_one(_pending("a2"))

    sent = {}

    async def ok(channel_type, channel_id, text):
        sent["text"] = text

    monkeypatch.setattr(svc, "_send_via_channel", ok)

    await svc.approve_and_send("a2")

    doc = await db_proxy["approval_queue"].find_one({"approval_id": "a2"})
    assert doc["status"] == "approved"
    assert sent["text"] == "hello world"
