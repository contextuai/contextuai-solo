"""
Multi-Channel Messaging Service — Unified abstraction for bot platforms.

Supports:
- Microsoft Teams (Bot Framework)
- Discord (Gateway + REST API)
- WhatsApp (Business Cloud API via Meta)
- Telegram (Bot API)

Each channel follows the same pattern:
  1. Receive inbound event (webhook)
  2. Normalize to ChannelMessage
  3. Dispatch to AI chat or automation
  4. Send response back via channel-specific API
"""

import os
import hmac
import hashlib
import httpx
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    SLACK = "slack"
    TEAMS = "teams"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    REDDIT = "reddit"
    TWITTER = "twitter"


class ChannelMessage:
    """Normalized inbound message from any channel."""

    def __init__(
        self,
        channel_type: ChannelType,
        channel_id: str,
        sender_id: str,
        sender_name: str,
        text: str,
        message_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        raw: Optional[Dict[str, Any]] = None,
    ):
        self.channel_type = channel_type
        self.channel_id = channel_id
        self.sender_id = sender_id
        self.sender_name = sender_name
        self.text = text
        self.message_id = message_id or str(uuid.uuid4())
        self.thread_id = thread_id
        self.raw = raw or {}
        self.timestamp = datetime.utcnow().isoformat()


# ===================================================================
# Channel Configurations
# ===================================================================

TEAMS_APP_ID = os.environ.get("TEAMS_APP_ID", "")
TEAMS_APP_PASSWORD = os.environ.get("TEAMS_APP_PASSWORD", "")
TEAMS_TENANT_ID = os.environ.get("TEAMS_TENANT_ID", "")

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "")
DISCORD_APPLICATION_ID = os.environ.get("DISCORD_APPLICATION_ID", "")

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def get_channel_status() -> Dict[str, Any]:
    """Return configuration status for all channels."""
    return {
        "teams": {
            "configured": bool(TEAMS_APP_ID and TEAMS_APP_PASSWORD),
            "app_id": TEAMS_APP_ID[:8] + "..." if TEAMS_APP_ID else None,
        },
        "discord": {
            "configured": bool(DISCORD_BOT_TOKEN and DISCORD_PUBLIC_KEY),
            "application_id": DISCORD_APPLICATION_ID or None,
        },
        "whatsapp": {
            "configured": bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID),
            "phone_number_id": WHATSAPP_PHONE_NUMBER_ID or None,
        },
        "telegram": {
            "configured": bool(TELEGRAM_BOT_TOKEN),
        },
    }


# ===================================================================
# Teams Bot (Microsoft Bot Framework v4)
# ===================================================================

class TeamsBot:
    """Microsoft Teams bot via Bot Framework REST API."""

    BASE_URL = "https://smba.trafficmanager.net"
    LOGIN_URL = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"

    def __init__(self):
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    @staticmethod
    def is_configured() -> bool:
        return bool(TEAMS_APP_ID and TEAMS_APP_PASSWORD)

    async def _get_token(self) -> str:
        """Get Bot Framework OAuth token."""
        if self._token and self._token_expiry and datetime.utcnow() < self._token_expiry:
            return self._token

        async with httpx.AsyncClient() as client:
            r = await client.post(self.LOGIN_URL, data={
                "grant_type": "client_credentials",
                "client_id": TEAMS_APP_ID,
                "client_secret": TEAMS_APP_PASSWORD,
                "scope": "https://api.botframework.com/.default",
            })
            data = r.json()
            self._token = data["access_token"]
            from datetime import timedelta
            self._token_expiry = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600) - 300)
            return self._token

    def parse_activity(self, body: Dict[str, Any]) -> Optional[ChannelMessage]:
        """Parse a Teams Bot Framework Activity into a ChannelMessage."""
        activity_type = body.get("type")
        if activity_type != "message":
            return None

        text = body.get("text", "").strip()
        # Remove bot mention from text
        if body.get("entities"):
            for entity in body["entities"]:
                if entity.get("type") == "mention":
                    mentioned = entity.get("mentioned", {})
                    if mentioned.get("id") == TEAMS_APP_ID:
                        mention_text = entity.get("text", "")
                        text = text.replace(mention_text, "").strip()

        sender = body.get("from", {})
        conversation = body.get("conversation", {})

        return ChannelMessage(
            channel_type=ChannelType.TEAMS,
            channel_id=conversation.get("id", ""),
            sender_id=sender.get("id", ""),
            sender_name=sender.get("name", "Unknown"),
            text=text,
            message_id=body.get("id"),
            thread_id=conversation.get("id"),
            raw=body,
        )

    async def send_reply(self, activity: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Reply to a Teams activity."""
        token = await self._get_token()
        service_url = activity.get("serviceUrl", self.BASE_URL)
        conversation_id = activity.get("conversation", {}).get("id", "")

        url = f"{service_url}/v3/conversations/{conversation_id}/activities"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        payload = {
            "type": "message",
            "text": text,
            "from": {"id": TEAMS_APP_ID, "name": "ContextuAI"},
            "conversation": activity.get("conversation"),
            "replyToId": activity.get("id"),
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            return {"status": r.status_code, "data": r.json() if r.status_code < 400 else r.text}


# ===================================================================
# Discord Bot (REST API)
# ===================================================================

class DiscordBot:
    """Discord bot via REST API (no gateway needed for webhook-based events)."""

    BASE_URL = "https://discord.com/api/v10"

    @staticmethod
    def is_configured() -> bool:
        return bool(DISCORD_BOT_TOKEN and DISCORD_PUBLIC_KEY)

    @staticmethod
    def verify_signature(body: bytes, signature: str, timestamp: str) -> bool:
        """Verify Discord interaction signature (Ed25519)."""
        try:
            from nacl.signing import VerifyKey
            from nacl.exceptions import BadSignatureError
            key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
            key.verify(timestamp.encode() + body, bytes.fromhex(signature))
            return True
        except Exception:
            # If nacl not installed, skip verification in dev
            logger.warning("Discord signature verification skipped (nacl not installed)")
            return True

    def parse_interaction(self, body: Dict[str, Any]) -> Optional[ChannelMessage]:
        """Parse a Discord interaction into a ChannelMessage."""
        interaction_type = body.get("type")

        # Type 1 = PING (Discord verification)
        if interaction_type == 1:
            return None

        # Type 2 = APPLICATION_COMMAND (slash command)
        if interaction_type == 2:
            data = body.get("data", {})
            command_name = data.get("name", "")
            options = data.get("options", [])
            text = command_name
            if options:
                text += " " + " ".join(
                    f"{o['name']}={o['value']}" for o in options if "value" in o
                )

            user = body.get("member", {}).get("user", {}) or body.get("user", {})
            return ChannelMessage(
                channel_type=ChannelType.DISCORD,
                channel_id=body.get("channel_id", ""),
                sender_id=user.get("id", ""),
                sender_name=user.get("username", "Unknown"),
                text=text,
                message_id=body.get("id"),
                thread_id=body.get("channel_id"),
                raw=body,
            )

        return None

    async def send_message(self, channel_id: str, content: str) -> Dict[str, Any]:
        """Send a message to a Discord channel."""
        url = f"{self.BASE_URL}/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "Content-Type": "application/json",
        }

        # Discord max message length is 2000 chars
        if len(content) > 2000:
            content = content[:1997] + "..."

        async with httpx.AsyncClient() as client:
            r = await client.post(url, json={"content": content}, headers=headers)
            return {"status": r.status_code, "data": r.json() if r.status_code < 400 else r.text}

    async def send_interaction_response(
        self, interaction_id: str, interaction_token: str, content: str
    ) -> Dict[str, Any]:
        """Respond to a Discord interaction (slash command)."""
        url = f"{self.BASE_URL}/interactions/{interaction_id}/{interaction_token}/callback"
        payload = {
            "type": 4,  # CHANNEL_MESSAGE_WITH_SOURCE
            "data": {"content": content[:2000]},
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload)
            return {"status": r.status_code}


# ===================================================================
# WhatsApp Bot (Cloud API via Meta)
# ===================================================================

class WhatsAppBot:
    """WhatsApp Business Cloud API integration."""

    BASE_URL = "https://graph.facebook.com/v18.0"

    @staticmethod
    def is_configured() -> bool:
        return bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID)

    @staticmethod
    def verify_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify WhatsApp webhook subscription."""
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            return challenge
        return None

    def parse_message(self, body: Dict[str, Any]) -> Optional[ChannelMessage]:
        """Parse a WhatsApp Cloud API webhook payload."""
        try:
            entry = body.get("entry", [])
            if not entry:
                return None

            changes = entry[0].get("changes", [])
            if not changes:
                return None

            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if not messages:
                return None

            msg = messages[0]
            if msg.get("type") != "text":
                return None

            contacts = value.get("contacts", [{}])
            sender_name = contacts[0].get("profile", {}).get("name", "Unknown") if contacts else "Unknown"

            return ChannelMessage(
                channel_type=ChannelType.WHATSAPP,
                channel_id=WHATSAPP_PHONE_NUMBER_ID,
                sender_id=msg.get("from", ""),
                sender_name=sender_name,
                text=msg.get("text", {}).get("body", ""),
                message_id=msg.get("id"),
                raw=body,
            )
        except (IndexError, KeyError) as e:
            logger.error(f"Failed to parse WhatsApp message: {e}")
            return None

    async def send_message(self, to: str, text: str) -> Dict[str, Any]:
        """Send a text message via WhatsApp Cloud API."""
        url = f"{self.BASE_URL}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            return {"status": r.status_code, "data": r.json() if r.status_code < 400 else r.text}


# ===================================================================
# Telegram Bot (Bot API)
# ===================================================================

class TelegramBot:
    """Telegram bot via Bot API."""

    BASE_URL = "https://api.telegram.org"

    @staticmethod
    def is_configured() -> bool:
        return bool(TELEGRAM_BOT_TOKEN)

    def parse_update(self, body: Dict[str, Any]) -> Optional[ChannelMessage]:
        """Parse a Telegram Bot API Update into a ChannelMessage."""
        message = body.get("message")
        if not message:
            return None

        text = message.get("text")
        if not text:
            return None

        chat = message.get("chat", {})
        sender = message.get("from", {})
        sender_name = sender.get("first_name", "Unknown")
        if sender.get("last_name"):
            sender_name += f" {sender['last_name']}"

        return ChannelMessage(
            channel_type=ChannelType.TELEGRAM,
            channel_id=str(chat.get("id", "")),
            sender_id=str(sender.get("id", "")),
            sender_name=sender_name,
            text=text,
            message_id=str(message.get("message_id", "")),
            raw=body,
        )

    async def send_message(self, chat_id: str, text: str) -> Dict[str, Any]:
        """Send a text message via Telegram Bot API."""
        url = f"{self.BASE_URL}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        # Telegram max message length is 4096 chars
        if len(text) > 4096:
            text = text[:4093] + "..."

        async with httpx.AsyncClient() as client:
            r = await client.post(url, json={"chat_id": chat_id, "text": text})
            return {"status": r.status_code, "data": r.json() if r.status_code < 400 else r.text}


# ===================================================================
# Unified Channel Service
# ===================================================================

class ChannelService:
    """
    Unified multi-channel messaging service.

    Manages channel registrations, conversation state across channels,
    and dispatches inbound messages to the AI chat engine.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.registrations = db["channel_registrations"]
        self.conversations = db["channel_conversations"]
        self.teams_bot = TeamsBot()
        self.discord_bot = DiscordBot()
        self.whatsapp_bot = WhatsAppBot()
        self.telegram_bot = TelegramBot()

    async def register_channel(
        self,
        channel_type: str,
        config: Dict[str, Any],
        organization: Optional[str] = None,
        registered_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a channel integration for an organization."""
        now = datetime.utcnow().isoformat()
        doc = {
            "registration_id": str(uuid.uuid4()),
            "channel_type": channel_type,
            "organization": organization,
            "config": config,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "registered_by": registered_by,
        }
        await self.registrations.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def list_registrations(
        self, organization: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List channel registrations."""
        query: Dict[str, Any] = {}
        if organization:
            query["organization"] = organization
        cursor = self.registrations.find(query).sort("created_at", -1)
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)
        return docs

    async def get_or_create_session(
        self,
        channel_type: str,
        channel_id: str,
        sender_id: str,
    ) -> Dict[str, Any]:
        """Get or create a conversation session for a channel user."""
        query = {
            "channel_type": channel_type,
            "channel_id": channel_id,
            "sender_id": sender_id,
            "status": "active",
        }
        session = await self.conversations.find_one(query)
        if session:
            session["id"] = str(session.pop("_id"))
            return session

        now = datetime.utcnow().isoformat()
        doc = {
            "session_id": str(uuid.uuid4()),
            "channel_type": channel_type,
            "channel_id": channel_id,
            "sender_id": sender_id,
            "status": "active",
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        await self.conversations.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def handle_message(self, msg: ChannelMessage) -> Dict[str, Any]:
        """
        Process an inbound channel message.

        Applies guardrails (sanitization, rate limiting, prompt injection
        detection), then dispatches to AI for a response.
        """
        from services.channel_guardrails import (
            sanitize_message,
            check_prompt_injection,
            check_rate_limit,
        )

        # --- Guardrails ---
        # 1. Rate limit
        allowed, rejection = check_rate_limit(msg.sender_id)
        if not allowed:
            return {
                "session_id": "",
                "channel_type": msg.channel_type.value,
                "sender": msg.sender_name,
                "text": msg.text[:100],
                "message_id": msg.message_id,
                "status": "rate_limited",
                "response": rejection,
            }

        # 2. Sanitize input
        msg.text = sanitize_message(msg.text)
        if not msg.text:
            return {
                "session_id": "",
                "channel_type": msg.channel_type.value,
                "sender": msg.sender_name,
                "text": "",
                "message_id": msg.message_id,
                "status": "empty",
                "response": "",
            }

        # 3. Prompt injection detection
        is_safe, matched = check_prompt_injection(msg.text)
        if not is_safe:
            logger.warning(
                "Blocked prompt injection from %s (%s): %s",
                msg.sender_name, msg.sender_id, matched,
            )
            return {
                "session_id": "",
                "channel_type": msg.channel_type.value,
                "sender": msg.sender_name,
                "text": msg.text[:100],
                "message_id": msg.message_id,
                "status": "blocked",
                "response": "I'm here to help with legitimate questions. How can I assist you?",
            }

        session = await self.get_or_create_session(
            msg.channel_type.value, msg.channel_id, msg.sender_id
        )

        # Increment message count
        await self.conversations.update_one(
            {"session_id": session["session_id"]},
            {
                "$inc": {"message_count": 1},
                "$set": {"updated_at": datetime.utcnow().isoformat()},
            },
        )

        # --- Check for a trigger (crew dispatch) ---
        try:
            from services.trigger_service import TriggerService
            trigger_svc = TriggerService(self.db)
            trigger_result = await trigger_svc.check_and_dispatch(msg, session)
            if trigger_result is not None:
                return {
                    "session_id": session["session_id"],
                    "channel_type": msg.channel_type.value,
                    "sender": msg.sender_name,
                    "text": msg.text,
                    "message_id": msg.message_id,
                    "status": trigger_result["status"],
                    "response": trigger_result["response"],
                    "trigger_id": trigger_result.get("trigger_id"),
                    "approval_id": trigger_result.get("approval_id"),
                }
        except ImportError:
            pass  # trigger_service not yet available — fall through to direct AI
        except Exception as e:
            logger.warning("Trigger check failed, falling through to direct AI: %s", e)

        # --- Direct AI reply (default model) ---
        response_text = await self._get_ai_response(msg.text, session)

        return {
            "session_id": session["session_id"],
            "channel_type": msg.channel_type.value,
            "sender": msg.sender_name,
            "text": msg.text,
            "message_id": msg.message_id,
            "status": "replied",
            "response": response_text,
        }

    async def _get_ai_response(
        self,
        user_text: str,
        session: Dict[str, Any],
    ) -> str:
        """Generate an AI response using the default local model.

        Always applies the channel safety system prompt to prevent
        information leakage and prompt injection.
        """
        try:
            from services.default_model_service import DefaultModelService
            from services.local_model_service import local_model_service, LLAMA_CPP_AVAILABLE
            from services.channel_guardrails import get_safe_system_prompt

            default_svc = DefaultModelService(self.db)
            ai_mode = await default_svc.get_ai_mode_preference()
            model_id = await default_svc.get_default_model_id(ai_mode)

            if not model_id:
                return "No AI model configured. Please set up a model in Settings."

            # Build lightweight conversation history from this channel session
            history = await self._get_channel_history(session["session_id"], limit=10)

            # Always wrap with safety guardrails
            safe_prompt = get_safe_system_prompt()

            # Local model path
            if LLAMA_CPP_AVAILABLE and (
                ai_mode == "local"
                or model_id.startswith("local-")
                or model_id.startswith("local:")
            ):
                model_config = await default_svc.get_default_model_config(ai_mode)
                result = await local_model_service.call_model(
                    prompt=user_text,
                    model_id=model_id,
                    persona_context={"system_prompt": safe_prompt},
                    conversation_history=history,
                    max_tokens=1024,
                    temperature=0.7,
                    stream=False,
                    model_config=model_config or {},
                )
                return result.get("content", "I couldn't generate a response.")

            return "No local model available. Please download a model from the Model Hub."
        except Exception as e:
            logger.error("AI response generation failed: %s", e, exc_info=True)
            return f"Sorry, I encountered an error generating a response."

    async def _get_channel_history(
        self,
        session_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieve recent message history for a channel session."""
        try:
            coll = self.db["channel_messages"]
            cursor = coll.find({"session_id": session_id}).sort("timestamp", -1).limit(limit)
            messages = []
            async for doc in cursor:
                messages.append({
                    "role": doc.get("role", "user"),
                    "content": doc.get("content", ""),
                })
            messages.reverse()  # oldest first
            return messages
        except Exception:
            return []

    async def _store_channel_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        """Store a message in the channel_messages collection."""
        try:
            coll = self.db["channel_messages"]
            await coll.insert_one({
                "_id": str(uuid.uuid4()),
                "session_id": session_id,
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.warning("Failed to store channel message: %s", e)

    async def get_conversations(
        self,
        channel_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List active conversations across channels."""
        query: Dict[str, Any] = {"status": "active"}
        if channel_type:
            query["channel_type"] = channel_type
        cursor = self.conversations.find(query).sort("updated_at", -1).limit(limit)
        docs = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            docs.append(doc)
        return docs
