"""
Slack integration tools for Strands Agent.
Provides channel messaging, search, and history capabilities via Slack Web API.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from strands.tools import tool

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackTools:
    """
    Slack operation tools for workspace communication and search.

    Features:
    - Send messages to channels
    - List channels
    - Search messages
    - Get channel history
    """

    def __init__(self, persona_id: str, credentials: Dict[str, Any]):
        """
        Initialize Slack tools with persona credentials.

        Args:
            persona_id: Unique persona identifier
            credentials: Slack connection credentials:
                - botToken: Slack bot token (xoxb-...)
                - channel: Default channel name
                - workspace: Workspace name
        """
        self.persona_id = persona_id
        self.credentials = credentials
        self.bot_token = credentials.get("botToken", "")
        self.default_channel = credentials.get("channel", "")
        self.workspace = credentials.get("workspace", "")
        self.headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        logger.info(f"SlackTools initialized for persona {persona_id}, workspace: {self.workspace}")

    def get_tools(self):
        """Return all Slack operation tools as a list for Strands Agent."""
        return [
            self.send_message,
            self.list_channels,
            self.search_messages,
            self.get_channel_history,
            self.test_connection,
        ]

    @tool
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test Slack connection by verifying the bot token.

        Returns:
            Dictionary with connection status:
            {
                "success": bool,
                "response_time_ms": float,
                "bot_name": str,
                "team": str,
                "error": Optional[str]
            }
        """
        try:
            import httpx

            start_time = time.time()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{SLACK_API_BASE}/auth.test",
                    headers=self.headers,
                )
                data = resp.json()
            response_time = round((time.time() - start_time) * 1000)

            if data.get("ok"):
                return {
                    "success": True,
                    "response_time_ms": response_time,
                    "bot_name": data.get("user", ""),
                    "team": data.get("team", ""),
                    "team_id": data.get("team_id", ""),
                }
            else:
                return {
                    "success": False,
                    "error": data.get("error", "Unknown error"),
                }

        except Exception as e:
            logger.error(f"Slack connection test failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @tool
    async def send_message(
        self,
        text: str,
        channel: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a message to a Slack channel.

        Args:
            text: Message text (supports Slack markdown/mrkdwn)
            channel: Channel name or ID (e.g., "#general" or "C01234567"). Uses default channel if not provided.

        Returns:
            Dictionary with send result:
            {
                "success": bool,
                "channel": str,
                "timestamp": str (message ts),
                "error": Optional[str]
            }
        """
        channel = channel or self.default_channel
        if not channel:
            return {"success": False, "error": "No channel specified and no default channel configured"}

        # Strip leading # if present
        if channel.startswith("#"):
            channel = channel[1:]

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{SLACK_API_BASE}/chat.postMessage",
                    headers=self.headers,
                    json={"channel": channel, "text": text},
                )
                data = resp.json()

            if data.get("ok"):
                return {
                    "success": True,
                    "channel": data.get("channel", channel),
                    "timestamp": data.get("ts", ""),
                }
            else:
                return {"success": False, "error": data.get("error", "Failed to send message")}

        except Exception as e:
            logger.error(f"Error sending Slack message: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @tool
    async def list_channels(
        self,
        limit: int = 50,
        types: str = "public_channel"
    ) -> Dict[str, Any]:
        """
        List Slack channels in the workspace.

        Args:
            limit: Maximum channels to return (default: 50, max: 200)
            types: Channel types: "public_channel", "private_channel", or both comma-separated

        Returns:
            Dictionary with channel list:
            {
                "success": bool,
                "channels": List of { id, name, topic, member_count, is_archived },
                "count": int,
                "error": Optional[str]
            }
        """
        limit = min(limit, 200)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{SLACK_API_BASE}/conversations.list",
                    headers=self.headers,
                    params={"limit": limit, "types": types, "exclude_archived": "true"},
                )
                data = resp.json()

            if data.get("ok"):
                channels = [
                    {
                        "id": ch["id"],
                        "name": ch.get("name", ""),
                        "topic": ch.get("topic", {}).get("value", ""),
                        "member_count": ch.get("num_members", 0),
                        "is_archived": ch.get("is_archived", False),
                    }
                    for ch in data.get("channels", [])
                ]
                return {"success": True, "channels": channels, "count": len(channels)}
            else:
                return {"success": False, "error": data.get("error", "Failed to list channels"), "channels": [], "count": 0}

        except Exception as e:
            logger.error(f"Error listing Slack channels: {e}", exc_info=True)
            return {"success": False, "error": str(e), "channels": [], "count": 0}

    @tool
    async def search_messages(
        self,
        query: str,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Search Slack messages across the workspace.

        Args:
            query: Search query text (supports Slack search syntax: from:user, in:channel, etc.)
            limit: Maximum results to return (default: 20, max: 100)

        Returns:
            Dictionary with search results:
            {
                "success": bool,
                "query": str,
                "messages": List of { text, user, channel, timestamp, permalink },
                "count": int,
                "total": int,
                "error": Optional[str]
            }
        """
        limit = min(limit, 100)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{SLACK_API_BASE}/search.messages",
                    headers=self.headers,
                    params={"query": query, "count": limit, "sort": "timestamp", "sort_dir": "desc"},
                )
                data = resp.json()

            if data.get("ok"):
                matches = data.get("messages", {}).get("matches", [])
                messages = [
                    {
                        "text": m.get("text", "")[:500],
                        "user": m.get("username", m.get("user", "")),
                        "channel": m.get("channel", {}).get("name", ""),
                        "timestamp": m.get("ts", ""),
                        "permalink": m.get("permalink", ""),
                    }
                    for m in matches
                ]
                total = data.get("messages", {}).get("total", 0)
                return {"success": True, "query": query, "messages": messages, "count": len(messages), "total": total}
            else:
                return {"success": False, "error": data.get("error", "Search failed"), "query": query, "messages": [], "count": 0, "total": 0}

        except Exception as e:
            logger.error(f"Error searching Slack messages: {e}", exc_info=True)
            return {"success": False, "error": str(e), "query": query, "messages": [], "count": 0, "total": 0}

    @tool
    async def get_channel_history(
        self,
        channel: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get recent message history from a Slack channel.

        Args:
            channel: Channel name or ID. Uses default channel if not provided.
            limit: Maximum messages to return (default: 20, max: 100)

        Returns:
            Dictionary with channel history:
            {
                "success": bool,
                "channel": str,
                "messages": List of { text, user, timestamp, type },
                "count": int,
                "error": Optional[str]
            }
        """
        channel = channel or self.default_channel
        if not channel:
            return {"success": False, "error": "No channel specified"}

        if channel.startswith("#"):
            channel = channel[1:]

        limit = min(limit, 100)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                # If channel is a name, resolve to ID
                channel_id = channel
                if not channel.startswith("C"):
                    list_resp = await client.get(
                        f"{SLACK_API_BASE}/conversations.list",
                        headers=self.headers,
                        params={"limit": 200, "types": "public_channel,private_channel"},
                    )
                    list_data = list_resp.json()
                    if list_data.get("ok"):
                        for ch in list_data.get("channels", []):
                            if ch["name"] == channel:
                                channel_id = ch["id"]
                                break

                resp = await client.get(
                    f"{SLACK_API_BASE}/conversations.history",
                    headers=self.headers,
                    params={"channel": channel_id, "limit": limit},
                )
                data = resp.json()

            if data.get("ok"):
                messages = [
                    {
                        "text": m.get("text", "")[:500],
                        "user": m.get("user", ""),
                        "timestamp": m.get("ts", ""),
                        "type": m.get("type", "message"),
                    }
                    for m in data.get("messages", [])
                ]
                return {"success": True, "channel": channel, "messages": messages, "count": len(messages)}
            else:
                return {"success": False, "error": data.get("error", "Failed to get history"), "channel": channel, "messages": [], "count": 0}

        except Exception as e:
            logger.error(f"Error getting channel history: {e}", exc_info=True)
            return {"success": False, "error": str(e), "channel": channel, "messages": [], "count": 0}
