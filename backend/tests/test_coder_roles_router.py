"""Integration tests for coder_roles router (PR 14).

Covers all happy paths + validation error paths for:
- GET/POST /api/v1/coder/projects/{id}/roles
- PUT/DELETE /api/v1/coder/projects/{id}/roles/{role_id}
- POST /api/v1/coder/projects/{id}/roles/apply-preset
- PUT  /api/v1/coder/projects/{id}/roles/reorder
"""

from __future__ import annotations

import os
import tempfile

import pytest


VALID_ROLE = {
    "role_kind": "coder",
    "display_name": "Coder",
    "system_prompt": "You are an expert software engineer.",
    "model_id": "qwen2.5-coder-7b",
    "temperature": 0.3,
    "max_tokens": 2048,
}


def _create_project(client) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "proj")
        r = client.post(
            "/api/v1/coder/projects",
            json={"name": "Test Proj", "folder_path": dest, "template_id": "static-site"},
        )
        assert r.status_code == 201, r.text
        return r.json()["project_id"]


# ---------------------------------------------------------------------------
# List / create
# ---------------------------------------------------------------------------

def test_list_roles_empty(test_app):
    pid = _create_project(test_app)
    r = test_app.get(f"/api/v1/coder/projects/{pid}/roles")
    assert r.status_code == 200
    assert r.json() == []


def test_create_role_happy_path(test_app):
    pid = _create_project(test_app)
    r = test_app.post(f"/api/v1/coder/projects/{pid}/roles", json=VALID_ROLE)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_id"] == pid
    assert body["role_kind"] == "coder"
    assert body["order"] == 0  # auto-assigned


def test_create_role_auto_increments_order(test_app):
    pid = _create_project(test_app)
    test_app.post(f"/api/v1/coder/projects/{pid}/roles", json=VALID_ROLE)
    r2 = test_app.post(
        f"/api/v1/coder/projects/{pid}/roles",
        json={**VALID_ROLE, "role_kind": "reviewer"},
    )
    assert r2.json()["order"] == 1


def test_list_roles_sorted_by_order(test_app):
    pid = _create_project(test_app)
    for kind, order in [("reviewer", 2), ("coder", 0), ("planner", 1)]:
        test_app.post(
            f"/api/v1/coder/projects/{pid}/roles",
            json={**VALID_ROLE, "role_kind": kind, "order": order},
        )
    rows = test_app.get(f"/api/v1/coder/projects/{pid}/roles").json()
    orders = [r["order"] for r in rows]
    assert orders == sorted(orders)


def test_create_role_unknown_project_returns_404(test_app):
    r = test_app.post("/api/v1/coder/projects/no-such-project/roles", json=VALID_ROLE)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_create_role_empty_system_prompt_rejected(test_app):
    pid = _create_project(test_app)
    r = test_app.post(
        f"/api/v1/coder/projects/{pid}/roles",
        json={**VALID_ROLE, "system_prompt": ""},
    )
    assert r.status_code == 422


def test_create_role_empty_model_id_accepted(test_app):
    """Empty model_id is now valid — it is the 'not yet configured' sentinel.

    The workflow service will fail fast with a clear error if the user tries
    to run a role that still has model_id == "".
    """
    pid = _create_project(test_app)
    r = test_app.post(
        f"/api/v1/coder/projects/{pid}/roles",
        json={**VALID_ROLE, "model_id": ""},
    )
    assert r.status_code == 201, r.text
    assert r.json()["model_id"] == ""


def test_create_role_whitespace_model_id_rejected(test_app):
    pid = _create_project(test_app)
    r = test_app.post(
        f"/api/v1/coder/projects/{pid}/roles",
        json={**VALID_ROLE, "model_id": "   "},
    )
    assert r.status_code == 422


def test_create_role_unknown_role_kind_rejected(test_app):
    pid = _create_project(test_app)
    r = test_app.post(
        f"/api/v1/coder/projects/{pid}/roles",
        json={**VALID_ROLE, "role_kind": "not_a_real_kind"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Update / delete
# ---------------------------------------------------------------------------

def test_update_role(test_app):
    pid = _create_project(test_app)
    created = test_app.post(f"/api/v1/coder/projects/{pid}/roles", json=VALID_ROLE).json()
    role_id = created["role_id"]

    r = test_app.put(
        f"/api/v1/coder/projects/{pid}/roles/{role_id}",
        json={"display_name": "Senior Coder", "enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Senior Coder"
    assert r.json()["enabled"] is False


def test_update_nonexistent_role_returns_404(test_app):
    pid = _create_project(test_app)
    r = test_app.put(
        f"/api/v1/coder/projects/{pid}/roles/ghost-role-id",
        json={"display_name": "x"},
    )
    assert r.status_code == 404


def test_update_empty_body_returns_400(test_app):
    pid = _create_project(test_app)
    created = test_app.post(f"/api/v1/coder/projects/{pid}/roles", json=VALID_ROLE).json()
    r = test_app.put(
        f"/api/v1/coder/projects/{pid}/roles/{created['role_id']}",
        json={},
    )
    assert r.status_code == 400


def test_delete_role(test_app):
    pid = _create_project(test_app)
    created = test_app.post(f"/api/v1/coder/projects/{pid}/roles", json=VALID_ROLE).json()
    role_id = created["role_id"]

    r = test_app.delete(f"/api/v1/coder/projects/{pid}/roles/{role_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    rows = test_app.get(f"/api/v1/coder/projects/{pid}/roles").json()
    assert not any(row["role_id"] == role_id for row in rows)


def test_delete_nonexistent_role_returns_404(test_app):
    pid = _create_project(test_app)
    r = test_app.delete(f"/api/v1/coder/projects/{pid}/roles/ghost")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Apply preset
# ---------------------------------------------------------------------------

def test_apply_preset_local_solo(test_app):
    pid = _create_project(test_app)
    r = test_app.post(
        f"/api/v1/coder/projects/{pid}/roles/apply-preset",
        json={"preset_id": "local-solo"},
    )
    assert r.status_code == 200
    roles = r.json()
    assert len(roles) >= 1
    assert all(role["project_id"] == pid for role in roles)


def test_apply_preset_replaces_existing(test_app):
    pid = _create_project(test_app)
    test_app.post(f"/api/v1/coder/projects/{pid}/roles", json=VALID_ROLE)
    test_app.post(
        f"/api/v1/coder/projects/{pid}/roles/apply-preset",
        json={"preset_id": "custom"},
    )
    rows = test_app.get(f"/api/v1/coder/projects/{pid}/roles").json()
    # custom preset has exactly 1 role
    assert len(rows) == 1


def test_apply_unknown_preset_returns_404(test_app):
    pid = _create_project(test_app)
    r = test_app.post(
        f"/api/v1/coder/projects/{pid}/roles/apply-preset",
        json={"preset_id": "no-such-preset"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------

def test_reorder_roles(test_app):
    pid = _create_project(test_app)
    r1 = test_app.post(f"/api/v1/coder/projects/{pid}/roles", json={**VALID_ROLE, "role_kind": "coder"}).json()
    r2 = test_app.post(f"/api/v1/coder/projects/{pid}/roles", json={**VALID_ROLE, "role_kind": "reviewer"}).json()
    r3 = test_app.post(f"/api/v1/coder/projects/{pid}/roles", json={**VALID_ROLE, "role_kind": "planner"}).json()

    new_order = [r3["role_id"], r1["role_id"], r2["role_id"]]
    r = test_app.put(
        f"/api/v1/coder/projects/{pid}/roles/reorder",
        json={"role_ids": new_order},
    )
    assert r.status_code == 200
    result_ids = [row["role_id"] for row in r.json()]
    assert result_ids == new_order


def test_reorder_mismatched_count_returns_400(test_app):
    pid = _create_project(test_app)
    r1 = test_app.post(f"/api/v1/coder/projects/{pid}/roles", json=VALID_ROLE).json()
    r2 = test_app.post(f"/api/v1/coder/projects/{pid}/roles", json={**VALID_ROLE, "role_kind": "reviewer"}).json()

    # Send only one ID when there are two roles.
    r = test_app.put(
        f"/api/v1/coder/projects/{pid}/roles/reorder",
        json={"role_ids": [r1["role_id"]]},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Preset discovery endpoints
# ---------------------------------------------------------------------------

def test_list_role_presets(test_app):
    r = test_app.get("/api/v1/coder/role-presets")
    assert r.status_code == 200
    presets = r.json()
    preset_ids = sorted(p["preset_id"] for p in presets)
    assert preset_ids == sorted(["local-solo", "cloud-premium", "hybrid", "custom"])


def test_get_role_preset_detail(test_app):
    r = test_app.get("/api/v1/coder/role-presets/local-solo")
    assert r.status_code == 200
    body = r.json()
    assert body["preset_id"] == "local-solo"
    assert "roles" in body
    assert len(body["roles"]) >= 1


def test_get_unknown_preset_detail_returns_404(test_app):
    r = test_app.get("/api/v1/coder/role-presets/nonexistent")
    assert r.status_code == 404
