"""Tests for the Cloud LLM Provider onboarding REST API.

Covers:
- empty-state list
- create + masked-key roundtrip
- update of an existing provider
- 404 on unknown id
- delete removes the row
- /test endpoint returns ok=false without making any network call when the
  config is incomplete (empty api_key short-circuits the dispatcher).

Note: pytest-httpx is not installed in this venv, so we don't mock httpx.
The "bad config returns ok=false" path is exercised via the missing-api_key
short-circuit in CloudProviderService.test_connection — no HTTP call leaves
the test runner.
"""


def test_list_empty(test_app):
    resp = test_app.get("/api/v1/cloud-providers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["providers"] == []
    assert body["total_count"] == 0


def test_create_anthropic_masks_api_key(test_app):
    resp = test_app.post(
        "/api/v1/cloud-providers",
        json={
            "provider_type": "anthropic",
            "display_name": "My Anthropic",
            "config": {"api_key": "sk-ant-secret-12345"},
        },
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["provider_type"] == "anthropic"
    assert created["display_name"] == "My Anthropic"
    # API key must be masked
    assert created["config"]["api_key"] == "***"
    # Provider id is a UUID-looking string
    assert created["provider_id"]
    assert created["connected"] is False
    assert created["last_test_status"] is None

    # Round-trip via list
    listing = test_app.get("/api/v1/cloud-providers").json()
    assert listing["total_count"] == 1
    assert listing["providers"][0]["provider_id"] == created["provider_id"]
    assert listing["providers"][0]["config"]["api_key"] == "***"

    # GET single
    pid = created["provider_id"]
    resp = test_app.get(f"/api/v1/cloud-providers/{pid}")
    assert resp.status_code == 200
    assert resp.json()["provider_id"] == pid
    assert resp.json()["config"]["api_key"] == "***"


def test_create_bedrock_masks_secret(test_app):
    resp = test_app.post(
        "/api/v1/cloud-providers",
        json={
            "provider_type": "bedrock",
            "config": {
                "aws_access_key_id": "AKIAEXAMPLE",
                "aws_secret_access_key": "super-secret",
                "aws_region": "us-east-1",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["provider_type"] == "bedrock"
    # Default display name applied
    assert body["display_name"] == "AWS Bedrock"
    # Access key id is NOT sensitive — should pass through
    assert body["config"]["aws_access_key_id"] == "AKIAEXAMPLE"
    assert body["config"]["aws_region"] == "us-east-1"
    # Secret IS masked
    assert body["config"]["aws_secret_access_key"] == "***"


def test_create_validation_requires_api_key(test_app):
    resp = test_app.post(
        "/api/v1/cloud-providers",
        json={"provider_type": "openai", "config": {}},
    )
    # Pydantic validation kicks in
    assert resp.status_code == 422


def test_post_upserts_same_provider_type(test_app):
    """A second POST for the same provider_type should update, not duplicate."""
    first = test_app.post(
        "/api/v1/cloud-providers",
        json={
            "provider_type": "openai",
            "display_name": "First",
            "config": {"api_key": "sk-first"},
        },
    ).json()

    second = test_app.post(
        "/api/v1/cloud-providers",
        json={
            "provider_type": "openai",
            "display_name": "Second",
            "config": {"api_key": "sk-second"},
        },
    ).json()

    # Same provider_id — upsert
    assert second["provider_id"] == first["provider_id"]
    assert second["display_name"] == "Second"

    listing = test_app.get("/api/v1/cloud-providers").json()
    assert listing["total_count"] == 1


def test_update_existing_provider(test_app):
    created = test_app.post(
        "/api/v1/cloud-providers",
        json={
            "provider_type": "google",
            "display_name": "Initial",
            "config": {"api_key": "google-key-1"},
        },
    ).json()
    pid = created["provider_id"]

    resp = test_app.put(
        f"/api/v1/cloud-providers/{pid}",
        json={"display_name": "Renamed Google"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Renamed Google"
    # Still masked
    assert resp.json()["config"]["api_key"] == "***"

    # Updating with the masked sentinel should NOT overwrite the real key.
    resp = test_app.put(
        f"/api/v1/cloud-providers/{pid}",
        json={"config": {"api_key": "***"}},
    )
    assert resp.status_code == 200


def test_get_unknown_404(test_app):
    resp = test_app.get("/api/v1/cloud-providers/does-not-exist")
    assert resp.status_code == 404


def test_update_unknown_404(test_app):
    resp = test_app.put(
        "/api/v1/cloud-providers/does-not-exist",
        json={"display_name": "x"},
    )
    assert resp.status_code == 404


def test_delete_provider(test_app):
    created = test_app.post(
        "/api/v1/cloud-providers",
        json={
            "provider_type": "anthropic",
            "config": {"api_key": "sk-ant-x"},
        },
    ).json()
    pid = created["provider_id"]

    resp = test_app.delete(f"/api/v1/cloud-providers/{pid}")
    assert resp.status_code == 204

    # Now 404
    assert test_app.get(f"/api/v1/cloud-providers/{pid}").status_code == 404


def test_delete_unknown_404(test_app):
    resp = test_app.delete("/api/v1/cloud-providers/does-not-exist")
    assert resp.status_code == 404


def test_test_arbitrary_missing_api_key_returns_failure(test_app):
    """The dispatcher short-circuits when api_key is missing — no HTTP call.

    pytest-httpx isn't installed in this venv, so we exercise the failure
    path via the empty-key short-circuit instead of mocking httpx.
    """
    resp = test_app.post(
        "/api/v1/cloud-providers/test",
        json={"provider_type": "anthropic", "config": {"api_key": ""}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]
    assert isinstance(body["latency_ms"], int)


def test_test_arbitrary_bedrock_missing_creds_returns_failure(test_app):
    resp = test_app.post(
        "/api/v1/cloud-providers/test",
        json={"provider_type": "bedrock", "config": {}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]


def test_test_existing_persists_failure(test_app):
    created = test_app.post(
        "/api/v1/cloud-providers",
        json={
            "provider_type": "anthropic",
            "config": {"api_key": "sk-ant-real"},
        },
    ).json()
    pid = created["provider_id"]

    # Wipe the api_key out so the probe short-circuits without HTTP.
    test_app.put(
        f"/api/v1/cloud-providers/{pid}",
        json={"config": {"api_key": ""}},
    )

    resp = test_app.post(f"/api/v1/cloud-providers/{pid}/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False

    # The failure was persisted on the row.
    refreshed = test_app.get(f"/api/v1/cloud-providers/{pid}").json()
    assert refreshed["last_test_status"] == "failed"
    assert refreshed["connected"] is False
    assert refreshed["last_tested_at"]


def test_test_existing_unknown_404(test_app):
    resp = test_app.post("/api/v1/cloud-providers/does-not-exist/test")
    assert resp.status_code == 404
