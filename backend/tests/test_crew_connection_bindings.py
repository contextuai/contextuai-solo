"""Schema tests for Phase 3 PR 1 — ConnectionBinding, triggers, CrewRun trigger fields."""

import pytest
from pydantic import ValidationError

from models.crew_models import (
    ConnectionBinding,
    CreateCrewRequest,
    CrewAgentConfig,
    CrewRunListItem,
    CrewRunResponse,
    ReactiveTrigger,
    ScheduledTrigger,
)


# ---------------------------------------------------------------------------
# ConnectionBinding
# ---------------------------------------------------------------------------
def test_connection_binding_defaults_direction_to_both():
    cb = ConnectionBinding(connection_id="telegram", platform="telegram")
    assert cb.direction == "both"


def test_connection_binding_rejects_invalid_direction():
    with pytest.raises(ValidationError):
        ConnectionBinding(
            connection_id="telegram",
            platform="telegram",
            direction="sideways",
        )


# ---------------------------------------------------------------------------
# ReactiveTrigger
# ---------------------------------------------------------------------------
def test_reactive_trigger_requires_at_least_one_match_rule():
    with pytest.raises(ValidationError):
        ReactiveTrigger(connection_id="reddit")


def test_reactive_trigger_accepts_keywords_only():
    t = ReactiveTrigger(connection_id="reddit", keywords=["demo"])
    assert t.type == "reactive"
    assert t.keywords == ["demo"]


def test_reactive_trigger_accepts_hashtags_or_mentions():
    t = ReactiveTrigger(connection_id="twitter", hashtags=["#launch"])
    assert t.hashtags == ["#launch"]
    t2 = ReactiveTrigger(connection_id="twitter", mentions=["@me"])
    assert t2.mentions == ["@me"]


# ---------------------------------------------------------------------------
# ScheduledTrigger
# ---------------------------------------------------------------------------
def test_scheduled_trigger_requires_exactly_one_of_cron_or_run_at():
    # Neither
    with pytest.raises(ValidationError):
        ScheduledTrigger(connection_ids=["linkedin"])
    # Both
    with pytest.raises(ValidationError):
        ScheduledTrigger(
            connection_ids=["linkedin"],
            cron="0 9 * * *",
            run_at="2026-05-01T09:00:00Z",
        )


def test_scheduled_trigger_accepts_cron():
    t = ScheduledTrigger(connection_ids=["linkedin"], cron="0 9 * * *")
    assert t.cron == "0 9 * * *"
    assert t.run_at is None


def test_scheduled_trigger_accepts_run_at():
    t = ScheduledTrigger(connection_ids=["linkedin"], run_at="2026-05-01T09:00:00Z")
    assert t.run_at == "2026-05-01T09:00:00Z"


# ---------------------------------------------------------------------------
# CreateCrewRequest — new additive fields
# ---------------------------------------------------------------------------
def _min_agent():
    return CrewAgentConfig(name="Writer", instructions="Write a post")


def test_create_crew_defaults_connection_bindings_and_triggers_to_empty():
    req = CreateCrewRequest(name="C1", agents=[_min_agent()])
    assert req.connection_bindings == []
    assert req.triggers == []
    assert req.approval_required is False


def test_create_crew_accepts_reactive_and_scheduled_triggers():
    req = CreateCrewRequest(
        name="Multi",
        agents=[_min_agent()],
        connection_bindings=[
            ConnectionBinding(
                connection_id="reddit",
                platform="reddit",
                direction="both",
            )
        ],
        triggers=[
            ReactiveTrigger(connection_id="reddit", keywords=["pricing"]),
            ScheduledTrigger(connection_ids=["linkedin"], cron="0 9 * * MON"),
        ],
        approval_required=True,
    )
    assert len(req.triggers) == 2
    assert req.triggers[0].type == "reactive"
    assert req.triggers[1].type == "scheduled"
    assert req.approval_required is True


def test_create_crew_round_trips_through_dict():
    req = CreateCrewRequest(
        name="RT",
        agents=[_min_agent()],
        connection_bindings=[
            ConnectionBinding(connection_id="discord", platform="discord")
        ],
    )
    roundtrip = CreateCrewRequest(**req.model_dump())
    assert roundtrip.connection_bindings[0].connection_id == "discord"


# ---------------------------------------------------------------------------
# CrewRun trigger metadata
# ---------------------------------------------------------------------------
def test_crew_run_response_defaults_to_manual():
    run = CrewRunResponse(
        run_id="r1",
        crew_id="c1",
        user_id="u1",
    )
    assert run.trigger_type == "manual"
    assert run.trigger_source is None


def test_crew_run_response_accepts_reactive_metadata():
    run = CrewRunResponse(
        run_id="r2",
        crew_id="c1",
        user_id="u1",
        trigger_type="reactive",
        trigger_source="reddit",
    )
    assert run.trigger_type == "reactive"
    assert run.trigger_source == "reddit"


def test_crew_run_list_item_accepts_scheduled_metadata():
    item = CrewRunListItem(
        run_id="r3",
        crew_id="c1",
        status="completed",
        trigger_type="scheduled",
        trigger_source="0 9 * * *",
    )
    assert item.trigger_type == "scheduled"
    assert item.trigger_source == "0 9 * * *"


def test_crew_run_response_rejects_invalid_trigger_type():
    with pytest.raises(ValidationError):
        CrewRunResponse(
            run_id="r4",
            crew_id="c1",
            user_id="u1",
            trigger_type="webhook",  # not in the allowed literal
        )
