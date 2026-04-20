"""Thin async wrapper over praw for Reddit inbound/outbound ops.

praw is sync; we run calls in a threadpool to keep the event loop responsive.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

try:
    import praw  # type: ignore
except ImportError:
    praw = None

logger = logging.getLogger(__name__)


class RedditClient:
    """One instance per Reddit account config."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        user_agent: str = "ContextuAI-Solo/1.0",
    ):
        if praw is None:
            raise RuntimeError("praw not installed. Add 'praw' to requirements.txt.")
        self._reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=user_agent,
            check_for_async=False,
        )

    async def test_connection(self) -> Dict[str, Any]:
        def _check() -> Dict[str, Any]:
            me = self._reddit.user.me()
            return {"ok": True, "username": me.name if me else None}

        return await asyncio.to_thread(_check)

    async def fetch_new_comments(
        self, subreddit: str, after_id: Optional[str], limit: int = 25
    ) -> List[Dict[str, Any]]:
        def _fetch() -> List[Dict[str, Any]]:
            items = []
            sub = self._reddit.subreddit(subreddit)
            for c in sub.comments(limit=limit):
                if after_id and c.id == after_id:
                    break
                items.append(
                    {
                        "id": c.id,
                        "fullname": c.fullname,
                        "author": str(c.author) if c.author else "[deleted]",
                        "body": c.body,
                        "permalink": f"https://reddit.com{c.permalink}",
                        "subreddit": subreddit,
                        "created_utc": c.created_utc,
                        "submission_id": c.submission.id,
                    }
                )
            return items

        return await asyncio.to_thread(_fetch)

    async def fetch_inbox(self, after_id: Optional[str], limit: int = 25) -> List[Dict[str, Any]]:
        def _fetch() -> List[Dict[str, Any]]:
            items = []
            for msg in self._reddit.inbox.unread(limit=limit):
                if after_id and msg.id == after_id:
                    break
                items.append(
                    {
                        "id": msg.id,
                        "fullname": msg.fullname,
                        "author": str(msg.author) if msg.author else "[deleted]",
                        "body": msg.body,
                        "subject": getattr(msg, "subject", ""),
                        "was_comment": getattr(msg, "was_comment", False),
                    }
                )
            return items

        return await asyncio.to_thread(_fetch)

    async def reply_to_comment(self, comment_fullname: str, text: str) -> str:
        def _reply() -> str:
            comment = self._reddit.comment(id=comment_fullname.replace("t1_", ""))
            reply = comment.reply(body=text)
            return reply.id

        return await asyncio.to_thread(_reply)

    async def send_dm(self, recipient: str, subject: str, text: str) -> bool:
        def _send() -> bool:
            self._reddit.redditor(recipient).message(subject=subject, message=text)
            return True

        return await asyncio.to_thread(_send)
