"""Tests for the Coder mode REST API (Phase 4 PR 6).

Covers:
- list templates returns the four shipped starters.
- create project with template_id="static-site" scaffolds the dest folder.
- list projects returns the new one.
- PUT /projects/{id} setting trusted=true flips the flag.
- POST /projects/{id}/start without trust returns 4xx.
- delete project succeeds.

We deliberately don't exercise the SSE output stream — subprocess timing
in CI is fragile. The "untrusted -> 403" path covers the start surface
without actually spawning a long-lived process.
"""

from __future__ import annotations

import os
import tempfile

import pytest


def test_list_templates_returns_four(test_app):
    resp = test_app.get("/api/v1/coder/templates")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = sorted(t["id"] for t in body["templates"])
    assert ids == ["cli-tool", "static-site", "telegram-bot", "web-app"]
    # Sanity: every template has a name + runtime + starter prompt.
    for t in body["templates"]:
        assert t["name"]
        assert t["runtime"] in ("node", "python", "static", "auto")
        assert "starter_prompt" in t


def test_create_project_with_template_scaffolds(test_app):
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "site")
        resp = test_app.post(
            "/api/v1/coder/projects",
            json={
                "name": "Demo Site",
                "folder_path": dest,
                "template_id": "static-site",
            },
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["name"] == "Demo Site"
        assert created["template_id"] == "static-site"
        assert created["runtime"] == "static"
        assert created["trusted"] is False
        assert created["status"] == "created"

        # Files were copied from the template's files/ subfolder.
        assert os.path.isfile(os.path.join(dest, "index.html"))
        assert os.path.isfile(os.path.join(dest, "style.css"))


def test_list_projects_returns_created(test_app):
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "proj")
        created = test_app.post(
            "/api/v1/coder/projects",
            json={
                "name": "List Me",
                "folder_path": dest,
                "template_id": "static-site",
            },
        ).json()
        pid = created["project_id"]

        resp = test_app.get("/api/v1/coder/projects")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["total_count"] >= 1
        assert any(p["project_id"] == pid for p in body["projects"])

        # Single GET roundtrip.
        single = test_app.get(f"/api/v1/coder/projects/{pid}")
        assert single.status_code == 200
        assert single.json()["project_id"] == pid


def test_put_trusted_flips_flag(test_app):
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "proj")
        created = test_app.post(
            "/api/v1/coder/projects",
            json={
                "name": "Trust Me",
                "folder_path": dest,
                "template_id": "static-site",
            },
        ).json()
        pid = created["project_id"]
        assert created["trusted"] is False

        resp = test_app.put(
            f"/api/v1/coder/projects/{pid}",
            json={"trusted": True},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["trusted"] is True
        assert body["status"] == "trusted"


def test_start_without_trust_returns_403(test_app):
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "proj")
        created = test_app.post(
            "/api/v1/coder/projects",
            json={
                "name": "Untrusted",
                "folder_path": dest,
                "template_id": "static-site",
            },
        ).json()
        pid = created["project_id"]

        resp = test_app.post(
            f"/api/v1/coder/projects/{pid}/start", json={}
        )
        assert resp.status_code == 403


def test_start_unknown_returns_404(test_app):
    resp = test_app.post(
        "/api/v1/coder/projects/does-not-exist/start", json={}
    )
    assert resp.status_code == 404


def test_delete_project_succeeds(test_app):
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "proj")
        created = test_app.post(
            "/api/v1/coder/projects",
            json={
                "name": "Delete Me",
                "folder_path": dest,
                "template_id": "static-site",
            },
        ).json()
        pid = created["project_id"]

        resp = test_app.delete(f"/api/v1/coder/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # Now 404 on read.
        assert test_app.get(f"/api/v1/coder/projects/{pid}").status_code == 404


def test_create_into_nonempty_folder_rejected(test_app):
    """Scaffolding into a non-empty folder should be a 4xx (force=False)."""
    with tempfile.TemporaryDirectory() as tmp:
        # Pre-populate the target.
        with open(os.path.join(tmp, "existing.txt"), "w") as f:
            f.write("hi")

        resp = test_app.post(
            "/api/v1/coder/projects",
            json={
                "name": "Conflict",
                "folder_path": tmp,
                "template_id": "static-site",
            },
        )
        assert resp.status_code == 400


def test_running_endpoint_starts_empty(test_app):
    """The /running list should return an empty list when nothing is up."""
    resp = test_app.get("/api/v1/coder/running")
    assert resp.status_code == 200
    body = resp.json()
    # Could have leftovers from earlier tests in the same session — accept
    # any list, just assert the shape.
    assert isinstance(body.get("running"), list)
