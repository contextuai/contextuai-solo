"""Background poller for Twitter/X inbound (mentions + DMs).

Polls every 90s — Twitter's free tier is stricter than Reddit. Dispatches
new items into channel_service.handle_message() so the trigger + approval
pipeline applies.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 90


class TwitterPoller:
    """Single-account background poller."""

    def __init__(self, db):
        self.db = db
        self._task: Optional[asyncio.Task] = None
        self._stopping = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run())
        logger.info("Twitter poller started (interval=%ss)", POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Twitter poller stopped")

    async def _run(self) -> None:
        from repositories.twitter_repository import TwitterRepository
        from services.twitter_client import TwitterClient

        repo = TwitterRepository(self.db)

        while not self._stopping:
            try:
                account = await repo.get_active()
                if not account:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                client = TwitterClient(
                    api_key=account.get("api_key"),
                    api_secret=account.get("api_secret"),
                    access_token=account.get("access_token"),
                    access_token_secret=account.get("access_token_secret"),
                    bearer_token=account.get("bearer_token"),
                )
                last_seen = account.get("last_seen_ids", {}) or {}

                if account.get("poll_mentions") and account.get("user_id"):
                    mentions = await client.fetch_mentions(
                        user_id=account["user_id"],
                        since_id=last_seen.get("mentions"),
                        max_results=25,
                    )
                    if mentions:
                        # Mentions come newest-first; record newest id
                        await repo.update_last_seen(
                            account["_id"], "mentions", mentions[0]["id"]
                        )
                        for m in reversed(mentions):
                            await self._dispatch_mention(m, account.get("keywords", []))

                if account.get("poll_dms"):
                    dms = await client.fetch_dm_events(
                        since_id=last_seen.get("dms"),
                        max_results=25,
                    )
                    if dms:
                        await repo.update_last_seen(
                            account["_id"], "dms", dms[0]["id"]
                        )
                        for d in reversed(dms):
                            await self._dispatch_dm(d)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Twitter poll cycle failed: %s", e)

            try:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

    async def _dispatch_mention(self, mention: dict, keywords: list) -> None:
        text = mention.get("text", "") or ""
        if keywords and not any(k.lower() in text.lower() for k in keywords):
            return

        from services.channels.channel_service import (
            ChannelMessage,
            ChannelType,
            channel_service,
        )

        msg = ChannelMessage(
            channel_type=ChannelType("twitter"),
            channel_id="mentions",
            sender_id=str(mention.get("author_id", "")),
            sender_name=mention.get("author_name") or str(mention.get("author_id", "")),
            text=text,
            message_id=str(mention.get("id", "")),
            thread_id=mention.get("conversation_id"),
            raw=mention,
        )
        try:
            await channel_service.handle_message(msg)
        except Exception as e:
            logger.exception("Failed to dispatch twitter mention %s: %s", mention.get("id"), e)

    async def _dispatch_dm(self, dm: dict) -> None:
        from services.channels.channel_service import (
            ChannelMessage,
            ChannelType,
            channel_service,
        )

        msg = ChannelMessage(
            channel_type=ChannelType("twitter"),
            channel_id="dm",
            sender_id=str(dm.get("sender_id", "")),
            sender_name=str(dm.get("sender_id", "")),
            text=dm.get("text", "") or "",
            message_id=str(dm.get("id", "")),
            raw=dm,
        )
        try:
            await channel_service.handle_message(msg)
        except Exception as e:
            logger.exception("Failed to dispatch twitter DM %s: %s", dm.get("id"), e)


twitter_poller: Optional[TwitterPoller] = None


def get_poller(db) -> TwitterPoller:
    global twitter_poller
    if twitter_poller is None:
        twitter_poller = TwitterPoller(db)
    return twitter_poller
