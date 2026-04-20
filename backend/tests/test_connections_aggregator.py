"""Tests for Phase 3 PR 2 — unified connections aggregator."""

import pytest
import pytest_asyncio

from services.connection_service import ConnectionService


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def svc(db_proxy):
    return ConnectionService(db_proxy)


async def _seed_oauth(db, provider: str, connected: bool = True):
    doc = {"_id": provider, "client_id": "x", "client_secret": "y"}
    if connected:
        doc.update({"access_token": "tok", "profile_name": f"{provider}-user"})
    await db["oauth_connections"].insert_one(doc)


async def _seed_reddit(db, _id="r1"):
    await db["reddit_accounts"].insert_one({
        "_id": _id,
        "client_id": "cid",
        "client_secret": "csec",
        "username": "u1",
        "password": "p",
        "subreddits": ["LocalLLaMA"],
        "keywords": ["pricing", "demo"],
    })


async def _seed_twitter(db, _id="tw1", with_write=True):
    doc = {
        "_id": _id,
        "user_id": "999",
        "bearer_token": "bearer",
    }
    if with_write:
        doc.update({
            "api_key": "k",
            "api_secret": "s",
            "access_token": "a",
            "access_token_secret": "b",
        })
    await db["twitter_accounts"].insert_one(doc)


async def _seed_telegram(db, _id="tg1"):
    await db["channel_registrations"].insert_one({
        "_id": _id,
        "channel_type": "telegram",
        "config": {"bot_token": "123:abc", "bot_name": "MyBot"},
    })


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_is_empty_when_no_records(svc):
    rows = await svc.list_connections()
    assert rows == []


@pytest.mark.asyncio
async def test_list_merges_all_stores(svc, db_proxy):
    await _seed_oauth(db_proxy, "linkedin")
    await _seed_oauth(db_proxy, "instagram", connected=False)
    await _seed_reddit(db_proxy)
    await _seed_twitter(db_proxy)
    await _seed_telegram(db_proxy)

    rows = await svc.list_connections()
    platforms = sorted(r.platform for r in rows)
    assert platforms == ["instagram", "linkedin", "reddit", "telegram", "twitter"]

    by_platform = {r.platform: r for r in rows}
    assert by_platform["linkedin"].id == "oauth:linkedin"
    assert by_platform["linkedin"].connected is True
    assert by_platform["instagram"].connected is False
    assert by_platform["reddit"].id.startswith("reddit:")
    assert by_platform["twitter"].outbound_supported is True
    assert by_platform["telegram"].display_name == "MyBot"


@pytest.mark.asyncio
async def test_twitter_without_write_creds_loses_outbound(svc, db_proxy):
    await _seed_twitter(db_proxy, with_write=False)
    rows = await svc.list_connections()
    tw = next(r for r in rows if r.platform == "twitter")
    assert tw.outbound_supported is False
    assert tw.outbound_enabled is False


# ---------------------------------------------------------------------------
# Outbound CRUD (blog / email / slack_webhook)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_slack_webhook_outbound(svc):
    from models.connection_models import OutboundConnectionCreate
    created = await svc.create_outbound(
        OutboundConnectionCreate(
            platform="slack_webhook",
            name="Team ops",
            config={"webhook_url": "https://hooks.slack.com/services/TXXX/BXXX/xxx"},
        ),
        user_id="test-user",
    )
    assert created.platform == "slack_webhook"
    assert created.id.startswith("outbound:")
    assert created.outbound_enabled is True
    assert created.inbound_enabled is False
    assert created.inbound_supported is False
    assert created.config_summary.get("webhook_host") == "hooks.slack.com"


@pytest.mark.asyncio
async def test_create_blog_rejects_missing_api_url(svc):
    from pydantic import ValidationError
    from models.connection_models import OutboundConnectionCreate
    with pytest.raises(ValidationError):
        OutboundConnectionCreate(
            platform="blog",
            name="My Blog",
            config={"cms_type": "ghost"},  # missing api_url
        )


@pytest.mark.asyncio
async def test_create_email_rejects_missing_from_email(svc):
    from pydantic import ValidationError
    from models.connection_models import OutboundConnectionCreate
    with pytest.raises(ValidationError):
        OutboundConnectionCreate(
            platform="email",
            name="Mailer",
            config={"provider": "sendgrid", "api_key": "sg-xxx"},  # missing from_email
        )


@pytest.mark.asyncio
async def test_update_and_delete_outbound(svc):
    from models.connection_models import OutboundConnectionCreate, OutboundConnectionUpdate
    created = await svc.create_outbound(
        OutboundConnectionCreate(
            platform="email",
            name="Old",
            config={"provider": "sendgrid", "api_key": "sg-xxx", "from_email": "a@b.c"},
        ),
        user_id="u1",
    )
    updated = await svc.update_outbound(
        created.id, OutboundConnectionUpdate(name="Renamed")
    )
    assert updated.display_name == "Renamed"

    await svc.delete_outbound(created.id)
    assert await svc.get_connection(created.id) is None


# ---------------------------------------------------------------------------
# Capability PATCH
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_capabilities_toggles_reddit(svc, db_proxy):
    await _seed_reddit(db_proxy, _id="r1")
    rows = await svc.list_connections()
    reddit = next(r for r in rows if r.platform == "reddit")
    assert reddit.inbound_enabled is True

    from models.connection_models import CapabilityUpdate
    updated = await svc.update_capabilities(reddit.id, CapabilityUpdate(inbound_enabled=False))
    assert updated.inbound_enabled is False

    raw = await db_proxy["reddit_accounts"].find_one({"_id": "r1"})
    assert raw["inbound_enabled"] is False


@pytest.mark.asyncio
async def test_patch_rejects_enabling_unsupported_capability(svc, db_proxy):
    # LinkedIn is outbound-supported but not inbound-supported
    await _seed_oauth(db_proxy, "linkedin")

    from fastapi import HTTPException
    from models.connection_models import CapabilityUpdate
    with pytest.raises(HTTPException) as exc:
        await svc.update_capabilities("oauth:linkedin", CapabilityUpdate(inbound_enabled=True))
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_patch_capabilities_rejects_empty_update():
    from pydantic import ValidationError
    from models.connection_models import CapabilityUpdate
    with pytest.raises(ValidationError):
        CapabilityUpdate()  # both None → invalid


@pytest.mark.asyncio
async def test_patch_unknown_connection_is_404(svc):
    from fastapi import HTTPException
    from models.connection_models import CapabilityUpdate
    with pytest.raises(HTTPException) as exc:
        await svc.update_capabilities("reddit:nonexistent", CapabilityUpdate(inbound_enabled=True))
    assert exc.value.status_code == 404
