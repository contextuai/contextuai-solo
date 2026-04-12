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
        return await self.repo.list_pending(limit=limit)

    async def list_all(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return await self.repo.list_all(status=status, limit=limit)

    async def get(self, approval_id: str) -> Optional[Dict[str, Any]]:
        return await self.repo.get_by_id(approval_id)

    async def approve_and_send(
        self,
        approval_id: str,
        edited_response: Optional[str] = None,
        reviewed_by: str = "desktop-user",
    ) -> Dict[str, Any]:
        """Approve (optionally edit) and send the response via the channel."""
        approval = await self.repo.approve(
            approval_id,
            reviewed_by=reviewed_by,
            edited_response=edited_response,
        )
        if not approval:
            raise ValueError(f"Approval '{approval_id}' not found")

        response_text = approval.get("final_response") or approval.get("draft_response", "")
        channel_type = approval["channel_type"]
        channel_id = approval["channel_id"]

        # Send via the appropriate channel
        try:
            await self._send_via_channel(channel_type, channel_id, response_text)
            logger.info(
                "Approved response sent via %s to %s",
                channel_type, channel_id,
            )
        except Exception as e:
            logger.error("Failed to send approved response: %s", e)
            raise

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
        return await self.repo.count_pending()

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

        if channel_type == "telegram":
            bot = TelegramBot()
            await bot.send_message(channel_id, text)
        elif channel_type == "discord":
            bot = DiscordBot()
            await bot.send_message(channel_id, text)
        elif channel_type == "whatsapp":
            bot = WhatsAppBot()
            await bot.send_message(channel_id, text)
        elif channel_type == "teams":
            logger.warning("Teams send not implemented in approval flow")
        elif channel_type in ("linkedin", "twitter", "instagram", "facebook"):
            from services.distribution_service import DistributionService
            dist_svc = DistributionService(self.db)
            result = await dist_svc.publish(
                channel_id=channel_id,
                content=text,
                published_by="approval-queue",
            )
            if not result.get("result", {}).get("success"):
                raise RuntimeError(
                    f"Distribution publish failed: {result.get('result', {}).get('error', 'unknown')}"
                )
        else:
            logger.warning("Unknown channel type: %s", channel_type)
