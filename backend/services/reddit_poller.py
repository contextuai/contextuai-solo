"""Background poller for Reddit inbound (subreddit mentions + inbox DMs).

Polls every 60s, respects Reddit's 60 req/min OAuth rate limit.
Dispatches new items into channel_service.handle_message() so the
existing trigger + approval pipeline applies.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60


class RedditPoller:
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
        logger.info("Reddit poller started (interval=%ss)", POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Reddit poller stopped")

    async def _run(self) -> None:
        from repositories.reddit_repository import RedditRepository
        from services.reddit_client import RedditClient

        repo = RedditRepository(self.db)

        while not self._stopping:
            try:
                account = await repo.get_active()
                if not account:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                client = RedditClient(
                    client_id=account["client_id"],
                    client_secret=account["client_secret"],
                    username=account["username"],
                    password=account["password"],
                    user_agent=account.get("user_agent", "ContextuAI-Solo/1.0"),
                )
                last_seen = account.get("last_seen_ids", {}) or {}

                for sub in account.get("subreddits", []):
                    after = last_seen.get(sub)
                    comments = await client.fetch_new_comments(sub, after, limit=25)
                    if comments:
                        await repo.update_last_seen(account["_id"], sub, comments[0]["id"])
                        for c in reversed(comments):
                            await self._dispatch_comment(c, account.get("keywords", []))

                if account.get("poll_inbox"):
                    after = last_seen.get("inbox")
                    inbox = await client.fetch_inbox(after, limit=25)
                    if inbox:
                        await repo.update_last_seen(account["_id"], "inbox", inbox[0]["id"])
                        for m in reversed(inbox):
                            await self._dispatch_dm(m)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Reddit poll cycle failed: %s", e)

            try:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

    async def _dispatch_comment(self, comment: dict, keywords: list) -> None:
        if keywords and not any(k.lower() in comment["body"].lower() for k in keywords):
            return

        from services.channels.channel_service import (
            ChannelMessage,
            ChannelType,
            channel_service,
        )

        msg = ChannelMessage(
            channel_type=ChannelType("reddit"),
            channel_id=comment["subreddit"],
            sender_id=comment["author"],
            sender_name=comment["author"],
            text=comment["body"],
            message_id=comment["fullname"],
            thread_id=comment["submission_id"],
            raw=comment,
        )
        try:
            await channel_service.handle_message(msg)
        except Exception as e:
            logger.exception("Failed to dispatch reddit comment %s: %s", comment["id"], e)

    async def _dispatch_dm(self, dm: dict) -> None:
        from services.channels.channel_service import (
            ChannelMessage,
            ChannelType,
            channel_service,
        )

        msg = ChannelMessage(
            channel_type=ChannelType("reddit"),
            channel_id="inbox",
            sender_id=dm["author"],
            sender_name=dm["author"],
            text=dm["body"],
            message_id=dm["fullname"],
            raw=dm,
        )
        try:
            await channel_service.handle_message(msg)
        except Exception as e:
            logger.exception("Failed to dispatch reddit DM %s: %s", dm["id"], e)


reddit_poller: Optional[RedditPoller] = None


def get_poller(db) -> RedditPoller:
    global reddit_poller
    if reddit_poller is None:
        reddit_poller = RedditPoller(db)
    return reddit_poller
