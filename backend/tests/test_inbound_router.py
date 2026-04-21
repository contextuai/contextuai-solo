"""Tests for Phase 3 PR 3 — inbound_router."""

from types import SimpleNamespace

import pytest
import pytest_asyncio

from services.inbound_router import (
    _trigger_matches,
    find_matching_crews,
    route_inbound,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _msg(channel_type: str, text: str):
    """Minimal ChannelMessage shim: only fields inbound_router reads."""
    return SimpleNamespace(
        channel_type=SimpleNamespace(value=channel_type),
        text=text,
    )


async def _seed_crew(db, crew_id: str, name: str, triggers: list, user_id: str = "u1"):
    await db["crews"].insert_one({
        "_id": crew_id,
        "crew_id": crew_id,
        "user_id": user_id,
        "name": name,
        "description": f"{name} description",
        "status": "active",
        "agents": [
            {
                "agent_id": "a1",
                "name": "Writer",
                "role": "writer",
                "instructions": "Write.",
                "order": 0,
            }
        ],
        "execution_config": {"mode": "sequential", "timeout_seconds": 60},
        "triggers": triggers,
        "created_at": "2026-04-21T00:00:00",
        "updated_at": "2026-04-21T00:00:00",
    })


# ---------------------------------------------------------------------------
# Matcher unit tests
# ---------------------------------------------------------------------------

def test_keyword_substring_match_case_insensitive():
    trigger = {"keywords": ["Pricing"], "hashtags": [], "mentions": []}
    assert _trigger_matches(trigger, "How does your PRICING work?") is True


def test_no_match_when_rules_empty():
    trigger = {"keywords": [], "hashtags": [], "mentions": []}
    assert _trigger_matches(trigger, "anything") is False


def test_hashtag_match():
    trigger = {"keywords": [], "hashtags": ["#demo"], "mentions": []}
    assert _trigger_matches(trigger, "Check out #demo today!") is True


def test_mention_match():
    trigger = {"keywords": [], "hashtags": [], "mentions": ["@support"]}
    assert _trigger_matches(trigger, "Hey @support, can you help?") is True


def test_empty_text_is_safe():
    trigger = {"keywords": ["x"], "hashtags": [], "mentions": []}
    assert _trigger_matches(trigger, "") is False


# ---------------------------------------------------------------------------
# find_matching_crews
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_matching_crews_exact_one(db_proxy):
    await _seed_crew(db_proxy, "crew-a", "Sales", [
        {"type": "reactive", "connection_id": "reddit", "keywords": ["pricing"]},
    ])
    await _seed_crew(db_proxy, "crew-b", "Support", [
        {"type": "reactive", "connection_id": "reddit", "keywords": ["bug"]},
    ])

    matches = await find_matching_crews(db_proxy, "reddit", "What's your pricing?")
    assert len(matches) == 1
    assert matches[0][0]["crew_id"] == "crew-a"


@pytest.mark.asyncio
async def test_find_matching_crews_connection_filter(db_proxy):
    await _seed_crew(db_proxy, "crew-a", "Sales", [
        {"type": "reactive", "connection_id": "telegram", "keywords": ["pricing"]},
    ])
    matches = await find_matching_crews(db_proxy, "reddit", "pricing question")
    assert matches == []


@pytest.mark.asyncio
async def test_find_matching_crews_multi_match(db_proxy):
    await _seed_crew(db_proxy, "crew-a", "Sales", [
        {"type": "reactive", "connection_id": "reddit", "keywords": ["pricing"]},
    ])
    await _seed_crew(db_proxy, "crew-b", "Marketing", [
        {"type": "reactive", "connection_id": "reddit", "keywords": ["demo"]},
    ])
    matches = await find_matching_crews(db_proxy, "reddit", "can I get a pricing demo?")
    assert len(matches) == 2


@pytest.mark.asyncio
async def test_scheduled_triggers_do_not_match_inbound(db_proxy):
    await _seed_crew(db_proxy, "crew-s", "Scheduled", [
        {"type": "scheduled", "connection_ids": ["reddit"], "cron": "0 9 * * *"},
    ])
    matches = await find_matching_crews(db_proxy, "reddit", "anything")
    assert matches == []


@pytest.mark.asyncio
async def test_inactive_crews_ignored(db_proxy):
    await _seed_crew(db_proxy, "crew-paused", "Paused", [
        {"type": "reactive", "connection_id": "reddit", "keywords": ["hit"]},
    ])
    await db_proxy["crews"].update_one(
        {"crew_id": "crew-paused"}, {"$set": {"status": "paused"}}
    )
    matches = await find_matching_crews(db_proxy, "reddit", "please hit this")
    assert matches == []


# ---------------------------------------------------------------------------
# route_inbound end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_inbound_returns_none_when_no_match(db_proxy):
    result = await route_inbound(db_proxy, _msg("reddit", "random message"))
    assert result is None


@pytest.mark.asyncio
async def test_route_inbound_unknown_channel_returns_none(db_proxy):
    result = await route_inbound(db_proxy, _msg("whatsapp", "pricing"))
    # whatsapp isn't in PLATFORM_FROM_CHANNEL_TYPE → early None
    assert result is None


@pytest.mark.asyncio
async def test_route_inbound_dispatches_on_single_match(db_proxy):
    await _seed_crew(db_proxy, "crew-x", "Sales", [
        {"type": "reactive", "connection_id": "reddit", "keywords": ["pricing"]},
    ])
    result = await route_inbound(db_proxy, _msg("reddit", "what's your pricing?"))
    assert result is not None
    assert result["status"] == "dispatched"
    assert result["crew_id"] == "crew-x"
    assert result["trigger_source"] == "reddit"
    assert result["run_id"]  # a run was created

    # Verify the run record carries the trigger metadata
    run = await db_proxy["crew_runs"].find_one({"run_id": result["run_id"]})
    assert run["trigger_type"] == "reactive"
    assert run["trigger_source"] == "reddit"


@pytest.mark.asyncio
async def test_route_inbound_multi_match_still_dispatches(db_proxy, monkeypatch):
    await _seed_crew(db_proxy, "crew-a", "Sales", [
        {"type": "reactive", "connection_id": "reddit", "keywords": ["pricing"]},
    ])
    await _seed_crew(db_proxy, "crew-b", "Support", [
        {"type": "reactive", "connection_id": "reddit", "keywords": ["pricing"]},
    ])

    # Force disambiguator to pick the second candidate deterministically.
    async def fake_disambiguate(candidates, text):
        return candidates[-1]

    monkeypatch.setattr(
        "services.inbound_router.disambiguate_with_llm", fake_disambiguate
    )

    result = await route_inbound(db_proxy, _msg("reddit", "need pricing help"))
    assert result is not None
    assert result["crew_id"] in {"crew-a", "crew-b"}
