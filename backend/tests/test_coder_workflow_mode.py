"""Tests for the /workflow endpoints (PR 14)."""

from __future__ import annotations

import os
import tempfile

import pytest


def _create_project(client) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "proj")
        r = client.post(
            "/api/v1/coder/projects",
            json={"name": "Workflow Test", "folder_path": dest, "template_id": "static-site"},
        )
        assert r.status_code == 201, r.text
        return r.json()["project_id"]


def test_get_workflow_default_is_solo(test_app):
    pid = _create_project(test_app)
    r = test_app.get(f"/api/v1/coder/projects/{pid}/workflow")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == pid
    assert body["workflow_mode"] == "solo"


def test_put_workflow_mode_sequential(test_app):
    pid = _create_project(test_app)
    r = test_app.put(
        f"/api/v1/coder/projects/{pid}/workflow",
        json={"workflow_mode": "sequential"},
    )
    assert r.status_code == 200
    assert r.json()["workflow_mode"] == "sequential"

    # Verify persisted.
    r2 = test_app.get(f"/api/v1/coder/projects/{pid}/workflow")
    assert r2.json()["workflow_mode"] == "sequential"


def test_put_workflow_mode_parallel(test_app):
    pid = _create_project(test_app)
    r = test_app.put(
        f"/api/v1/coder/projects/{pid}/workflow",
        json={"workflow_mode": "parallel"},
    )
    assert r.status_code == 200
    assert r.json()["workflow_mode"] == "parallel"


def test_put_workflow_mode_custom(test_app):
    pid = _create_project(test_app)
    r = test_app.put(
        f"/api/v1/coder/projects/{pid}/workflow",
        json={"workflow_mode": "custom"},
    )
    assert r.status_code == 200
    assert r.json()["workflow_mode"] == "custom"


def test_put_invalid_workflow_mode_returns_422(test_app):
    pid = _create_project(test_app)
    r = test_app.put(
        f"/api/v1/coder/projects/{pid}/workflow",
        json={"workflow_mode": "turbo_hyper_mode"},
    )
    assert r.status_code == 422


def test_get_workflow_unknown_project_returns_404(test_app):
    r = test_app.get("/api/v1/coder/projects/no-such-project/workflow")
    assert r.status_code == 404


def test_put_workflow_unknown_project_returns_404(test_app):
    r = test_app.put(
        "/api/v1/coder/projects/no-such-project/workflow",
        json={"workflow_mode": "solo"},
    )
    assert r.status_code == 404


def test_project_response_includes_workflow_mode(test_app):
    """CoderProjectResponse must expose workflow_mode."""
    pid = _create_project(test_app)
    r = test_app.get(f"/api/v1/coder/projects/{pid}")
    assert r.status_code == 200
    assert "workflow_mode" in r.json()
    assert r.json()["workflow_mode"] == "solo"


def test_roundtrip_through_all_modes(test_app):
    pid = _create_project(test_app)
    for mode in ("solo", "sequential", "parallel", "custom"):
        r = test_app.put(
            f"/api/v1/coder/projects/{pid}/workflow",
            json={"workflow_mode": mode},
        )
        assert r.status_code == 200, r.text
        assert r.json()["workflow_mode"] == mode
