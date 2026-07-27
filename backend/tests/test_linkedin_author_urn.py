"""Author-URN selection for the LinkedIn connector.

Regression cover for the case where an `org_id` was configured without the
matching `w_organization_social` scope: the callback used to write an
organization author URN anyway, and every publish then failed with
403 ACCESS_DENIED on /author.
"""

from routers.desktop_oauth import _linkedin_author_urn, _parse_granted_scopes

MEMBER_SCOPES = ["openid", "profile", "w_member_social"]
ORG_SCOPES = MEMBER_SCOPES + ["w_organization_social"]


def test_org_urn_used_when_org_scope_granted():
    assert (
        _linkedin_author_urn("12345", "abc", ORG_SCOPES)
        == "urn:li:organization:12345"
    )


def test_falls_back_to_member_when_org_scope_missing():
    """The bug: org_id set, org scope never granted."""
    assert (
        _linkedin_author_urn("12345", "abc", MEMBER_SCOPES)
        == "urn:li:person:abc"
    )


def test_member_urn_when_no_org_configured():
    assert _linkedin_author_urn(None, "abc", MEMBER_SCOPES) == "urn:li:person:abc"


def test_returns_none_when_nothing_identifies_an_author():
    assert _linkedin_author_urn(None, None, MEMBER_SCOPES) is None


def test_org_id_without_profile_id_does_not_produce_org_urn():
    """No member fallback available, but an unauthorised org URN is still
    worse than no channel config — it would fail on every publish."""
    assert _linkedin_author_urn("12345", None, MEMBER_SCOPES) is None


def test_parse_granted_scopes_handles_both_separators():
    assert _parse_granted_scopes("openid,profile,w_member_social") == MEMBER_SCOPES
    assert _parse_granted_scopes("openid profile w_member_social") == MEMBER_SCOPES


def test_parse_granted_scopes_empty():
    assert _parse_granted_scopes(None) == []
    assert _parse_granted_scopes("") == []
