"""Tests for the sample crew seeder.

Verifies it seeds ready-to-run example crews (writer -> reviewer -> finalizer),
resolves library-agent system prompts into instructions, and is idempotent so
samples don't reappear after a user deletes them.
"""

import pytest

from services.sample_crew_seeder import (
    seed_sample_crews,
    FINALIZER_INSTRUCTIONS,
    DESKTOP_USER_ID,
)
from repositories.crew_repository import CrewRepository

# The library-agent ids the samples reference.
_LIB_IDS = [
    "marketing_sales-social-media-manager",
    "social_engagement-brand-voice-guardian",
    "social_engagement-content-repurposer",
]


async def _seed_library_agents(db):
    for aid in _LIB_IDS:
        await db["workspace_agents"].insert_one({
            "agent_id": aid,
            "name": aid.split("-", 1)[-1].replace("-", " ").title(),
            "system_prompt": f"You are {aid}. " + ("x" * 80),
            "is_active": True,
        })


@pytest.mark.asyncio
async def test_seeds_sample_crews_with_finalizer(db_proxy):
    await _seed_library_agents(db_proxy)

    created = await seed_sample_crews(db_proxy)
    assert created == 2

    crews, _ = await CrewRepository(db_proxy).get_user_crews(DESKTOP_USER_ID, limit=50)
    names = {c["name"] for c in crews}
    assert "LinkedIn Content Pipeline (Sample)" in names

    pipeline = next(c for c in crews if c["name"] == "LinkedIn Content Pipeline (Sample)")
    agents = pipeline["agents"]
    assert len(agents) == 3
    # Every agent got an id and real instructions.
    assert all(a.get("agent_id") for a in agents)
    assert all(len(a.get("instructions") or "") > 0 for a in agents)
    # Last step is the finalizer (the deliverable producer).
    assert agents[-1]["name"] == "Finalizer"
    assert agents[-1]["role"] == "editor"
    assert agents[-1]["instructions"] == FINALIZER_INSTRUCTIONS
    assert agents[-1].get("library_agent_id") is None


@pytest.mark.asyncio
async def test_seeding_is_idempotent(db_proxy):
    await _seed_library_agents(db_proxy)
    first = await seed_sample_crews(db_proxy)
    assert first == 2
    # Second run is gated by the seed flag — nothing new.
    second = await seed_sample_crews(db_proxy)
    assert second == 0


@pytest.mark.asyncio
async def test_skips_sample_when_library_agent_missing(db_proxy):
    # No library agents inserted → samples can't resolve → none created,
    # but the run still completes without raising.
    created = await seed_sample_crews(db_proxy)
    assert created == 0
