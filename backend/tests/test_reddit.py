"""Smoke tests for the Reddit connection scaffold.

Uses the shared test_app fixture (real temp SQLite, no MongoDB).
Network calls to Reddit are NOT made — only the /test and /reply endpoints
would hit Reddit, and those are not exercised here.
"""


def test_get_account_when_none_configured(test_app):
    r = test_app.get("/api/v1/reddit/account")
    assert r.status_code == 200
    assert r.json() == {"account": None}


def test_create_account_and_redact_secrets(test_app):
    payload = {
        "client_id": "cid",
        "client_secret": "csecret",
        "username": "u",
        "password": "p",
        "subreddits": ["LocalLLaMA"],
        "keywords": ["local LLM"],
    }
    r = test_app.post("/api/v1/reddit/account", json=payload)
    assert r.status_code == 200
    body = r.json()["account"]
    assert body["password"] == "***"
    assert body["client_secret"] == "***"
    assert body["subreddits"] == ["LocalLLaMA"]
    assert body["enabled"] is True


def test_get_account_after_create_returns_redacted(test_app):
    test_app.post(
        "/api/v1/reddit/account",
        json={
            "client_id": "cid",
            "client_secret": "csecret",
            "username": "u",
            "password": "p",
        },
    )
    r = test_app.get("/api/v1/reddit/account")
    assert r.status_code == 200
    account = r.json()["account"]
    assert account is not None
    assert account["password"] == "***"
    assert account["username"] == "u"


def test_test_connection_errors_without_account(test_app):
    r = test_app.post("/api/v1/reddit/test")
    assert r.status_code == 400


def test_create_replaces_existing_account(test_app):
    first = test_app.post(
        "/api/v1/reddit/account",
        json={"client_id": "a", "client_secret": "b", "username": "u1", "password": "p"},
    ).json()["account"]
    second = test_app.post(
        "/api/v1/reddit/account",
        json={"client_id": "a2", "client_secret": "b2", "username": "u2", "password": "p"},
    ).json()["account"]
    assert first["_id"] != second["_id"]

    r = test_app.get("/api/v1/reddit/account")
    assert r.json()["account"]["username"] == "u2"


def test_invalid_payload_returns_422(test_app):
    r = test_app.post("/api/v1/reddit/account", json={"client_id": "only"})
    assert r.status_code == 422
