"""
Crew Template Seeder

Reads *.json crew-template files from the on-disk template library and
upserts them into the ``crew_templates`` collection. Templates are stored
separately from user-created crews so that the system catalog is never
polluted with user data and can be re-seeded safely on every startup.

Mirrors the pattern of BlueprintLibraryService.sync_library_to_db().
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class CrewTemplateSeeder:
    """
    Service for syncing pre-built crew templates from disk into the
    ``crew_templates`` collection. System templates (``is_system=True``)
    ship with the app; user-created crews live in the ``crews`` collection
    and are never touched by this service.
    """

    LIBRARY_PATH: str = os.getenv(
        "CREW_TEMPLATE_LIBRARY_PATH",
        os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            ),
            "crew-templates",
        ),
    )

    # -------------------------------------------------------------------------
    # Parsing
    # -------------------------------------------------------------------------

    def parse_template_file(self, file_path: str) -> Dict[str, Any]:
        """Load and validate a single crew-template JSON file."""
        file_path = os.path.abspath(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        required = ("id", "name", "execution_mode", "agents")
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(
                f"Crew template {Path(file_path).name} missing required fields: {missing}"
            )

        template_id = str(data["id"]).strip()
        if not template_id:
            raise ValueError(f"Crew template {Path(file_path).name} has empty id")

        agents: List[str] = list(data.get("agents", []))
        bindings: List[Dict[str, Any]] = []
        for b in data.get("channel_bindings", []):
            if not isinstance(b, dict) or "channel_type" not in b:
                continue
            bindings.append({
                "channel_type": str(b["channel_type"]),
                "enabled": bool(b.get("enabled", True)),
                "approval_required": bool(b.get("approval_required", False)),
            })

        return {
            "id": template_id,
            "name": str(data["name"]).strip(),
            "description": str(data.get("description", "")).strip(),
            "execution_mode": str(data["execution_mode"]).strip(),
            "agents": agents,
            "channel_bindings": bindings,
            "tags": list(data.get("tags", [])),
            "is_template": bool(data.get("is_template", True)),
            "is_system": bool(data.get("is_system", True)),
            "file_path": file_path,
        }

    # -------------------------------------------------------------------------
    # Sync
    # -------------------------------------------------------------------------

    async def sync_library_to_db(self, collection) -> int:
        """
        Scan all *.json files in the template library and upsert them into
        the ``crew_templates`` collection.

        Returns the number of newly inserted templates. Existing templates
        (matched by ``_id``) are left untouched so that user edits or
        manual overrides are preserved across restarts.
        """
        library = Path(self.LIBRARY_PATH)
        if not library.exists():
            logger.warning(
                "Crew template library not found at %s — skipping sync", library
            )
            return 0

        seeded = 0
        for json_file in sorted(library.glob("*.json")):
            try:
                parsed = self.parse_template_file(str(json_file))
                template_id = parsed["id"]

                existing = await collection.find_one({"_id": template_id})
                if existing is not None:
                    continue

                now = datetime.utcnow().isoformat() + "Z"
                doc = {
                    "_id": template_id,
                    "template_id": template_id,
                    "name": parsed["name"],
                    "description": parsed["description"],
                    "execution_mode": parsed["execution_mode"],
                    "agents": parsed["agents"],
                    "channel_bindings": parsed["channel_bindings"],
                    "tags": parsed["tags"],
                    "is_template": parsed["is_template"],
                    "is_system": parsed["is_system"],
                    "source": "library",
                    "usage_count": 0,
                    "created_by": "system",
                    "deleted_at": None,
                    "created_at": now,
                    "updated_at": now,
                }

                await collection.insert_one(doc)
                seeded += 1
            except Exception:
                logger.warning(
                    "Failed to sync crew template: %s", json_file.name, exc_info=True
                )

        return seeded
