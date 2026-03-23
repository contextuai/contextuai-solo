"""
Default Model Service — resolves the appropriate model ID based on AI mode (local vs cloud).

Used by workspace orchestrator, crew orchestrator, and the preference endpoint
to ensure consistent model resolution across all workflows.
"""

import logging
from typing import Optional, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from repositories.model_repository import ModelRepository

logger = logging.getLogger(__name__)

# Cloud fallback: Bedrock Claude Sonnet
DEFAULT_CLOUD_MODEL = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"


class DefaultModelService:
    """Resolves the default model ID based on the current AI mode."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.model_repo = ModelRepository(db)

    async def get_default_model_id(self, mode: str) -> str:
        """
        Return the best default model ID for the given mode.

        Args:
            mode: "local" or "cloud"

        Returns:
            Model ID string
        """
        if mode == "local":
            return await self._get_default_local_model_id()
        return DEFAULT_CLOUD_MODEL

    async def _get_default_local_model_id(self) -> str:
        """Get the first available enabled local model."""
        try:
            models = await self.model_repo.get_enabled_models()
            for m in models:
                mid = m.get("_id", m.get("id", ""))
                provider = m.get("provider", "")
                if provider == "local" or str(mid).startswith("local-") or str(mid).startswith("local:"):
                    return str(mid)
        except Exception as e:
            logger.warning(f"Failed to query local models: {e}")
        return ""

    async def get_default_model_config(self, mode: str) -> Optional[Dict[str, Any]]:
        """
        Return the full model config for the default model in the given mode.
        """
        model_id = await self.get_default_model_id(mode)
        if not model_id:
            return None
        try:
            model = await self.model_repo.get_one({"_id": model_id})
            return model
        except Exception:
            return None

    async def get_ai_mode_preference(self) -> str:
        """Read AI mode preference from the settings collection."""
        try:
            coll = self.db["settings"]
            doc = await coll.find_one({"_id": "ai_mode_preference"})
            if doc:
                return doc.get("ai_mode", "cloud")
        except Exception as e:
            logger.debug(f"Failed to read ai_mode preference: {e}")
        return "cloud"

    async def set_ai_mode_preference(self, mode: str) -> None:
        """Save AI mode preference to the settings collection."""
        try:
            coll = self.db["settings"]
            # Delete + insert to avoid $set issues with the SQLite compat layer
            await coll.delete_one({"_id": "ai_mode_preference"})
            await coll.insert_one({
                "_id": "ai_mode_preference",
                "ai_mode": mode,
            })
        except Exception as e:
            logger.warning(f"Failed to save ai_mode preference: {e}")
