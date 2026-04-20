"""
ConnectionService — unified read/write over every credential store.

Surfaces a single list of `ConnectionSummary` records merging:
  - oauth_connections (linkedin / instagram / facebook — OAuth2)
  - reddit_accounts (token-paste)
  - twitter_accounts (OAuth 1.0a + bearer)
  - channel_registrations (telegram / discord — token-paste)
  - distribution_channels (blog / email / slack_webhook — the new outbound-only types)

Each summary carries a `store` discriminator and a prefixed `id`
(e.g. `oauth:linkedin`, `reddit:abc123`) so PATCH/DELETE can route back
to the originating collection without ambiguity.

Capability flags (`inbound_enabled` / `outbound_enabled`) are read from
raw records with `.get(..., default)` — works whether PR 1's typed-model
defaults have migrated yet or not.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from models.connection_models import (
    OUTBOUND_ONLY_PLATFORMS,
    PLATFORM_CAPABILITIES,
    CapabilityUpdate,
    ConnectionSummary,
    OutboundConnectionCreate,
    OutboundConnectionUpdate,
)
from services.distribution_service import DistributionService


# Map ConnectionService platform slug → distribution_service.channel_type
# (slack_webhook is our platform name; the underlying publisher in
# distribution_service keys the record as "slack".)
PLATFORM_TO_DIST_CHANNEL_TYPE = {
    "blog": "blog",
    "email": "email",
    "slack_webhook": "slack",
}
DIST_CHANNEL_TYPE_TO_PLATFORM = {v: k for k, v in PLATFORM_TO_DIST_CHANNEL_TYPE.items()}

OAUTH_PROVIDERS = ("linkedin", "instagram", "facebook")


def _prefix(store: str, native_id: str) -> str:
    return f"{store}:{native_id}"


def _unprefix(prefixed_id: str) -> Tuple[str, str]:
    if ":" not in prefixed_id:
        raise HTTPException(400, f"Invalid connection id: {prefixed_id!r}")
    store, native = prefixed_id.split(":", 1)
    return store, native


def _capability_defaults(platform: str) -> Dict[str, bool]:
    """Return (inbound_enabled, outbound_enabled) defaults for a platform.

    Outbound-only platforms default inbound off. Everything else defaults
    both on — these are the flags applied when a record has never been
    touched by a capability PATCH.
    """
    caps = PLATFORM_CAPABILITIES.get(platform, {})
    return {
        "inbound_enabled": caps.get("inbound_supported", False),
        "outbound_enabled": caps.get("outbound_supported", False),
    }


def _mask(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]


class ConnectionService:
    def __init__(self, db):
        self.db = db
        self.distribution = DistributionService(db)

    # ------------------------------------------------------------------
    # LIST
    # ------------------------------------------------------------------

    async def list_connections(self) -> List[ConnectionSummary]:
        out: List[ConnectionSummary] = []
        out.extend(await self._list_oauth())
        out.extend(await self._list_reddit())
        out.extend(await self._list_twitter())
        out.extend(await self._list_channel_registrations())
        out.extend(await self._list_outbound())
        return out

    async def _list_oauth(self) -> List[ConnectionSummary]:
        rows: List[ConnectionSummary] = []
        coll = self.db["oauth_connections"]
        async for doc in coll.find({}):
            provider = doc.get("_id") if isinstance(doc.get("_id"), str) else None
            if provider not in OAUTH_PROVIDERS:
                continue
            connected = bool(doc.get("access_token"))
            caps = _capability_defaults(provider)
            rows.append(ConnectionSummary(
                id=_prefix("oauth", provider),
                platform=provider,
                store="oauth_connections",
                display_name=doc.get("profile_name") or provider.title(),
                connected=connected,
                inbound_enabled=bool(doc.get("inbound_enabled", caps["inbound_enabled"])),
                outbound_enabled=bool(doc.get("outbound_enabled", caps["outbound_enabled"])),
                inbound_supported=PLATFORM_CAPABILITIES[provider]["inbound_supported"],
                outbound_supported=PLATFORM_CAPABILITIES[provider]["outbound_supported"],
                config_summary={
                    "profile_id": doc.get("profile_id"),
                    "scopes": doc.get("scopes", []),
                    "org_id": doc.get("org_id"),
                    "expires_in": doc.get("expires_in"),
                },
                created_at=doc.get("connected_at") or doc.get("updated_at"),
                updated_at=doc.get("updated_at"),
            ))
        return rows

    async def _list_reddit(self) -> List[ConnectionSummary]:
        rows: List[ConnectionSummary] = []
        coll = self.db["reddit_accounts"]
        async for doc in coll.find({}):
            native_id = str(doc.get("_id"))
            caps = _capability_defaults("reddit")
            rows.append(ConnectionSummary(
                id=_prefix("reddit", native_id),
                platform="reddit",
                store="reddit_accounts",
                display_name=doc.get("username"),
                connected=bool(doc.get("client_id") and doc.get("client_secret")),
                inbound_enabled=bool(doc.get("inbound_enabled", caps["inbound_enabled"])),
                outbound_enabled=bool(doc.get("outbound_enabled", caps["outbound_enabled"])),
                inbound_supported=True,
                outbound_supported=True,
                config_summary={
                    "subreddits": doc.get("subreddits", []),
                    "keyword_count": len(doc.get("keywords", []) or []),
                    "poll_inbox": doc.get("poll_inbox", True),
                },
                created_at=_iso(doc.get("created_at")),
                updated_at=_iso(doc.get("updated_at")),
            ))
        return rows

    async def _list_twitter(self) -> List[ConnectionSummary]:
        rows: List[ConnectionSummary] = []
        coll = self.db["twitter_accounts"]
        async for doc in coll.find({}):
            native_id = str(doc.get("_id"))
            caps = _capability_defaults("twitter")
            has_write = bool(
                doc.get("api_key") and doc.get("api_secret")
                and doc.get("access_token") and doc.get("access_token_secret")
            )
            rows.append(ConnectionSummary(
                id=_prefix("twitter", native_id),
                platform="twitter",
                store="twitter_accounts",
                display_name=doc.get("user_id"),
                connected=bool(doc.get("user_id") and (doc.get("bearer_token") or has_write)),
                inbound_enabled=bool(doc.get("inbound_enabled", caps["inbound_enabled"])),
                # If no OAuth 1.0a creds, outbound is physically impossible — force off.
                outbound_enabled=bool(doc.get("outbound_enabled", caps["outbound_enabled"])) and has_write,
                inbound_supported=True,
                outbound_supported=has_write,
                config_summary={
                    "poll_mentions": doc.get("poll_mentions", True),
                    "poll_dms": doc.get("poll_dms", True),
                    "has_write_creds": has_write,
                    "keyword_count": len(doc.get("keywords", []) or []),
                },
                created_at=_iso(doc.get("created_at")),
                updated_at=_iso(doc.get("updated_at")),
            ))
        return rows

    async def _list_channel_registrations(self) -> List[ConnectionSummary]:
        rows: List[ConnectionSummary] = []
        coll = self.db["channel_registrations"]
        async for doc in coll.find({"channel_type": {"$in": ["telegram", "discord"]}}):
            platform = doc["channel_type"]
            native_id = str(doc.get("_id"))
            caps = _capability_defaults(platform)
            rows.append(ConnectionSummary(
                id=_prefix("channel", native_id),
                platform=platform,
                store="channel_registrations",
                display_name=(doc.get("config") or {}).get("bot_name") or platform.title(),
                connected=bool((doc.get("config") or {}).get("bot_token")),
                inbound_enabled=bool(doc.get("inbound_enabled", caps["inbound_enabled"])),
                outbound_enabled=bool(doc.get("outbound_enabled", caps["outbound_enabled"])),
                inbound_supported=True,
                outbound_supported=True,
                config_summary={
                    "has_token": bool((doc.get("config") or {}).get("bot_token")),
                },
                created_at=_iso(doc.get("created_at")),
                updated_at=_iso(doc.get("updated_at")),
            ))
        return rows

    async def _list_outbound(self) -> List[ConnectionSummary]:
        """Blog/email/slack from distribution_channels. Skip rows that duplicate OAuth providers."""
        rows: List[ConnectionSummary] = []
        coll = self.db["distribution_channels"]
        async for doc in coll.find({"channel_type": {"$in": list(DIST_CHANNEL_TYPE_TO_PLATFORM.keys())}}):
            underlying = doc.get("channel_type")
            platform = DIST_CHANNEL_TYPE_TO_PLATFORM.get(underlying)
            if not platform:
                continue
            channel_id = doc.get("channel_id") or str(doc.get("_id"))
            caps = _capability_defaults(platform)
            cfg = doc.get("config") or {}
            rows.append(ConnectionSummary(
                id=_prefix("outbound", channel_id),
                platform=platform,
                store="distribution_channels",
                display_name=doc.get("name"),
                connected=bool(doc.get("enabled", True)),
                inbound_enabled=bool(doc.get("inbound_enabled", caps["inbound_enabled"])),
                outbound_enabled=bool(doc.get("outbound_enabled", caps["outbound_enabled"])),
                inbound_supported=False,
                outbound_supported=True,
                config_summary=self._outbound_summary(platform, cfg),
                created_at=doc.get("created_at"),
                updated_at=doc.get("updated_at"),
            ))
        return rows

    @staticmethod
    def _outbound_summary(platform: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
        if platform == "blog":
            return {"cms_type": cfg.get("cms_type"), "api_url": cfg.get("api_url")}
        if platform == "email":
            return {"provider": cfg.get("provider"), "from_email": cfg.get("from_email")}
        if platform == "slack_webhook":
            return {"webhook_host": _webhook_host(cfg.get("webhook_url"))}
        return {}

    # ------------------------------------------------------------------
    # GET single
    # ------------------------------------------------------------------

    async def get_connection(self, connection_id: str) -> Optional[ConnectionSummary]:
        store, native = _unprefix(connection_id)
        all_rows = await self.list_connections()
        for row in all_rows:
            if row.id == connection_id:
                return row
        return None

    # ------------------------------------------------------------------
    # PATCH capabilities
    # ------------------------------------------------------------------

    async def update_capabilities(
        self,
        connection_id: str,
        update: CapabilityUpdate,
    ) -> ConnectionSummary:
        store, native = _unprefix(connection_id)
        existing = await self.get_connection(connection_id)
        if not existing:
            raise HTTPException(404, f"Connection {connection_id} not found")

        # Reject toggling a capability the platform doesn't support
        if update.inbound_enabled is True and not existing.inbound_supported:
            raise HTTPException(
                422,
                f"Platform {existing.platform} does not support inbound",
            )
        if update.outbound_enabled is True and not existing.outbound_supported:
            raise HTTPException(
                422,
                f"Platform {existing.platform} does not support outbound",
            )

        set_fields: Dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}
        if update.inbound_enabled is not None:
            set_fields["inbound_enabled"] = update.inbound_enabled
        if update.outbound_enabled is not None:
            set_fields["outbound_enabled"] = update.outbound_enabled

        if store == "oauth":
            await self.db["oauth_connections"].update_one(
                {"_id": native}, {"$set": set_fields}
            )
        elif store == "reddit":
            await self.db["reddit_accounts"].update_one(
                _by_id(native), {"$set": set_fields}
            )
        elif store == "twitter":
            await self.db["twitter_accounts"].update_one(
                _by_id(native), {"$set": set_fields}
            )
        elif store == "channel":
            await self.db["channel_registrations"].update_one(
                _by_id(native), {"$set": set_fields}
            )
        elif store == "outbound":
            await self.db["distribution_channels"].update_one(
                {"channel_id": native}, {"$set": set_fields}
            )
        else:
            raise HTTPException(400, f"Unknown connection store: {store}")

        refreshed = await self.get_connection(connection_id)
        if not refreshed:
            raise HTTPException(500, "Failed to re-read connection after update")
        return refreshed

    # ------------------------------------------------------------------
    # Outbound CRUD (blog / email / slack_webhook)
    # ------------------------------------------------------------------

    async def create_outbound(
        self,
        req: OutboundConnectionCreate,
        user_id: str,
    ) -> ConnectionSummary:
        if req.platform not in OUTBOUND_ONLY_PLATFORMS:
            raise HTTPException(400, f"Platform {req.platform} is not outbound-only")

        underlying = PLATFORM_TO_DIST_CHANNEL_TYPE[req.platform]
        doc = await self.distribution.create_channel(
            channel_type=underlying,
            name=req.name,
            config=req.config,
            organization="solo",
            created_by=user_id,
        )
        # Write capability defaults so reads are stable
        await self.db["distribution_channels"].update_one(
            {"channel_id": doc["channel_id"]},
            {"$set": {
                "inbound_enabled": False,
                "outbound_enabled": True,
                "enabled": req.enabled,
            }},
        )
        summary = await self.get_connection(_prefix("outbound", doc["channel_id"]))
        if not summary:
            raise HTTPException(500, "Created outbound connection could not be read back")
        return summary

    async def update_outbound(
        self,
        connection_id: str,
        update: OutboundConnectionUpdate,
    ) -> ConnectionSummary:
        store, native = _unprefix(connection_id)
        if store != "outbound":
            raise HTTPException(400, "Only outbound-only connections support this update")
        set_fields: Dict[str, Any] = {}
        if update.name is not None:
            set_fields["name"] = update.name
        if update.config is not None:
            set_fields["config"] = update.config
        if update.enabled is not None:
            set_fields["enabled"] = update.enabled
        set_fields["updated_at"] = datetime.utcnow().isoformat()
        result = await self.db["distribution_channels"].update_one(
            {"channel_id": native}, {"$set": set_fields}
        )
        if result.matched_count == 0:
            raise HTTPException(404, f"Outbound connection {connection_id} not found")
        summary = await self.get_connection(connection_id)
        if not summary:
            raise HTTPException(404, f"Outbound connection {connection_id} not found")
        return summary

    async def delete_outbound(self, connection_id: str) -> None:
        store, native = _unprefix(connection_id)
        if store != "outbound":
            raise HTTPException(400, "Only outbound-only connections support delete via this endpoint")
        deleted = await self.distribution.delete_channel(native)
        if not deleted:
            raise HTTPException(404, f"Outbound connection {connection_id} not found")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _by_id(native_id: str) -> Dict[str, Any]:
    """SQLite adapter stores _id as str; return a single-key filter."""
    return {"_id": native_id}


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _webhook_host(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    # Only expose the host — redact the token segment for privacy.
    try:
        from urllib.parse import urlparse
        return urlparse(url).hostname
    except Exception:
        return None
