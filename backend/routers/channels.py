"""
Multi-Channel Bot Router — Unified endpoints for Teams, Discord, WhatsApp, and Telegram.

Endpoints:
  GET    /api/v1/channels/status               — Channel configuration status
  GET    /api/v1/channels/registrations         — List channel registrations
  POST   /api/v1/channels/registrations         — Register a channel
  GET    /api/v1/channels/conversations         — List active conversations

  POST   /api/v1/channels/teams/webhook         — Teams Bot Framework webhook
  POST   /api/v1/channels/discord/webhook       — Discord interactions webhook
  GET    /api/v1/channels/whatsapp/webhook      — WhatsApp verification
  POST   /api/v1/channels/whatsapp/webhook      — WhatsApp inbound messages
  POST   /api/v1/channels/telegram/webhook      — Telegram Bot API webhook
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from services.auth_service import get_current_user, require_admin
from services.channels.channel_service import (
    ChannelService,
    ChannelType,
    TeamsBot,
    DiscordBot,
    WhatsAppBot,
    TelegramBot,
    get_channel_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/channels", tags=["channels"])


# ------------------------------------------------------------------
# Request Models
# ------------------------------------------------------------------

class RegisterChannelRequest(BaseModel):
    channel_type: str = Field(..., pattern="^(teams|discord|whatsapp|telegram)$")
    config: dict = Field(default_factory=dict)


# ------------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------------

async def get_channel_service(
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ChannelService:
    return ChannelService(db)


def _get_user_id(user: dict) -> str:
    return user.get("user_id") or user.get("sub")


# ------------------------------------------------------------------
# Channel Management
# ------------------------------------------------------------------

@router.get("/status")
async def channel_status(user: dict = Depends(get_current_user)):
    """Get configuration status for all bot channels."""
    return {"status": "success", "data": get_channel_status()}


@router.get("/registrations", dependencies=[Depends(require_admin)])
async def list_registrations(
    user: dict = Depends(get_current_user),
    svc: ChannelService = Depends(get_channel_service),
):
    """List all channel registrations."""
    org = user.get("organization")
    regs = await svc.list_registrations(org)
    return {"status": "success", "data": {"registrations": regs, "count": len(regs)}}


@router.post("/registrations", dependencies=[Depends(require_admin)])
async def register_channel(
    request: RegisterChannelRequest,
    user: dict = Depends(get_current_user),
    svc: ChannelService = Depends(get_channel_service),
):
    """Register a new channel integration."""
    user_id = _get_user_id(user)
    org = user.get("organization")
    reg = await svc.register_channel(
        channel_type=request.channel_type,
        config=request.config,
        organization=org,
        registered_by=user_id,
    )
    return {"status": "success", "data": reg}


@router.get("/conversations", dependencies=[Depends(require_admin)])
async def list_conversations(
    channel_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    svc: ChannelService = Depends(get_channel_service),
):
    """List active conversations across all channels."""
    convos = await svc.get_conversations(channel_type, limit)
    return {"status": "success", "data": {"conversations": convos, "count": len(convos)}}


# ------------------------------------------------------------------
# Teams Webhook
# ------------------------------------------------------------------

@router.post("/teams/webhook")
async def teams_webhook(
    request: Request,
    svc: ChannelService = Depends(get_channel_service),
):
    """Microsoft Teams Bot Framework webhook endpoint."""
    if not TeamsBot.is_configured():
        raise HTTPException(503, "Teams bot not configured")

    body = await request.json()
    msg = svc.teams_bot.parse_activity(body)

    if msg is None:
        return {"status": "ok", "detail": "Non-message activity ignored"}

    result = await svc.handle_message(msg)

    # Send reply back to Teams
    try:
        await svc.teams_bot.send_reply(body, result["response"])
    except Exception as e:
        logger.error(f"Failed to reply to Teams: {e}")

    return {"status": "success", "data": result}


# ------------------------------------------------------------------
# Discord Webhook
# ------------------------------------------------------------------

@router.post("/discord/webhook")
async def discord_webhook(
    request: Request,
    svc: ChannelService = Depends(get_channel_service),
):
    """Discord interactions webhook endpoint."""
    if not DiscordBot.is_configured():
        raise HTTPException(503, "Discord bot not configured")

    body_bytes = await request.body()
    body = await request.json()

    # Verify Discord signature
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    if not svc.discord_bot.verify_signature(body_bytes, signature, timestamp):
        raise HTTPException(401, "Invalid signature")

    # Handle PING (Discord verification)
    if body.get("type") == 1:
        return {"type": 1}

    msg = svc.discord_bot.parse_interaction(body)
    if msg is None:
        return {"status": "ok", "detail": "Unhandled interaction type"}

    result = await svc.handle_message(msg)

    # Respond to interaction
    try:
        await svc.discord_bot.send_interaction_response(
            body["id"], body["token"], result["response"]
        )
    except Exception as e:
        logger.error(f"Failed to respond to Discord interaction: {e}")

    return {"status": "success", "data": result}


# ------------------------------------------------------------------
# Telegram Webhook
# ------------------------------------------------------------------

@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    svc: ChannelService = Depends(get_channel_service),
):
    """Telegram Bot API webhook endpoint."""
    if not TelegramBot.is_configured():
        raise HTTPException(503, "Telegram bot not configured")

    body = await request.json()
    msg = svc.telegram_bot.parse_update(body)

    if msg is None:
        return {"status": "ok", "detail": "Non-text message or unsupported update"}

    result = await svc.handle_message(msg)

    # Reply via Telegram
    try:
        await svc.telegram_bot.send_message(msg.channel_id, result["response"])
    except Exception as e:
        logger.error(f"Failed to reply via Telegram: {e}")

    return {"status": "success", "data": result}


# ------------------------------------------------------------------
# WhatsApp Webhook
# ------------------------------------------------------------------

@router.get("/whatsapp/webhook")
async def whatsapp_verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    """WhatsApp webhook verification (Meta Cloud API)."""
    result = WhatsAppBot.verify_webhook(mode, token, challenge)
    if result is not None:
        return Response(content=result, media_type="text/plain")
    raise HTTPException(403, "Verification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(
    request: Request,
    svc: ChannelService = Depends(get_channel_service),
):
    """WhatsApp inbound message webhook."""
    if not WhatsAppBot.is_configured():
        raise HTTPException(503, "WhatsApp bot not configured")

    body = await request.json()
    msg = svc.whatsapp_bot.parse_message(body)

    if msg is None:
        return {"status": "ok", "detail": "Non-text message or status update"}

    result = await svc.handle_message(msg)

    # Reply via WhatsApp
    try:
        await svc.whatsapp_bot.send_message(msg.sender_id, result["response"])
    except Exception as e:
        logger.error(f"Failed to reply via WhatsApp: {e}")

    return {"status": "success", "data": result}
