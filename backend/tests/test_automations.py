"""Tests for the Automations REST API.

Covers:
- empty-state list
- create + roundtrip
- prompt validation (regex parse + persona detection against the agent library)
- prompt validation when an unknown @agent is referenced
- run with an unknown automation_id (404)
- update + delete lifecycle
"""

import pytest


def _seed_agent(db_proxy, slug: str, name: str = None):
    """Insert a minimal workspace_agents row for validation tests."""
    import asyncio

    async def _do():
        coll = db_proxy["workspace_agents"]
        await coll.insert_one(
            {
                "_id": f"marketing-sales-{slug}",
                "agent_id": f"marketing-sales-{slug}",
                "slug": slug,
                "name": name or slug,
                "system_prompt": "You are a helpful agent.",
                "is_active": True,
            }
        )

    asyncio.get_event_loop().run_until_complete(_do())


def test_list_empty(test_app):
    resp = test_app.get("/api/v1/automations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["automations"] == []
    assert body["total_count"] == 0


def test_create_and_get(test_app):
    payload = {
        "name": "Weekly LinkedIn",
        "description": "Daily AI funding round-up",
        "prompt_template": "@market-researcher pull AI funding news, then @blog-writer summarise it.",
        "trigger_type": "manual",
    }
    resp = test_app.post("/api/v1/automations", json=payload)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["name"] == "Weekly LinkedIn"
    assert sorted(created["personas_detected"]) == ["blog-writer", "market-researcher"]
    assert created["execution_mode"] in ("sequential", "smart", "parallel")

    # Read back
    aid = created["automation_id"]
    resp = test_app.get(f"/api/v1/automations/{aid}")
    assert resp.status_code == 200
    assert resp.json()["automation_id"] == aid

    # In list
    resp = test_app.get("/api/v1/automations")
    body = resp.json()
    assert body["total_count"] == 1
    assert body["automations"][0]["automation_id"] == aid


def test_validate_detects_personas_and_unknown(test_app, db_proxy):
    _seed_agent(db_proxy, slug="market-researcher")

    # Known agent → no errors.
    resp = test_app.post(
        "/api/v1/automations/validate",
        json={"prompt_template": "@market-researcher pull funding stats."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["personas_detected"] == ["market-researcher"]
    assert body["errors"] == []

    # Unknown agent → flagged as error.
    resp = test_app.post(
        "/api/v1/automations/validate",
        json={"prompt_template": "@nonexistent-agent do a thing"},
    )
    body = resp.json()
    assert body["is_valid"] is False
    assert any("nonexistent-agent" in e for e in body["errors"])


def test_validate_no_personas(test_app):
    resp = test_app.post(
        "/api/v1/automations/validate",
        json={"prompt_template": "Just a prose request, no @ mentions."},
    )
    body = resp.json()
    assert body["is_valid"] is False
    assert body["personas_detected"] == []
    assert any("No @agents" in w for w in body["warnings"])


def test_run_unknown_404(test_app):
    resp = test_app.post(
        "/api/v1/automations/does-not-exist/run", json={}
    )
    assert resp.status_code == 404


def test_update_and_delete(test_app):
    created = test_app.post(
        "/api/v1/automations",
        json={
            "name": "Initial",
            "prompt_template": "@a-agent do something",
        },
    ).json()
    aid = created["automation_id"]

    # Update name + status
    resp = test_app.put(
        f"/api/v1/automations/{aid}",
        json={"name": "Renamed", "status": "active"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    assert resp.json()["status"] == "active"

    # Delete
    resp = test_app.delete(f"/api/v1/automations/{aid}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Now 404
    assert test_app.get(f"/api/v1/automations/{aid}").status_code == 404


def test_promote_without_personas_400(test_app):
    """Cannot promote an automation that has no @mentions."""
    created = test_app.post(
        "/api/v1/automations",
        json={
            "name": "No agents",
            "prompt_template": "Just write a haiku about Mondays.",
        },
    ).json()
    aid = created["automation_id"]
    resp = test_app.post(f"/api/v1/automations/{aid}/promote-to-crew", json={})
    assert resp.status_code == 400
