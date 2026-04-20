"""Persistence for Reddit account config + poll state."""
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository


class RedditRepository(BaseRepository):
    """Stores one Reddit account config per user (single-user desktop = 1 doc)."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "reddit_accounts")

    async def get_active(self) -> Optional[Dict[str, Any]]:
        """Return the single enabled Reddit account (desktop = 1 user)."""
        cursor = self.collection.find({"enabled": True})
        docs = await cursor.to_list(length=1)
        return docs[0] if docs else None

    async def update_last_seen(self, account_id: str, source: str, last_id: str) -> None:
        """Track last seen comment/submission id per subreddit (or 'inbox')."""
        await self.collection.update_one(
            {"_id": account_id},
            {"$set": {f"last_seen_ids.{source}": last_id}},
        )
