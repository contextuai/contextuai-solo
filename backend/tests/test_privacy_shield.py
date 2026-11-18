"""SPEC-28: Glass-Box Privacy Shield & Airplane Lock (`backend/services/net_guard.py`, `backend/routers/privacy.py`) tests."""
import pytest
from fastapi.testclient import TestClient

import app as app_module
from services.net_guard import (
    EgressBlockedError,
    assert_egress_allowed,
    clear_egress_ledger,
    get_egress_ledger,
    get_privacy_manifest,
    record_egress,
    set_airplane_lock,
)


def setup_function():
    set_airplane_lock(False)
    clear_egress_ledger()


def teardown_function():
    set_airplane_lock(False)
    clear_egress_ledger()


def test_net_guard_loopback_exempt_and_airplane_lock_blocks_external():
    # Loopback calls never count as external egress and are never blocked
    set_airplane_lock(True)
    assert_egress_allowed("http://127.0.0.1:18741/v1/chat/completions", purpose="local_v1")
    record_egress("http://localhost:18741/api/v1/health", purpose="health")
    assert len(get_egress_ledger()["entries"]) == 0

    # External call is blocked when airplane_lock=True
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed(
            "https://huggingface.co/api/models",
            purpose="hf_hub_search",
        )

    ledger = get_egress_ledger()["entries"]
    assert len(ledger) == 1
    assert ledger[0]["blocked"] is True
    assert ledger[0]["host"] == "huggingface.co"

    # Disable airplane lock -> external call is allowed and logged
    set_airplane_lock(False)
    assert_egress_allowed("https://huggingface.co/api/models", purpose="hf_hub_search")
    record_egress("https://huggingface.co/api/models", purpose="hf_hub_search", bytes_sent=128)
    ledger_after = get_egress_ledger()["entries"]
    assert any(e["blocked"] is False and e["host"] == "huggingface.co" for e in ledger_after)


def test_privacy_router_endpoints(monkeypatch):
    monkeypatch.delenv("CONTEXTUAI_SIDECAR_TOKEN", raising=False)
    client = TestClient(app_module.app)

    r_manifest = client.get("/api/v1/privacy/manifest")
    assert r_manifest.status_code == 200
    data = r_manifest.json()
    assert data["telemetry"] == "none"
    assert len(get_privacy_manifest()["guarantees"]) >= 3

    r_lock = client.post("/api/v1/privacy/airplane-lock", json={"enabled": True})
    assert r_lock.status_code == 200
    assert r_lock.json()["airplane_lock"] is True

    r_ledger = client.get("/api/v1/privacy/ledger")
    assert r_ledger.status_code == 200
    assert r_ledger.json()["airplane_lock"] is True

    client.post("/api/v1/privacy/airplane-lock", json={"enabled": False})
