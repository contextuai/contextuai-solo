"""Async wrapper over the Twitter/X API v2.

Handles both OAuth 1.0a user context (for posting + DMs) and app-only
bearer tokens (read-only). OAuth 1.0a signing copied from
distribution_service._publish_twitter.
"""
import base64
import hashlib
import hmac
import logging
import secrets
import time
import urllib.parse
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twitter.com"


class TwitterClient:
    """One instance per Twitter account config."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_token_secret: Optional[str] = None,
        bearer_token: Optional[str] = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.bearer_token = bearer_token

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------
    def _has_oauth1(self) -> bool:
        return bool(
            self.api_key
            and self.api_secret
            and self.access_token
            and self.access_token_secret
        )

    def _oauth1_header(
        self,
        method: str,
        url: str,
        query_params: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build an OAuth 1.0a HMAC-SHA1 Authorization header.

        Signature base string includes all oauth_* params plus query
        params (POST bodies signed here are JSON, so they are not part
        of the signature per RFC 5849 section 3.4.1.3.2 when the body
        is not form-encoded).
        """
        nonce = secrets.token_hex(16)
        timestamp = str(int(time.time()))
        oauth_params: Dict[str, str] = {
            "oauth_consumer_key": self.api_key or "",
            "oauth_nonce": nonce,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": timestamp,
            "oauth_token": self.access_token or "",
            "oauth_version": "1.0",
        }

        all_params = {**oauth_params, **(query_params or {})}
        param_str = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
            for k, v in sorted(all_params.items())
        )
        base_string = (
            f"{method.upper()}&"
            f"{urllib.parse.quote(url, safe='')}&"
            f"{urllib.parse.quote(param_str, safe='')}"
        )
        signing_key = (
            f"{urllib.parse.quote(self.api_secret or '', safe='')}&"
            f"{urllib.parse.quote(self.access_token_secret or '', safe='')}"
        )
        signature = hmac.new(
            signing_key.encode(), base_string.encode(), hashlib.sha1
        ).digest()
        oauth_params["oauth_signature"] = base64.b64encode(signature).decode()

        return "OAuth " + ", ".join(
            f'{k}="{urllib.parse.quote(v, safe="")}"'
            for k, v in sorted(oauth_params.items())
        )

    def _read_headers(self) -> Dict[str, str]:
        """Return headers suitable for read endpoints.

        Bearer token preferred if available (simpler, higher rate-limit on
        free tier); otherwise falls back to OAuth 1.0a user context.
        """
        if self.bearer_token:
            return {"Authorization": f"Bearer {self.bearer_token}"}
        if not self._has_oauth1():
            raise RuntimeError(
                "Twitter read requires either bearer_token or OAuth 1.0a creds"
            )
        return {}  # caller must build OAuth1 header with per-request url/params

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------
    async def test_connection(self) -> Dict[str, Any]:
        """GET /2/users/me — verify credentials."""
        url = f"{BASE_URL}/2/users/me"
        async with httpx.AsyncClient(timeout=15.0) as client:
            if self.bearer_token:
                r = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.bearer_token}"},
                )
            elif self._has_oauth1():
                r = await client.get(
                    url, headers={"Authorization": self._oauth1_header("GET", url)}
                )
            else:
                raise RuntimeError("No Twitter credentials configured")

        if r.status_code != 200:
            raise RuntimeError(f"Twitter auth failed ({r.status_code}): {r.text[:200]}")
        data = r.json().get("data", {})
        return {
            "ok": True,
            "id": data.get("id"),
            "username": data.get("username"),
            "name": data.get("name"),
        }

    async def fetch_mentions(
        self,
        user_id: str,
        since_id: Optional[str] = None,
        max_results: int = 25,
    ) -> List[Dict[str, Any]]:
        """GET /2/users/:id/mentions — newest-first list of mentions."""
        url = f"{BASE_URL}/2/users/{user_id}/mentions"
        params: Dict[str, str] = {
            "max_results": str(max(5, min(max_results, 100))),
            "tweet.fields": "author_id,conversation_id,created_at",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        if since_id:
            params["since_id"] = since_id

        async with httpx.AsyncClient(timeout=15.0) as client:
            if self.bearer_token:
                r = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.bearer_token}"},
                    params=params,
                )
            elif self._has_oauth1():
                r = await client.get(
                    url,
                    headers={"Authorization": self._oauth1_header("GET", url, params)},
                    params=params,
                )
            else:
                raise RuntimeError("No Twitter credentials configured")

        if r.status_code != 200:
            logger.warning("Twitter mentions fetch failed %s: %s", r.status_code, r.text[:200])
            return []

        body = r.json()
        tweets = body.get("data", []) or []
        users = {u["id"]: u for u in (body.get("includes", {}).get("users", []) or [])}

        items: List[Dict[str, Any]] = []
        for t in tweets:
            author = users.get(t.get("author_id", ""), {})
            items.append(
                {
                    "id": t.get("id"),
                    "text": t.get("text", ""),
                    "author_id": t.get("author_id"),
                    "author_name": author.get("username") or author.get("name") or t.get("author_id"),
                    "conversation_id": t.get("conversation_id"),
                    "created_at": t.get("created_at"),
                }
            )
        return items

    async def fetch_dm_events(
        self,
        since_id: Optional[str] = None,
        max_results: int = 25,
    ) -> List[Dict[str, Any]]:
        """GET /2/dm_events — newest-first list of inbound DMs.

        Requires OAuth 1.0a (user context) — bearer token cannot read DMs.
        """
        url = f"{BASE_URL}/2/dm_events"
        params: Dict[str, str] = {
            "max_results": str(max(5, min(max_results, 100))),
            "dm_event.fields": "sender_id,text,created_at,event_type",
            "event_types": "MessageCreate",
        }
        if since_id:
            params["since_id"] = since_id

        async with httpx.AsyncClient(timeout=15.0) as client:
            if self._has_oauth1():
                r = await client.get(
                    url,
                    headers={"Authorization": self._oauth1_header("GET", url, params)},
                    params=params,
                )
            elif self.bearer_token:
                # DMs technically require user-context, but attempt bearer
                # for free-tier accounts that have elevated it.
                r = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.bearer_token}"},
                    params=params,
                )
            else:
                raise RuntimeError("No Twitter credentials configured")

        if r.status_code != 200:
            logger.warning("Twitter DM fetch failed %s: %s", r.status_code, r.text[:200])
            return []

        events = r.json().get("data", []) or []
        items: List[Dict[str, Any]] = []
        for e in events:
            if e.get("event_type") != "MessageCreate":
                continue
            items.append(
                {
                    "id": e.get("id"),
                    "text": e.get("text", ""),
                    "sender_id": e.get("sender_id"),
                    "created_at": e.get("created_at"),
                }
            )
        return items

    async def reply_to_tweet(self, tweet_id: str, text: str) -> Dict[str, Any]:
        """POST /2/tweets — reply to a tweet (requires OAuth 1.0a)."""
        if not self._has_oauth1():
            raise RuntimeError("Posting tweets requires OAuth 1.0a user context")

        url = f"{BASE_URL}/2/tweets"
        payload = {
            "text": text[:280],
            "reply": {"in_reply_to_tweet_id": tweet_id},
        }
        headers = {
            "Authorization": self._oauth1_header("POST", url),
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Twitter reply failed ({r.status_code}): {r.text[:200]}")
        data = r.json().get("data", {})
        return {"ok": True, "tweet_id": data.get("id")}

    async def send_dm(self, recipient_user_id: str, text: str) -> Dict[str, Any]:
        """POST /2/dm_conversations/with/:id/messages — send a DM.

        Requires OAuth 1.0a user context.
        """
        if not self._has_oauth1():
            raise RuntimeError("Sending DMs requires OAuth 1.0a user context")

        url = f"{BASE_URL}/2/dm_conversations/with/{recipient_user_id}/messages"
        headers = {
            "Authorization": self._oauth1_header("POST", url),
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json={"text": text[:10000]}, headers=headers)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Twitter DM failed ({r.status_code}): {r.text[:200]}")
        data = r.json().get("data", {})
        return {"ok": True, "dm_event_id": data.get("dm_event_id")}
