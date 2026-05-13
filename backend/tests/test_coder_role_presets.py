"""Tests for CoderRolePresetService — loading and applying the 4 presets (PR 14)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from repositories.coder_agent_role_repository import CoderAgentRoleRepository
from services.coder_role_preset_service import CoderRolePresetService


PRESET_IDS = ["local-solo", "cloud-premium", "hybrid", "custom"]


@pytest.fixture
def preset_service():
    return CoderRolePresetService()


@pytest_asyncio.fixture
async def role_repo(db_proxy):
    return CoderAgentRoleRepository(db_proxy)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def test_list_presets_returns_four(preset_service):
    summaries = preset_service.list_presets()
    ids = sorted(s.preset_id for s in summaries)
    assert ids == sorted(PRESET_IDS)


@pytest.mark.parametrize("preset_id", PRESET_IDS)
def test_preset_schema(preset_service, preset_id):
    detail = preset_service.get_preset(preset_id)
    assert detail is not None, f"Preset '{preset_id}' not found"
    assert detail.preset_id == preset_id
    assert detail.name
    assert detail.description
    assert detail.workflow_mode in ("solo", "sequential", "parallel", "custom")
    assert len(detail.roles) >= 1
    for role in detail.roles:
        assert role.role_kind
        assert role.display_name
        assert role.system_prompt
        # model_id may be "" (not-yet-configured sentinel) or "__DEFAULT__"
        # (custom preset) — both are valid at the schema level.
        assert isinstance(role.model_id, str)
        assert 0.0 <= role.temperature <= 2.0
        assert role.max_tokens > 0


def test_local_solo_has_coder_role(preset_service):
    detail = preset_service.get_preset("local-solo")
    kinds = [r.role_kind.value for r in detail.roles]
    assert "coder" in kinds


def test_local_solo_all_roles_have_empty_model_id(preset_service):
    """After the PR-17 cleanup, local-solo ships no hardcoded model IDs."""
    detail = preset_service.get_preset("local-solo")
    for role in detail.roles:
        assert role.model_id == "", (
            f"Role '{role.display_name}' has model_id={role.model_id!r}; "
            "expected empty string (not-yet-configured sentinel)"
        )


def test_cloud_premium_all_roles_have_empty_model_id(preset_service):
    """After the PR-17 cleanup, cloud-premium ships no hardcoded model IDs."""
    detail = preset_service.get_preset("cloud-premium")
    for role in detail.roles:
        assert role.model_id == "", (
            f"Role '{role.display_name}' has model_id={role.model_id!r}; "
            "expected empty string (not-yet-configured sentinel)"
        )


def test_hybrid_all_roles_have_empty_model_id(preset_service):
    """After the PR-17 cleanup, hybrid ships no hardcoded model IDs."""
    detail = preset_service.get_preset("hybrid")
    for role in detail.roles:
        assert role.model_id == "", (
            f"Role '{role.display_name}' has model_id={role.model_id!r}; "
            "expected empty string (not-yet-configured sentinel)"
        )


def test_custom_uses_default_placeholder(preset_service):
    """The custom preset keeps __DEFAULT__ — user's deliberate intent."""
    detail = preset_service.get_preset("custom")
    model_ids = [r.model_id for r in detail.roles]
    assert "__DEFAULT__" in model_ids


def test_orders_are_sequential(preset_service):
    for pid in PRESET_IDS:
        detail = preset_service.get_preset(pid)
        orders = sorted(r.order for r in detail.roles)
        # Orders must be unique and non-negative.
        assert len(orders) == len(set(orders))
        assert all(o >= 0 for o in orders)


def test_get_unknown_preset_returns_none(preset_service):
    assert preset_service.get_preset("does-not-exist") is None


# ---------------------------------------------------------------------------
# apply_preset
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_preset_inserts_roles(preset_service, role_repo):
    pid = str(uuid.uuid4())
    detail = preset_service.get_preset("local-solo")
    rows = await preset_service.apply_preset(pid, "local-solo", role_repo)
    assert len(rows) == len(detail.roles)
    # All rows tied to the right project.
    assert all(r["project_id"] == pid for r in rows)


@pytest.mark.asyncio
async def test_apply_preset_clears_existing_roles(preset_service, role_repo):
    pid = str(uuid.uuid4())
    # Pre-seed a stale role.
    await role_repo.create({
        "role_id": str(uuid.uuid4()),
        "project_id": pid,
        "role_kind": "custom",
        "display_name": "Old",
        "system_prompt": "Old prompt",
        "model_id": "old-model",
        "temperature": 0.5,
        "max_tokens": 2048,
        "enabled": True,
        "order": 0,
    })

    await preset_service.apply_preset(pid, "custom", role_repo)
    rows = await role_repo.list_for_project(pid)
    # custom preset has exactly 1 role; the old one must be gone.
    assert len(rows) == 1
    assert rows[0]["display_name"] != "Old"


@pytest.mark.asyncio
async def test_apply_unknown_preset_raises_key_error(preset_service, role_repo):
    with pytest.raises(KeyError):
        await preset_service.apply_preset(str(uuid.uuid4()), "no-such-preset", role_repo)


@pytest.mark.asyncio
@pytest.mark.parametrize("preset_id", PRESET_IDS)
async def test_apply_each_preset(preset_service, role_repo, preset_id):
    pid = str(uuid.uuid4())
    rows = await preset_service.apply_preset(pid, preset_id, role_repo)
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_apply_local_solo_roles_have_empty_model_id(preset_service, role_repo):
    """After apply_preset('local-solo'), every role has model_id == ''."""
    pid = str(uuid.uuid4())
    rows = await preset_service.apply_preset(pid, "local-solo", role_repo)
    for row in rows:
        assert row["model_id"] == "", (
            f"Role '{row['display_name']}' has model_id={row['model_id']!r}"
        )


@pytest.mark.asyncio
async def test_apply_cloud_premium_roles_have_empty_model_id(preset_service, role_repo):
    """After apply_preset('cloud-premium'), every role has model_id == ''."""
    pid = str(uuid.uuid4())
    rows = await preset_service.apply_preset(pid, "cloud-premium", role_repo)
    for row in rows:
        assert row["model_id"] == "", (
            f"Role '{row['display_name']}' has model_id={row['model_id']!r}"
        )


@pytest.mark.asyncio
async def test_apply_hybrid_roles_have_empty_model_id(preset_service, role_repo):
    """After apply_preset('hybrid'), every role has model_id == ''."""
    pid = str(uuid.uuid4())
    rows = await preset_service.apply_preset(pid, "hybrid", role_repo)
    for row in rows:
        assert row["model_id"] == "", (
            f"Role '{row['display_name']}' has model_id={row['model_id']!r}"
        )


@pytest.mark.asyncio
async def test_apply_custom_role_has_default_sentinel(preset_service, role_repo):
    """After apply_preset('custom'), the single role has model_id == '__DEFAULT__'."""
    pid = str(uuid.uuid4())
    rows = await preset_service.apply_preset(pid, "custom", role_repo)
    assert len(rows) == 1
    assert rows[0]["model_id"] == "__DEFAULT__"
