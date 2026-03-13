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
        "scopes": ["openid", "profile", "w_member_social"],
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


class OAuthClientConfig(BaseModel):
    client_id: str
    client_secret: str


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
    <h1>{provider} Connected</h1>
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
             background: #1c1c1c; padding: 12px; border-radius: 8px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#x274C;</div>
    <h1>Connection Failed</h1>
    <p>{error}</p>
    <p class="error">{detail}</p>
  </div>
</body>
</html>"""


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

    await collection.find_one_and_update(
        {"_id": provider},
        {"$set": {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }},
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

    # Build authorization URL
    params = {
        "response_type": "code",
        "client_id": doc["client_id"],
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": " ".join(provider_config["scopes"]),
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"{provider_config['authorize_url']}?{query}"

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
            ERROR_HTML.format(error="Unknown provider", detail=provider),
            status_code=400,
        )

    # Handle error from provider
    if error:
        return HTMLResponse(
            ERROR_HTML.format(
                error=f"{provider.title()} denied the request",
                detail=error_description or error,
            ),
            status_code=400,
        )

    # Verify state
    if not state or state not in _pending_states:
        return HTMLResponse(
            ERROR_HTML.format(
                error="Invalid state parameter",
                detail="The authorization request may have expired. Please try again.",
            ),
            status_code=400,
        )

    # Clean up state
    state_data = _pending_states.pop(state)

    if not code:
        return HTMLResponse(
            ERROR_HTML.format(error="No authorization code", detail="Missing code parameter."),
            status_code=400,
        )

    # Load client credentials
    db = await get_database()
    collection = db["oauth_connections"]
    doc = await collection.find_one({"_id": provider})

    if not doc or not doc.get("client_id"):
        return HTMLResponse(
            ERROR_HTML.format(error="Client not configured", detail="OAuth client credentials missing."),
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
                ERROR_HTML.format(
                    error="Token exchange failed",
                    detail=f"Status {token_response.status_code}: {token_response.text[:200]}",
                ),
                status_code=400,
            )

        tokens = token_response.json()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in")

        if not access_token:
            return HTMLResponse(
                ERROR_HTML.format(error="No access token", detail="Provider did not return an access token."),
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

        return HTMLResponse(
            SUCCESS_HTML.format(provider=provider_config["name"]),
            status_code=200,
        )

    except Exception as e:
        logger.exception("OAuth callback error for %s", provider)
        return HTMLResponse(
            ERROR_HTML.format(error="Connection error", detail=str(e)[:200]),
            status_code=500,
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

    return OAuthStatusResponse(
        provider=provider,
        connected=True,
        profile_name=doc.get("profile_name"),
        profile_id=doc.get("profile_id"),
        connected_at=doc.get("connected_at"),
        scopes=doc.get("scopes"),
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
