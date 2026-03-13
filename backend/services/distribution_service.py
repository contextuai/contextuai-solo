"""
Distribution Channel Registry — Publish content to external platforms.

Supports:
- LinkedIn (API v2)
- Twitter/X (API v2)
- Blog CMS (Ghost, WordPress, custom API)
- Email (SendGrid, SES, SMTP)
- Slack (incoming webhook)

Each channel is registered per-organization with credentials, format
requirements, and enabled/disabled flags. Content is published via a
unified interface with delivery receipts logged for tracking.
"""

import base64
import time
import urllib.parse
import uuid
import hmac
import hashlib
import httpx
import logging
import secrets
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class DistributionChannelType(str, Enum):
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    BLOG = "blog"
    EMAIL = "email"
    SLACK = "slack"


class PublishStatus(str, Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
    SCHEDULED = "scheduled"


# Format constraints per channel
CHANNEL_CONSTRAINTS = {
    DistributionChannelType.LINKEDIN: {
        "max_length": 3000,
        "supports_html": False,
        "supports_images": True,
        "supports_links": True,
    },
    DistributionChannelType.TWITTER: {
        "max_length": 280,
        "supports_html": False,
        "supports_images": True,
        "supports_links": True,
    },
    DistributionChannelType.BLOG: {
        "max_length": 100000,
        "supports_html": True,
        "supports_images": True,
        "supports_links": True,
    },
    DistributionChannelType.EMAIL: {
        "max_length": 100000,
        "supports_html": True,
        "supports_images": True,
        "supports_links": True,
    },
    DistributionChannelType.SLACK: {
        "max_length": 40000,
        "supports_html": False,
        "supports_images": False,
        "supports_links": True,
    },
}


class DistributionService:
    """Manage distribution channels and publish content."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.channels = db["distribution_channels"]
        self.deliveries = db["distribution_deliveries"]

    # ------------------------------------------------------------------
    # Channel CRUD
    # ------------------------------------------------------------------

    async def create_channel(
        self,
        channel_type: str,
        name: str,
        config: Dict[str, Any],
        organization: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a new distribution channel."""
        now = datetime.utcnow().isoformat()
        doc = {
            "channel_id": str(uuid.uuid4()),
            "channel_type": channel_type,
            "name": name,
            "config": config,
            "organization": organization,
            "enabled": True,
            "publish_count": 0,
            "last_published_at": None,
            "created_at": now,
            "updated_at": now,
            "created_by": created_by,
        }
        await self.channels.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def list_channels(
        self,
        organization: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List distribution channels."""
        query: Dict[str, Any] = {}
        if organization:
            query["organization"] = organization
        if channel_type:
            query["channel_type"] = channel_type

        cursor = self.channels.find(query).sort("name", 1)
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            # Mask credentials in config
            if "config" in doc:
                doc["config"] = self._mask_credentials(doc["config"])
            docs.append(doc)
        return docs

    async def get_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific channel by ID."""
        doc = await self.channels.find_one({"channel_id": channel_id})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def update_channel(
        self,
        channel_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update a distribution channel."""
        updates["updated_at"] = datetime.utcnow().isoformat()
        result = await self.channels.update_one(
            {"channel_id": channel_id},
            {"$set": updates},
        )
        if result.modified_count == 0:
            return None
        return await self.get_channel(channel_id)

    async def delete_channel(self, channel_id: str) -> bool:
        """Delete a distribution channel."""
        result = await self.channels.delete_one({"channel_id": channel_id})
        return result.deleted_count > 0

    async def toggle_channel(self, channel_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        """Enable or disable a channel."""
        return await self.update_channel(channel_id, {"enabled": enabled})

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(
        self,
        channel_id: str,
        content: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        published_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Publish content to a distribution channel."""
        channel = await self.get_channel(channel_id)
        if not channel:
            return {"status": "error", "message": "Channel not found"}

        if not channel.get("enabled"):
            return {"status": "error", "message": "Channel is disabled"}

        channel_type = channel["channel_type"]
        config = channel.get("config", {})

        # Validate content length
        constraints = CHANNEL_CONSTRAINTS.get(
            DistributionChannelType(channel_type), {}
        )
        max_len = constraints.get("max_length", 100000)
        if len(content) > max_len:
            return {
                "status": "error",
                "message": f"Content exceeds {channel_type} limit of {max_len} chars",
            }

        # Dispatch to channel-specific publisher
        delivery_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        try:
            result = await self._dispatch_publish(
                channel_type, config, content, title, metadata
            )
            status = PublishStatus.PUBLISHED if result.get("success") else PublishStatus.FAILED
        except Exception as e:
            logger.error(f"Publish failed for {channel_type}: {e}")
            result = {"success": False, "error": str(e)}
            status = PublishStatus.FAILED

        # Log delivery
        delivery = {
            "delivery_id": delivery_id,
            "channel_id": channel_id,
            "channel_type": channel_type,
            "channel_name": channel.get("name"),
            "title": title,
            "content_length": len(content),
            "status": status.value,
            "result": result,
            "metadata": metadata,
            "published_by": published_by,
            "timestamp": now,
        }
        await self.deliveries.insert_one(delivery)
        delivery.pop("_id", None)

        # Update channel stats
        update = {"$inc": {"publish_count": 1}, "$set": {"updated_at": now}}
        if status == PublishStatus.PUBLISHED:
            update["$set"]["last_published_at"] = now
        await self.channels.update_one({"channel_id": channel_id}, update)

        return delivery

    async def publish_to_multiple(
        self,
        channel_ids: List[str],
        content: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        published_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Publish content to multiple channels."""
        results = []
        for cid in channel_ids:
            result = await self.publish(cid, content, title, metadata, published_by)
            results.append(result)

        published = sum(1 for r in results if r.get("status") == "published")
        return {
            "total_channels": len(channel_ids),
            "published": published,
            "failed": len(channel_ids) - published,
            "deliveries": results,
        }

    async def get_deliveries(
        self,
        channel_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get delivery history."""
        query: Dict[str, Any] = {}
        if channel_id:
            query["channel_id"] = channel_id
        cursor = self.deliveries.find(query).sort("timestamp", -1).limit(limit)
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)
        return docs

    async def get_channel_types(self) -> List[Dict[str, Any]]:
        """List available channel types with their constraints."""
        types = []
        for ct in DistributionChannelType:
            constraints = CHANNEL_CONSTRAINTS.get(ct, {})
            types.append({
                "type": ct.value,
                "constraints": constraints,
                "required_config": self._required_config(ct),
            })
        return types

    # ------------------------------------------------------------------
    # Channel-Specific Publishers
    # ------------------------------------------------------------------

    async def _dispatch_publish(
        self,
        channel_type: str,
        config: Dict[str, Any],
        content: str,
        title: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Route publish to the correct channel handler."""
        ct = DistributionChannelType(channel_type)

        if ct == DistributionChannelType.LINKEDIN:
            return await self._publish_linkedin(config, content, title)
        elif ct == DistributionChannelType.TWITTER:
            return await self._publish_twitter(config, content)
        elif ct == DistributionChannelType.BLOG:
            return await self._publish_blog(config, content, title, metadata)
        elif ct == DistributionChannelType.EMAIL:
            return await self._publish_email(config, content, title, metadata)
        elif ct == DistributionChannelType.SLACK:
            return await self._publish_slack(config, content, title)
        elif ct == DistributionChannelType.INSTAGRAM:
            return await self._publish_instagram(config, content, metadata)
        elif ct == DistributionChannelType.FACEBOOK:
            return await self._publish_facebook(config, content)
        else:
            return {"success": False, "error": f"Unsupported channel: {channel_type}"}

    async def _publish_linkedin(
        self, config: Dict[str, Any], content: str, title: Optional[str]
    ) -> Dict[str, Any]:
        """Publish to LinkedIn via API v2."""
        access_token = config.get("access_token")
        author_urn = config.get("author_urn")  # e.g., urn:li:person:xxx or urn:li:organization:xxx

        if not access_token or not author_urn:
            return {"success": False, "error": "Missing access_token or author_urn"}

        url = "https://api.linkedin.com/v2/ugcPosts"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                    "shareMediaCategory": "NONE",
                },
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code in (200, 201):
                return {"success": True, "post_id": r.headers.get("x-restli-id"), "status_code": r.status_code}
            return {"success": False, "error": r.text, "status_code": r.status_code}

    async def _publish_twitter(
        self, config: Dict[str, Any], content: str
    ) -> Dict[str, Any]:
        """
        Publish to Twitter/X via API v2.
        Supports two auth methods:
          1. OAuth 1.0a User Context (api_key + api_secret + access_token + access_token_secret)
          2. Bearer token (app-level, read-only for most endpoints)
        """
        api_key = config.get("api_key")
        api_secret = config.get("api_secret")
        access_token = config.get("access_token")
        access_token_secret = config.get("access_token_secret")
        bearer_token = config.get("bearer_token")

        url = "https://api.twitter.com/2/tweets"

        # Prefer OAuth 1.0a user context (can post on behalf of user)
        if api_key and api_secret and access_token and access_token_secret:
            try:
                # Build OAuth 1.0a signature
                nonce = secrets.token_hex(16)
                timestamp = str(int(time.time()))
                oauth_params = {
                    "oauth_consumer_key": api_key,
                    "oauth_nonce": nonce,
                    "oauth_signature_method": "HMAC-SHA1",
                    "oauth_timestamp": timestamp,
                    "oauth_token": access_token,
                    "oauth_version": "1.0",
                }
                # Create signature base string
                param_str = "&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in sorted(oauth_params.items()))
                base_string = f"POST&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_str, safe='')}"
                signing_key = f"{urllib.parse.quote(api_secret, safe='')}&{urllib.parse.quote(access_token_secret, safe='')}"
                signature = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
                oauth_signature = base64.b64encode(signature).decode()
                oauth_params["oauth_signature"] = oauth_signature

                auth_header = "OAuth " + ", ".join(
                    f'{k}="{urllib.parse.quote(v, safe="")}"' for k, v in sorted(oauth_params.items())
                )
                headers = {"Authorization": auth_header, "Content-Type": "application/json"}

                async with httpx.AsyncClient() as client:
                    r = await client.post(url, json={"text": content[:280]}, headers=headers)
                    if r.status_code in (200, 201):
                        data = r.json()
                        return {"success": True, "tweet_id": data.get("data", {}).get("id"), "status_code": r.status_code}
                    return {"success": False, "error": r.text, "status_code": r.status_code}
            except Exception as e:
                logger.exception("Twitter OAuth 1.0a publish failed")
                return {"success": False, "error": str(e)}

        elif bearer_token:
            headers = {"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
            async with httpx.AsyncClient() as client:
                r = await client.post(url, json={"text": content[:280]}, headers=headers)
                if r.status_code in (200, 201):
                    data = r.json()
                    return {"success": True, "tweet_id": data.get("data", {}).get("id"), "status_code": r.status_code}
            return {"success": False, "error": r.text, "status_code": r.status_code}

        else:
            return {"success": False, "error": "Missing Twitter credentials (need api_key+api_secret+access_token+access_token_secret or bearer_token)"}

    async def _publish_instagram(
        self, config: Dict[str, Any], content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Publish to Instagram via Graph API.
        Requires a Facebook Page linked to an Instagram Business account.
        Two-step: create media container, then publish it.
        """
        access_token = config.get("access_token")
        ig_user_id = config.get("instagram_user_id")

        if not access_token or not ig_user_id:
            return {"success": False, "error": "Missing access_token or instagram_user_id"}

        image_url = (metadata or {}).get("image_url")
        base_url = f"https://graph.facebook.com/v21.0/{ig_user_id}"

        async with httpx.AsyncClient() as client:
            if image_url:
                # Photo post: create media container then publish
                r1 = await client.post(f"{base_url}/media", params={
                    "image_url": image_url,
                    "caption": content[:2200],
                    "access_token": access_token,
                })
                if r1.status_code != 200:
                    return {"success": False, "error": r1.text, "status_code": r1.status_code}
                container_id = r1.json().get("id")

                r2 = await client.post(f"{base_url}/media_publish", params={
                    "creation_id": container_id,
                    "access_token": access_token,
                })
                if r2.status_code != 200:
                    return {"success": False, "error": r2.text, "status_code": r2.status_code}
                return {"success": True, "post_id": r2.json().get("id"), "status_code": r2.status_code}
            else:
                # Text-only: not supported by Instagram API (requires image/video)
                return {"success": False, "error": "Instagram requires an image_url or video_url for posts"}

    async def _publish_facebook(
        self, config: Dict[str, Any], content: str
    ) -> Dict[str, Any]:
        """Publish to a Facebook Page via Graph API."""
        access_token = config.get("page_access_token") or config.get("access_token")
        page_id = config.get("page_id")

        if not access_token or not page_id:
            return {"success": False, "error": "Missing page_access_token or page_id"}

        url = f"https://graph.facebook.com/v21.0/{page_id}/feed"

        async with httpx.AsyncClient() as client:
            r = await client.post(url, params={
                "message": content,
                "access_token": access_token,
            })
            if r.status_code == 200:
                return {"success": True, "post_id": r.json().get("id"), "status_code": r.status_code}
            return {"success": False, "error": r.text, "status_code": r.status_code}

    async def _publish_blog(
        self, config: Dict[str, Any], content: str,
        title: Optional[str], metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Publish to a blog CMS (Ghost, WordPress, or custom API)."""
        cms_type = config.get("cms_type", "custom")
        api_url = config.get("api_url")
        api_key = config.get("api_key")

        if not api_url:
            return {"success": False, "error": "Missing api_url"}

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if cms_type == "ghost":
            payload = {
                "posts": [{
                    "title": title or "Untitled",
                    "html": content,
                    "status": metadata.get("status", "draft") if metadata else "draft",
                }],
            }
        elif cms_type == "wordpress":
            payload = {
                "title": title or "Untitled",
                "content": content,
                "status": metadata.get("status", "draft") if metadata else "draft",
            }
        else:
            payload = {
                "title": title or "Untitled",
                "content": content,
                "metadata": metadata or {},
            }

        async with httpx.AsyncClient() as client:
            r = await client.post(api_url, json=payload, headers=headers)
            if r.status_code in (200, 201):
                return {"success": True, "status_code": r.status_code}
            return {"success": False, "error": r.text, "status_code": r.status_code}

    async def _publish_email(
        self, config: Dict[str, Any], content: str,
        title: Optional[str], metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Send email via SendGrid or SES."""
        provider = config.get("provider", "sendgrid")
        api_key = config.get("api_key")
        from_email = config.get("from_email")
        to_emails = metadata.get("to_emails", []) if metadata else []

        if not api_key or not from_email:
            return {"success": False, "error": "Missing api_key or from_email"}
        if not to_emails:
            return {"success": False, "error": "No recipients specified in metadata.to_emails"}

        if provider == "sendgrid":
            url = "https://api.sendgrid.com/v3/mail/send"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "personalizations": [{"to": [{"email": e} for e in to_emails]}],
                "from": {"email": from_email},
                "subject": title or "No Subject",
                "content": [{"type": "text/html", "value": content}],
            }

            async with httpx.AsyncClient() as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code in (200, 202):
                    return {"success": True, "status_code": r.status_code}
                return {"success": False, "error": r.text, "status_code": r.status_code}

        return {"success": False, "error": f"Unsupported email provider: {provider}"}

    async def _publish_slack(
        self, config: Dict[str, Any], content: str, title: Optional[str]
    ) -> Dict[str, Any]:
        """Publish to Slack via incoming webhook."""
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            return {"success": False, "error": "Missing webhook_url"}

        text = f"*{title}*\n\n{content}" if title else content

        async with httpx.AsyncClient() as client:
            r = await client.post(webhook_url, json={"text": text})
            if r.status_code == 200:
                return {"success": True, "status_code": 200}
            return {"success": False, "error": r.text, "status_code": r.status_code}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mask_credentials(config: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive fields in config for list responses."""
        masked = dict(config)
        sensitive_keys = {"access_token", "bearer_token", "api_key", "webhook_url", "password", "secret"}
        for key in sensitive_keys:
            if key in masked and masked[key]:
                val = str(masked[key])
                masked[key] = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
        return masked

    @staticmethod
    def _required_config(channel_type: DistributionChannelType) -> List[str]:
        """Return required config fields per channel type."""
        requirements = {
            DistributionChannelType.LINKEDIN: ["access_token", "author_urn"],
            DistributionChannelType.TWITTER: ["bearer_token"],
            DistributionChannelType.BLOG: ["api_url"],
            DistributionChannelType.EMAIL: ["api_key", "from_email", "provider"],
            DistributionChannelType.SLACK: ["webhook_url"],
        }
        return requirements.get(channel_type, [])
