"""
Event Service — Publish/subscribe event system for proactive notifications.

Handles:
- Subscription CRUD (create, list, update, delete)
- Event emission and fan-out to matching subscriptions
- Delivery via webhook, Slack, and email channels
- Delivery logging and failure tracking
"""

import hmac
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx

from repositories.event_repository import (
    EventSubscriptionRepository,
    EventDeliveryRepository,
)

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTIONS_PER_USER = 50


class EventService:
    """Service for event subscriptions and delivery."""

    def __init__(
        self,
        sub_repo: EventSubscriptionRepository,
        delivery_repo: EventDeliveryRepository,
    ):
        self.sub_repo = sub_repo
        self.delivery_repo = delivery_repo

    # ------------------------------------------------------------------
    # Subscription CRUD
    # ------------------------------------------------------------------

    async def create_subscription(
        self, user_id: str, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new event subscription."""
        # Check capacity
        existing, total = await self.sub_repo.get_user_subscriptions(user_id, page_size=0)
        count = await self.sub_repo.collection.count_documents({
            "user_id": user_id,
            "deleted_at": None,
        })
        if count >= MAX_SUBSCRIPTIONS_PER_USER:
            raise ValueError(f"Maximum {MAX_SUBSCRIPTIONS_PER_USER} subscriptions per user")

        data["user_id"] = user_id
        return await self.sub_repo.create_subscription(data)

    async def get_subscription(
        self, subscription_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a subscription (with ownership check)."""
        sub = await self.sub_repo.get_by_subscription_id(subscription_id)
        if sub and sub["user_id"] != user_id:
            return None
        return sub

    async def list_subscriptions(
        self,
        user_id: str,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ):
        """List user subscriptions."""
        return await self.sub_repo.get_user_subscriptions(
            user_id, status=status, page=page, page_size=page_size
        )

    async def update_subscription(
        self, subscription_id: str, user_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a subscription (with ownership check)."""
        sub = await self.sub_repo.get_by_subscription_id(subscription_id)
        if not sub or sub["user_id"] != user_id:
            return None
        return await self.sub_repo.update_subscription(subscription_id, data)

    async def delete_subscription(
        self, subscription_id: str, user_id: str
    ) -> bool:
        """Delete a subscription (with ownership check)."""
        sub = await self.sub_repo.get_by_subscription_id(subscription_id)
        if not sub or sub["user_id"] != user_id:
            return False
        return await self.sub_repo.soft_delete(subscription_id)

    async def get_delivery_logs(
        self, subscription_id: str, user_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get delivery logs (with ownership check)."""
        sub = await self.sub_repo.get_by_subscription_id(subscription_id)
        if not sub or sub["user_id"] != user_id:
            return []
        return await self.delivery_repo.get_delivery_logs(subscription_id, limit)

    # ------------------------------------------------------------------
    # Event Emission (called by other services)
    # ------------------------------------------------------------------

    async def emit(
        self,
        event_type: str,
        payload: Dict[str, Any],
        source_user_id: Optional[str] = None,
    ) -> int:
        """
        Emit an event and deliver to all matching subscriptions.
        Returns the number of deliveries attempted.

        This is fire-and-forget — errors are logged but don't propagate.
        """
        try:
            subscriptions = await self.sub_repo.get_active_subscriptions_for_event(
                event_type
            )

            # Filter by subscription-level filters
            matched = []
            for sub in subscriptions:
                if self._matches_filters(sub.get("filters"), payload):
                    matched.append(sub)

            if not matched:
                return 0

            # Build event envelope
            event = {
                "event_type": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "source_user_id": source_user_id,
                "data": payload,
            }

            delivered = 0
            for sub in matched:
                try:
                    await self._deliver(sub, event)
                    delivered += 1
                except Exception as e:
                    logger.error(
                        f"Failed to deliver event {event_type} to "
                        f"subscription {sub['subscription_id']}: {e}"
                    )

            return delivered

        except Exception as e:
            logger.error(f"Error emitting event {event_type}: {e}")
            return 0

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    async def _deliver(self, subscription: Dict[str, Any], event: Dict[str, Any]):
        """Deliver an event to a subscription's configured channel."""
        channel = subscription.get("channel", "webhook")
        config = subscription.get("channel_config", {})
        sub_id = subscription["subscription_id"]

        try:
            if channel == "webhook":
                await self._deliver_webhook(config, event)
            elif channel == "slack":
                await self._deliver_slack(config, event)
            elif channel == "email":
                await self._deliver_email(config, event)
            else:
                raise ValueError(f"Unknown channel: {channel}")

            # Log success
            await self.sub_repo.record_delivery(sub_id, success=True)
            await self.delivery_repo.log_delivery({
                "subscription_id": sub_id,
                "event_type": event["event_type"],
                "channel": channel,
                "status": "delivered",
                "payload_summary": event["event_type"],
                "delivered_at": datetime.utcnow().isoformat(),
            })

        except Exception as e:
            # Log failure
            await self.sub_repo.record_delivery(sub_id, success=False)
            await self.delivery_repo.log_delivery({
                "subscription_id": sub_id,
                "event_type": event["event_type"],
                "channel": channel,
                "status": "failed",
                "error": str(e)[:500],
                "delivered_at": datetime.utcnow().isoformat(),
            })
            raise

    async def _deliver_webhook(self, config: Dict[str, Any], event: Dict[str, Any]):
        """Deliver event via HTTP webhook."""
        url = config.get("url")
        if not url:
            raise ValueError("Webhook URL not configured")

        body = json.dumps(event, default=str)
        headers = {"Content-Type": "application/json"}

        # Add custom headers
        if config.get("headers"):
            headers.update(config["headers"])

        # Add HMAC signature if secret is configured
        secret = config.get("secret")
        if secret:
            signature = hmac.new(
                secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, content=body, headers=headers)
            if resp.status_code >= 400:
                raise ValueError(f"Webhook returned {resp.status_code}: {resp.text[:200]}")

    async def _deliver_slack(self, config: Dict[str, Any], event: Dict[str, Any]):
        """Deliver event via Slack webhook."""
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            raise ValueError("Slack webhook URL not configured")

        # Format as Slack message
        event_type = event["event_type"]
        data = event.get("data", {})
        text = f"*Event: {event_type}*\n"

        # Add relevant data fields
        for key in ["name", "status", "automation_id", "crew_id", "message"]:
            if key in data:
                text += f"  {key}: {data[key]}\n"

        payload = {"text": text}
        if config.get("channel"):
            payload["channel"] = config["channel"]

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code >= 400:
                raise ValueError(f"Slack webhook returned {resp.status_code}")

    async def _deliver_email(self, config: Dict[str, Any], event: Dict[str, Any]):
        """Deliver event via email (placeholder — would integrate with SES/SMTP)."""
        recipients = config.get("to", [])
        if not recipients:
            raise ValueError("No email recipients configured")

        # In production, this would send via SES or SMTP
        logger.info(
            f"[Email placeholder] Would send {event['event_type']} to {recipients}"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_filters(
        filters: Optional[Dict[str, Any]], payload: Dict[str, Any]
    ) -> bool:
        """Check if event payload matches subscription filters."""
        if not filters:
            return True
        for key, value in filters.items():
            if payload.get(key) != value:
                return False
        return True


# ---------------------------------------------------------------------------
# Convenience function for fire-and-forget event emission
# ---------------------------------------------------------------------------

async def emit_event(
    event_type: str,
    payload: Dict[str, Any],
    source_user_id: Optional[str] = None,
) -> None:
    """
    Fire-and-forget event emission.
    Call this from any service to emit an event without blocking.
    """
    try:
        from database import get_database
        db = await get_database()
        svc = EventService(
            EventSubscriptionRepository(db),
            EventDeliveryRepository(db),
        )
        await svc.emit(event_type, payload, source_user_id)
    except Exception as e:
        logger.error(f"Failed to emit event {event_type}: {e}")
