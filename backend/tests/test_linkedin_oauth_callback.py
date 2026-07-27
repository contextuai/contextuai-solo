"""Integration cover for the LinkedIn OAuth callback's channel registration.

Drives the real /oauth/linkedin/callback route with LinkedIn's HTTP calls
faked, and asserts which author URN lands on the auto-registered
distribution channel.

The regression guarded here: an `org_id` configured without the matching
`w_organization_social` grant used to produce an organization author URN,
which made every subsequent publish fail with 403 ACCESS_DENIED on /author.
"""

import json

import pytest

from routers import desktop_oauth


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.headers: dict = {}
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient for both LinkedIn calls."""

    granted_scope = ""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        # Token exchange
        return _FakeResponse(200, {
            "access_token": "test-access-token",
            "expires_in": 5183999,
            "scope": type(self).granted_scope,
        })

    async def get(self, url, **kwargs):
        # userinfo
        return _FakeResponse(200, {"name": "Test User", "sub": "person123"})


@pytest.fixture
def linkedin_oauth(test_app, db_proxy, monkeypatch):
    """Point the callback at the temp DB and fake out LinkedIn."""
    async def _get_db():
        return db_proxy

    # The router did `from database import get_database`, so it holds its own
    # reference — patching the database module alone would not reach it.
    monkeypatch.setattr(desktop_oauth, "get_database", _get_db)
    monkeypatch.setattr(desktop_oauth.httpx, "AsyncClient", _FakeAsyncClient)
    return test_app


def _connect(client, granted_scope: str, org_id: str | None):
    """Run configure -> authorize -> callback, return the created channel."""
    _FakeAsyncClient.granted_scope = granted_scope

    body = {"client_id": "test-client", "client_secret": "test-secret"}
    if org_id is not None:
        body["org_id"] = org_id
    assert client.post("/api/v1/oauth/linkedin/configure", json=body).status_code == 200

    state = client.get("/api/v1/oauth/linkedin/authorize").json()["state"]

    resp = client.get(
        "/api/v1/oauth/linkedin/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )
    assert resp.status_code == 200, resp.text

    rows = client.get("/api/v1/distribution/channels").json()["data"]["channels"]
    linkedin = [c for c in rows if c.get("channel_type") == "linkedin"]
    assert len(linkedin) == 1, f"expected one linkedin channel, got {rows}"
    return linkedin[0]


def test_org_id_without_org_scope_falls_back_to_member(linkedin_oauth):
    """The regression: org configured, LinkedIn grants member scopes only."""
    channel = _connect(
        linkedin_oauth,
        granted_scope="openid,profile,w_member_social",
        org_id="230066020",
    )
    assert channel["config"]["author_urn"] == "urn:li:person:person123"


def test_org_scope_granted_uses_org_urn(linkedin_oauth):
    channel = _connect(
        linkedin_oauth,
        granted_scope="openid,profile,w_member_social,w_organization_social",
        org_id="230066020",
    )
    assert channel["config"]["author_urn"] == "urn:li:organization:230066020"


def test_no_org_configured_uses_member_urn(linkedin_oauth):
    channel = _connect(
        linkedin_oauth,
        granted_scope="openid,profile,w_member_social",
        org_id=None,
    )
    assert channel["config"]["author_urn"] == "urn:li:person:person123"


def test_status_reports_granted_scopes_not_requested(linkedin_oauth):
    """Status must not claim a scope LinkedIn withheld."""
    _connect(
        linkedin_oauth,
        granted_scope="openid,profile,w_member_social",
        org_id="230066020",
    )
    status = linkedin_oauth.get("/api/v1/oauth/linkedin/status").json()
    assert status["connected"] is True
    assert "w_organization_social" not in status["scopes"]
    assert status["scopes"] == ["openid", "profile", "w_member_social"]
