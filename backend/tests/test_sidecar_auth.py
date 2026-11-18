"""SPEC-01: Sidecar Auth Token + CORS Lockdown (`backend/app.py`) tests."""
import pytest
from fastapi.testclient import TestClient

import app as app_module


def test_cors_origins_locked_down():
    assert "*" not in app_module.ALLOWED_CORS_ORIGINS
    assert "http://tauri.localhost" in app_module.ALLOWED_CORS_ORIGINS
    assert "http://localhost:1420" in app_module.ALLOWED_CORS_ORIGINS


def test_sidecar_token_noop_when_unset(monkeypatch):
    monkeypatch.delenv("CONTEXTUAI_SIDECAR_TOKEN", raising=False)
    client = TestClient(app_module.app)
    resp = client.get("/api/v1/desktop/edition")
    assert resp.status_code == 200
    assert resp.json()["edition"] in ("solo", "lite")


def test_sidecar_token_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("CONTEXTUAI_SIDECAR_TOKEN", "secret-test-token-12345")
    client = TestClient(app_module.app)

    # Exempt health endpoints work without token
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200

    # Protected /api/v1/* endpoint rejects missing or wrong token
    r_missing = client.get("/api/v1/desktop/edition")
    assert r_missing.status_code == 401

    r_wrong = client.get(
        "/api/v1/desktop/edition",
        headers={"X-ContextuAI-Token": "wrong-token"},
    )
    assert r_wrong.status_code == 401

    # Valid X-ContextuAI-Token succeeds
    r_valid_header = client.get(
        "/api/v1/desktop/edition",
        headers={"X-ContextuAI-Token": "secret-test-token-12345"},
    )
    assert r_valid_header.status_code == 200

    # Valid Authorization: Bearer <token> succeeds
    r_valid_bearer = client.get(
        "/api/v1/desktop/edition",
        headers={"Authorization": "Bearer secret-test-token-12345"},
    )
    assert r_valid_bearer.status_code == 200
