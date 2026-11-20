"""
Approval Service — Human-in-the-loop review for auto-generated replies.

When a trigger has ``approval_required=True``, the AI-generated response
is stored as a pending approval instead of being sent immediately.
Users review, edit, and approve/reject from the Approvals page.
On approval, the response is sent back through the channel.
"""

import logging
from typing import Dict, Any, Optional, List

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.approval_repository import ApprovalRepository

logger = logging.getLogger(__name__)

RETIRED_SOCIAL_CHANNELS = frozenset(
    {"linkedin", "twitter", "instagram", "facebook", "reddit"}
)


def _is_retired_social_approval(doc: Dict[str, Any]) -> bool:
    return str(doc.get("channel_type") or "").strip().lower() in RETIRED_SOCIAL_CHANNELS


class ApprovalService:
    """Business logic for the approval queue."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.repo = ApprovalRepository(db)

    async def create_approval(
        self,
        trigger_id: str,
        channel_type: str,
        channel_id: str,
        sender_name: str,
        sender_id: str,
        inbound_text: str,
        draft_response: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """Create a new pending approval."""
        return await self.repo.create({
            "trigger_id": trigger_id,
            "channel_type": channel_type,
            "channel_id": channel_id,
            "sender_name": sender_name,
            "sender_id": sender_id,
            "inbound_text": inbound_text,
            "draft_response": draft_response,
            "session_id": session_id,
        })

    async def list_pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = await self.repo.list_pending(limit=max(limit * 2, 100))
        return [d for d in rows if not _is_retired_social_approval(d)][:limit]

    async def list_all(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        rows = await self.repo.list_all(status=status, limit=max(limit * 2, 100))
        return [d for d in rows if not _is_retired_social_approval(d)][:limit]

    async def get(self, approval_id: str) -> Optional[Dict[str, Any]]:
        return await self.repo.get_by_id(approval_id)

    async def approve_and_send(
        self,
        approval_id: str,
        edited_response: Optional[str] = None,
        reviewed_by: str = "desktop-user",
    ) -> Dict[str, Any]:
        """Approve (optionally edit) and send the response via the channel.

        Sends FIRST and only marks the approval ``approved`` if the send
        actually succeeds — so a failed post (e.g. an expired channel token)
        leaves the item ``pending`` to retry, instead of falsely showing as
        approved-but-not-posted.
        """
        existing = await self.repo.get_by_id(approval_id)
        if not existing:
            raise ValueError(f"Approval '{approval_id}' not found")

        response_text = (
            edited_response
            or existing.get("final_response")
            or existing.get("draft_response", "")
            or existing.get("content", "")
        )
        channel_type = existing["channel_type"]
        channel_id = existing["channel_id"]

        # Send first — raises on failure, leaving the approval pending to retry.
        try:
            await self._send_via_channel(channel_type, channel_id, response_text)
            logger.info(
                "Approved response sent via %s to %s",
                channel_type, channel_id,
            )
        except Exception as e:
            logger.error("Failed to send approved response: %s", e)
            raise

        # Sent successfully — now persist the approved/edited state.
        approval = await self.repo.approve(
            approval_id,
            reviewed_by=reviewed_by,
            edited_response=edited_response,
        )
        if not approval:
            raise ValueError(f"Approval '{approval_id}' not found")

        # Store in channel message history
        session_id = approval.get("session_id")
        if session_id:
            try:
                from services.channels.channel_service import ChannelService
                svc = ChannelService(self.db)
                await svc._store_channel_message(session_id, "assistant", response_text)
            except Exception:
                pass

        return approval

    async def reject_approval(
        self,
        approval_id: str,
        reviewed_by: str = "desktop-user",
    ) -> Dict[str, Any]:
        """Reject a pending approval (discard the draft)."""
        approval = await self.repo.reject(approval_id, reviewed_by=reviewed_by)
        if not approval:
            raise ValueError(f"Approval '{approval_id}' not found")
        return approval

    async def count_pending(self) -> int:
        pending = await self.repo.list_pending(limit=500)
        return sum(1 for d in pending if not _is_retired_social_approval(d))

    async def retire_legacy_social_approvals(self) -> int:
        """Reject leftover pending social-distribution drafts from pre-v1.2 installs."""
        pending = await self.repo.list_pending(limit=500)
        retired = 0
        for doc in pending:
            if _is_retired_social_approval(doc):
                await self.repo.reject(
                    doc["approval_id"],
                    reviewed_by="vesper-v1.2-migration",
                )
                retired += 1
        return retired

    async def _send_via_channel(
        self,
        channel_type: str,
        channel_id: str,
        text: str,
    ) -> None:
        """Send a message via the appropriate channel bot."""
        from services.channels.channel_service import (
            TelegramBot,
            DiscordBot,
            WhatsAppBot,
            TeamsBot,
        )

        ct = str(channel_type or "").strip().lower()
        if ct == "telegram":
            bot = TelegramBot()
            await bot.send_message(channel_id, text)
        elif ct == "discord":
            bot = DiscordBot()
            await bot.send_message(channel_id, text)
        elif ct == "whatsapp":
            bot = WhatsAppBot()
            await bot.send_message(channel_id, text)
        elif ct == "teams":
            logger.warning("Teams send not implemented in approval flow")
        elif ct in RETIRED_SOCIAL_CHANNELS:
            raise RuntimeError("Social distribution publishing has been retired in Vesper v1.2")
        else:
            logger.warning("Unknown channel type: %s", channel_type)
