"""
Desktop OAuth Router — Handles OAuth2 flows for desktop app connections.

Provides:
  - GET  /oauth/{provider}/authorize  → Returns auth URL (frontend opens in browser)
  - GET  /oauth/{provider}/callback   → Handles redirect from provider
  - GET  /oauth/{provider}/status     → Check if provider is connected
  - DELETE /oauth/{provider}          → Disconnect / revoke tokens
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/oauth", tags=["oauth"])

# ---------------------------------------------------------------------------
# Provider configurations
# ---------------------------------------------------------------------------

OAUTH_PROVIDERS = {
    "linkedin": {
        "name": "LinkedIn",
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "userinfo_url": "https://api.linkedin.com/v2/userinfo",
        "scopes": ["openid", "profile", "w_member_social", "w_organization_social"],
        "docs_url": "https://learn.microsoft.com/en-us/linkedin/marketing/getting-started",
    },
    "instagram": {
        "name": "Instagram",
        "authorize_url": "https://www.facebook.com/v21.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v21.0/oauth/access_token",
        "userinfo_url": "https://graph.facebook.com/v21.0/me",
        "scopes": ["instagram_basic", "instagram_content_publish", "pages_show_list"],
        "docs_url": "https://developers.facebook.com/docs/instagram-api/",
        "userinfo_params": {"fields": "id,name"},
    },
    "facebook": {
        "name": "Facebook",
        "authorize_url": "https://www.facebook.com/v21.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v21.0/oauth/access_token",
        "userinfo_url": "https://graph.facebook.com/v21.0/me",
        "scopes": ["pages_manage_posts", "pages_read_engagement", "pages_show_list"],
        "docs_url": "https://developers.facebook.com/docs/pages-api/",
        "userinfo_params": {"fields": "id,name"},
    },
}

# The desktop backend port — callback comes back here
DESKTOP_PORT = int(os.environ.get("DESKTOP_BACKEND_PORT", "18741"))
REDIRECT_BASE = f"http://localhost:{DESKTOP_PORT}"

# In-memory state store (single desktop user, fine for this use case)
_pending_states: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class OAuthAuthorizeResponse(BaseModel):
    auth_url: str
    state: str
    provider: str


class OAuthStatusResponse(BaseModel):
    provider: str
    connected: bool
    profile_name: Optional[str] = None
    profile_id: Optional[str] = None
    connected_at: Optional[str] = None
    scopes: Optional[list[str]] = None
    expires_at: Optional[str] = None
    org_id: Optional[str] = None


class OAuthClientConfig(BaseModel):
    client_id: str
    client_secret: str
    org_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Success/error HTML pages shown after OAuth redirect
# ---------------------------------------------------------------------------

SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Connected!</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           display: flex; align-items: center; justify-content: center;
           min-height: 100vh; margin: 0; background: #0a0a0a; color: #fff; }
    .card { text-align: center; padding: 48px; border-radius: 24px;
            background: #171717; border: 1px solid #262626; max-width: 400px; }
    .icon { font-size: 48px; margin-bottom: 16px; }
    h1 { font-size: 24px; margin: 0 0 8px; }
    p { color: #a3a3a3; font-size: 14px; margin: 0 0 24px; }
    .btn { display: inline-block; padding: 10px 24px; border-radius: 12px;
           background: #FF4700; color: #fff; text-decoration: none;
           font-size: 14px; font-weight: 600; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#x2705;</div>
    <h1>__PROVIDER__ Connected</h1>
    <p>Your account has been linked successfully. You can close this window and return to the app.</p>
    <script>
      // Try to close the tab automatically after a short delay
      setTimeout(() => window.close(), 3000);
    </script>
  </div>
</body>
</html>"""

ERROR_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Connection Failed</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           display: flex; align-items: center; justify-content: center;
           min-height: 100vh; margin: 0; background: #0a0a0a; color: #fff; }
    .card { text-align: center; padding: 48px; border-radius: 24px;
            background: #171717; border: 1px solid #262626; max-width: 400px; }
    .icon { font-size: 48px; margin-bottom: 16px; }
    h1 { font-size: 24px; margin: 0 0 8px; }
    p { color: #a3a3a3; font-size: 14px; margin: 0; }
    .error { color: #ef4444; font-size: 12px; margin-top: 12px;
             background: #1c1c1c; padding: 12px; border-radius: 8px;
             text-align: left; word-break: break-word; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#x274C;</div>
    <h1>Connection Failed</h1>
    <p>__ERROR__</p>
    <p class="error">__DETAIL__</p>
  </div>
</body>
</html>"""


def _render_success(provider_name: str) -> str:
    import html as _html
    return SUCCESS_HTML.replace("__PROVIDER__", _html.escape(provider_name))


def _render_error(error: str, detail: str) -> str:
    import html as _html
    return (
        ERROR_HTML
        .replace("__ERROR__", _html.escape(error))
        .replace("__DETAIL__", _html.escape(detail))
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/{provider}/configure")
async def configure_oauth_client(provider: str, config: OAuthClientConfig):
    """
    Store OAuth client credentials (client_id, client_secret) for a provider.
    These are needed before initiating the OAuth flow.
    """
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {provider}")

    db = await get_database()
    collection = db["oauth_connections"]

    update_fields = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    if config.org_id is not None:
        update_fields["org_id"] = config.org_id.strip() or None

    await collection.find_one_and_update(
        {"_id": provider},
        {"$set": update_fields},
        upsert=True,
    )

    return {"status": "configured", "provider": provider}


@router.get("/{provider}/authorize", response_model=OAuthAuthorizeResponse)
async def initiate_oauth(provider: str):
    """
    Generate the OAuth authorization URL. Frontend opens this in the browser.
    """
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {provider}")

    # Load client credentials from DB
    db = await get_database()
    collection = db["oauth_connections"]
    doc = await collection.find_one({"_id": provider})

    if not doc or not doc.get("client_id"):
        raise HTTPException(
            400,
            f"OAuth client not configured for {provider}. "
            f"Please provide client_id and client_secret first."
        )

    provider_config = OAUTH_PROVIDERS[provider]
    state = secrets.token_urlsafe(32)
    redirect_uri = f"{REDIRECT_BASE}/api/v1/oauth/{provider}/callback"

    # Store state for verification
    _pending_states[state] = {
        "provider": provider,
        "created_at": datetime.utcnow().isoformat(),
    }

    # Build authorization URL (urlencode handles spaces in scope and special chars in redirect_uri)
    params = {
        "response_type": "code",
        "client_id": doc["client_id"],
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": " ".join(provider_config["scopes"]),
    }
    auth_url = f"{provider_config['authorize_url']}?{urlencode(params)}"

    return OAuthAuthorizeResponse(
        auth_url=auth_url,
        state=state,
        provider=provider,
    )


@router.get("/{provider}/callback", response_class=HTMLResponse)
async def oauth_callback(
    provider: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """
    OAuth callback handler. The browser redirects here after user authorizes.
    Exchanges the auth code for tokens and stores them.
    """
    if provider not in OAUTH_PROVIDERS:
        return HTMLResponse(
            _render_error("Unknown provider", provider),
            status_code=400,
        )

    # Handle error from provider
    if error:
        # Provide helpful hint for LinkedIn's most common scope error
        detail = error_description or error
        if provider == "linkedin" and "openid" in detail.lower() and "not authorized" in detail.lower():
            detail += (
                " — Open your LinkedIn app → Products tab, and add both "
                "'Sign In with LinkedIn using OpenID Connect' and 'Share on LinkedIn'. "
                "Wait a few seconds after adding, then try again."
            )
        return HTMLResponse(
            _render_error(f"{provider.title()} denied the request", detail),
            status_code=400,
        )

    # Verify state
    if not state or state not in _pending_states:
        return HTMLResponse(
            _render_error(
                "Invalid state parameter",
                "The authorization request may have expired. Please try again.",
            ),
            status_code=400,
        )

    # Clean up state
    state_data = _pending_states.pop(state)

    if not code:
        return HTMLResponse(
            _render_error("No authorization code", "Missing code parameter."),
            status_code=400,
        )

    # Load client credentials
    db = await get_database()
    collection = db["oauth_connections"]
    doc = await collection.find_one({"_id": provider})

    if not doc or not doc.get("client_id"):
        return HTMLResponse(
            _render_error("Client not configured", "OAuth client credentials missing."),
            status_code=500,
        )

    provider_config = OAUTH_PROVIDERS[provider]
    redirect_uri = f"{REDIRECT_BASE}/api/v1/oauth/{provider}/callback"

    # Exchange code for tokens
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                provider_config["token_url"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": doc["client_id"],
                    "client_secret": doc["client_secret"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if token_response.status_code != 200:
            logger.error("Token exchange failed: %s %s", token_response.status_code, token_response.text)
            return HTMLResponse(
                _render_error(
                    "Token exchange failed",
                    f"Status {token_response.status_code}: {token_response.text[:200]}",
                ),
                status_code=400,
            )

        tokens = token_response.json()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in")

        if not access_token:
            return HTMLResponse(
                _render_error("No access token", "Provider did not return an access token."),
                status_code=400,
            )

        # Fetch user profile
        profile_name = None
        profile_id = None
        try:
            userinfo_params = provider_config.get("userinfo_params", {})
            async with httpx.AsyncClient() as client:
                userinfo_resp = await client.get(
                    provider_config["userinfo_url"],
                    params={"access_token": access_token, **userinfo_params}
                    if provider in ("instagram", "facebook")
                    else {},
                    headers={"Authorization": f"Bearer {access_token}"}
                    if provider not in ("instagram", "facebook")
                    else {},
                )
            if userinfo_resp.status_code == 200:
                userinfo = userinfo_resp.json()
                profile_name = userinfo.get("name") or userinfo.get("localizedFirstName", "")
                profile_id = userinfo.get("sub") or userinfo.get("id")
        except Exception:
            logger.warning("Could not fetch user profile for %s", provider)

        # Store tokens in database
        await collection.find_one_and_update(
            {"_id": provider},
            {"$set": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "profile_name": profile_name,
                "profile_id": profile_id,
                "scopes": provider_config["scopes"],
                "status": "connected",
                "connected_at": datetime.utcnow().isoformat() + "Z",
            }},
            upsert=True,
        )

        logger.info("OAuth connected: %s (profile: %s)", provider, profile_name)

        # Resolve provider-specific channel config extras (Meta pages, IG biz id)
        extra_config: dict = {}
        if provider in ("instagram", "facebook"):
            try:
                async with httpx.AsyncClient(timeout=15.0) as mc:
                    pages_resp = await mc.get(
                        "https://graph.facebook.com/v21.0/me/accounts",
                        params={"access_token": access_token},
                    )
                if pages_resp.status_code == 200:
                    pages = (pages_resp.json().get("data") or [])
                    if pages:
                        # TODO: multi-page selection UI — for now pick the first page
                        first_page = pages[0]
                        page_id = first_page.get("id")
                        page_access_token = first_page.get("access_token")

                        if provider == "facebook":
                            if page_id:
                                extra_config["page_id"] = page_id
                            if page_access_token:
                                extra_config["page_access_token"] = page_access_token
                            if not page_id or not page_access_token:
                                logger.warning(
                                    "Facebook page info incomplete (page_id=%s, token=%s)",
                                    bool(page_id), bool(page_access_token),
                                )

                        elif provider == "instagram":
                            # IG business account is linked to a FB page;
                            # fetch it via the page-level token.
                            if page_id and page_access_token:
                                try:
                                    async with httpx.AsyncClient(timeout=15.0) as mc2:
                                        ig_resp = await mc2.get(
                                            f"https://graph.facebook.com/v21.0/{page_id}",
                                            params={
                                                "fields": "instagram_business_account",
                                                "access_token": page_access_token,
                                            },
                                        )
                                    if ig_resp.status_code == 200:
                                        ig_biz = (ig_resp.json() or {}).get(
                                            "instagram_business_account"
                                        )
                                        if ig_biz and ig_biz.get("id"):
                                            extra_config["instagram_user_id"] = ig_biz["id"]
                                            extra_config["page_access_token"] = page_access_token
                                            extra_config["page_id"] = page_id
                                        else:
                                            logger.warning(
                                                "Facebook page %s has no linked Instagram "
                                                "business account — IG publishing disabled",
                                                page_id,
                                            )
                                    else:
                                        logger.warning(
                                            "Failed to fetch IG business account from page %s: "
                                            "%s %s",
                                            page_id, ig_resp.status_code, ig_resp.text[:200],
                                        )
                                except Exception as ig_err:
                                    logger.warning(
                                        "IG business-account lookup failed: %s", ig_err
                                    )
                    else:
                        logger.warning(
                            "%s OAuth: user has no Facebook pages (required for publishing)",
                            provider,
                        )
                else:
                    logger.warning(
                        "%s OAuth: /me/accounts call failed %s: %s",
                        provider, pages_resp.status_code, pages_resp.text[:200],
                    )
            except Exception as meta_err:
                logger.warning(
                    "%s OAuth: page-info lookup failed: %s", provider, meta_err
                )

        # Auto-register a distribution channel so crew publishing works
        # without the user having to register credentials in two places
        try:
            dist_coll = db["distribution_channels"]
            existing = await dist_coll.find_one({"channel_type": provider})
            if not existing:
                import uuid
                channel_config = {"access_token": access_token, **extra_config}
                if provider == "linkedin" and profile_id:
                    # Use org_id for company page, profile_id for personal
                    org_id = doc.get("org_id")
                    if org_id:
                        channel_config["author_urn"] = f"urn:li:organization:{org_id}"
                    else:
                        channel_config["author_urn"] = f"urn:li:person:{profile_id}"
                await dist_coll.insert_one({
                    "_id": str(uuid.uuid4()),
                    "channel_id": str(uuid.uuid4()),
                    "channel_type": provider,
                    "name": f"{profile_name or provider_config['name']} (auto)",
                    "config": channel_config,
                    "organization": "solo",
                    "enabled": True,
                    "publish_count": 0,
                    "last_published_at": None,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "created_by": "oauth-auto",
                })
                logger.info("Auto-created distribution channel for %s", provider)
            else:
                # Update access token and author_urn on existing channel
                update_set = {
                    "config.access_token": access_token,
                    "updated_at": datetime.utcnow().isoformat(),
                }
                if provider == "linkedin":
                    org_id = doc.get("org_id")
                    if org_id:
                        update_set["config.author_urn"] = f"urn:li:organization:{org_id}"
                    elif profile_id:
                        update_set["config.author_urn"] = f"urn:li:person:{profile_id}"
                for k, v in extra_config.items():
                    update_set[f"config.{k}"] = v
                await dist_coll.update_one(
                    {"channel_type": provider},
                    {"$set": update_set},
                )
        except Exception as e:
            logger.warning("Failed to auto-register distribution channel for %s: %s", provider, e)

        return HTMLResponse(
            _render_success(provider_config["name"]),
            status_code=200,
        )

    except Exception as e:
        logger.exception("OAuth callback error for %s", provider)
        return HTMLResponse(
            _render_error("Connection error", str(e)[:200]),
            status_code=500,
        )


class OAuthTestResponse(BaseModel):
    provider: str
    success: bool
    message: str
    profile_name: Optional[str] = None
    profile_id: Optional[str] = None
    response_time_ms: Optional[int] = None


@router.post("/{provider}/test", response_model=OAuthTestResponse)
async def test_oauth_connection(provider: str):
    """
    Test an OAuth connection by making a real API call to the provider.
    Validates that the stored access token is still valid.
    """
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {provider}")

    db = await get_database()
    collection = db["oauth_connections"]
    doc = await collection.find_one({"_id": provider})

    if not doc or doc.get("status") != "connected" or not doc.get("access_token"):
        return OAuthTestResponse(
            provider=provider,
            success=False,
            message="Not connected. Please complete the OAuth flow first.",
        )

    provider_config = OAUTH_PROVIDERS[provider]
    access_token = doc["access_token"]

    import time
    start = time.monotonic()

    try:
        userinfo_params = provider_config.get("userinfo_params", {})
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider in ("instagram", "facebook"):
                resp = await client.get(
                    provider_config["userinfo_url"],
                    params={"access_token": access_token, **userinfo_params},
                )
            else:
                resp = await client.get(
                    provider_config["userinfo_url"],
                    headers={"Authorization": f"Bearer {access_token}"},
                )

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code == 200:
            userinfo = resp.json()
            profile_name = userinfo.get("name") or userinfo.get("localizedFirstName", "")
            profile_id = userinfo.get("sub") or userinfo.get("id")

            # Update profile info in DB if changed
            await collection.find_one_and_update(
                {"_id": provider},
                {"$set": {
                    "profile_name": profile_name,
                    "profile_id": profile_id,
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                }},
            )

            return OAuthTestResponse(
                provider=provider,
                success=True,
                message=f"Connected to {provider_config['name']} as {profile_name}",
                profile_name=profile_name,
                profile_id=profile_id,
                response_time_ms=elapsed_ms,
            )

        elif resp.status_code == 401:
            # Token expired or revoked
            await collection.find_one_and_update(
                {"_id": provider},
                {"$set": {"status": "disconnected", "access_token": None}},
            )
            return OAuthTestResponse(
                provider=provider,
                success=False,
                message="Access token expired or revoked. Please reconnect.",
                response_time_ms=elapsed_ms,
            )

        else:
            return OAuthTestResponse(
                provider=provider,
                success=False,
                message=f"API returned status {resp.status_code}: {resp.text[:200]}",
                response_time_ms=elapsed_ms,
            )

    except httpx.TimeoutException:
        return OAuthTestResponse(
            provider=provider,
            success=False,
            message=f"Connection to {provider_config['name']} timed out after 10 seconds.",
        )
    except Exception as e:
        logger.exception("Test connection failed for %s", provider)
        return OAuthTestResponse(
            provider=provider,
            success=False,
            message=f"Connection error: {str(e)[:200]}",
        )


@router.get("/{provider}/status", response_model=OAuthStatusResponse)
async def get_oauth_status(provider: str):
    """Check connection status for a provider."""
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {provider}")

    db = await get_database()
    collection = db["oauth_connections"]
    doc = await collection.find_one({"_id": provider})

    if not doc or doc.get("status") != "connected":
        return OAuthStatusResponse(provider=provider, connected=False)

    # Compute token expiry from connected_at + expires_in
    expires_at = None
    connected_at = doc.get("connected_at")
    expires_in = doc.get("expires_in")
    if connected_at and expires_in:
        try:
            from datetime import timedelta
            ca = datetime.fromisoformat(connected_at.replace("Z", "+00:00"))
            expires_at = (ca + timedelta(seconds=expires_in)).isoformat()
        except Exception:
            pass

    return OAuthStatusResponse(
        provider=provider,
        connected=True,
        profile_name=doc.get("profile_name"),
        profile_id=doc.get("profile_id"),
        connected_at=connected_at,
        scopes=doc.get("scopes"),
        expires_at=expires_at,
        org_id=doc.get("org_id"),
    )


@router.delete("/{provider}")
async def disconnect_oauth(provider: str):
    """Disconnect and remove stored tokens for a provider."""
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(404, f"Unknown provider: {provider}")

    db = await get_database()
    collection = db["oauth_connections"]

    # Remove tokens but keep client_id/client_secret for re-auth
    doc = await collection.find_one({"_id": provider})
    if doc:
        await collection.find_one_and_update(
            {"_id": provider},
            {"$set": {
                "access_token": None,
                "refresh_token": None,
                "profile_name": None,
                "profile_id": None,
                "status": "disconnected",
                "disconnected_at": datetime.utcnow().isoformat() + "Z",
            }},
        )

    return {"status": "disconnected", "provider": provider}
