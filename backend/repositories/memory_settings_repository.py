"""Single-row settings doc for the Unified Memory Layer kill switch + toggles.

There is exactly one settings document, ``_id="default"``. Mirrors the
KB pattern of talking to ``self.collection`` directly rather than going
through the generic ``BaseRepository.create``/``update`` helpers, since we
want full control over the fixed id and a merge-with-defaults read path.
"""
from datetime import datetime
from typing import Any, Dict

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.base_repository import BaseRepository

_SETTINGS_ID = "default"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "enabled": True,
    "chat_enabled": True,
    "crews_enabled": True,
    "channels_enabled": False,
    "confidence_threshold": 0.6,
}


class MemorySettingsRepository(BaseRepository):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "memory_settings")

    async def get_settings(self) -> Dict[str, Any]:
        """Return stored settings merged over defaults; defaults alone if absent."""
        doc = await self.collection.find_one({"_id": _SETTINGS_ID})
        if not doc:
            return {"_id": _SETTINGS_ID, **DEFAULT_SETTINGS}
        return {**DEFAULT_SETTINGS, **doc}

    async def update_settings(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        current = await self.get_settings()
        current.update(patch)
        current["_id"] = _SETTINGS_ID
        current["updated_at"] = datetime.utcnow().isoformat()

        existing = await self.collection.find_one({"_id": _SETTINGS_ID})
        if existing:
            await self.collection.update_one({"_id": _SETTINGS_ID}, {"$set": current})
        else:
            await self.collection.insert_one(current)
        return current
