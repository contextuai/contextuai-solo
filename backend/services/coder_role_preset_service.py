"""Coder Role Preset Service.

Loads the four role preset JSON files from ``coder-role-presets/`` at the
repo root (mirrors the blueprints/ and agent-library/ pattern). Presets are
cached in memory and invalidated when the file's mtime changes.

Public API
----------
- ``list_presets()`` — lightweight summary list
- ``get_preset(preset_id)`` — full detail including role list
- ``apply_preset(project_id, preset_id, role_repo)`` — atomically replaces
  the project's roles with the preset's roles and returns the new list
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from models.coder_models import (
    RolePresetDetail,
    RolePresetRole,
    RolePresetSummary,
)
from repositories.coder_agent_role_repository import CoderAgentRoleRepository

logger = logging.getLogger(__name__)

# Default path — resolved relative to the repo root at import time.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PRESET_DIR = _REPO_ROOT / "coder-role-presets"


class CoderRolePresetService:
    """Load and apply Coder role presets from disk."""

    def __init__(self, preset_dir: Optional[Path] = None) -> None:
        self._preset_dir: Path = Path(
            os.environ.get("CODER_ROLE_PRESET_DIR", str(preset_dir or _DEFAULT_PRESET_DIR))
        )
        # Cache: preset_id -> (mtime, parsed_dict)
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _preset_files(self) -> List[Path]:
        """Return all .json files in the preset directory."""
        if not self._preset_dir.exists():
            logger.warning("Preset directory not found: %s", self._preset_dir)
            return []
        return sorted(self._preset_dir.glob("*.json"))

    def _load_file(self, path: Path) -> Optional[Dict[str, Any]]:
        """Load a preset file, using the cache when the mtime hasn't changed."""
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None

        pid = path.stem  # filename without extension
        cached_mtime, cached_data = self._cache.get(pid, (None, None))
        if cached_mtime == mtime and cached_data is not None:
            return cached_data

        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._cache[pid] = (mtime, data)
            return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load preset %s: %s", path, exc)
            return None

    def _all_presets(self) -> List[Dict[str, Any]]:
        result = []
        for path in self._preset_files():
            data = self._load_file(path)
            if data:
                result.append(data)
        return result

    def _find_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        for path in self._preset_files():
            if path.stem == preset_id:
                return self._load_file(path)
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_presets(self) -> List[RolePresetSummary]:
        """Return a lightweight summary of every preset."""
        summaries = []
        for data in self._all_presets():
            try:
                summaries.append(
                    RolePresetSummary(
                        preset_id=data["preset_id"],
                        name=data["name"],
                        description=data["description"],
                        workflow_mode=data["workflow_mode"],
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed preset: %s", exc)
        return summaries

    def get_preset(self, preset_id: str) -> Optional[RolePresetDetail]:
        """Return full preset detail (including roles), or None if not found."""
        data = self._find_preset(preset_id)
        if not data:
            return None
        try:
            roles = [RolePresetRole(**r) for r in data.get("roles", [])]
            return RolePresetDetail(
                preset_id=data["preset_id"],
                name=data["name"],
                description=data["description"],
                workflow_mode=data["workflow_mode"],
                roles=roles,
            )
        except (KeyError, ValueError) as exc:
            logger.error("Malformed preset %s: %s", preset_id, exc)
            return None

    async def apply_preset(
        self,
        project_id: str,
        preset_id: str,
        role_repo: CoderAgentRoleRepository,
    ) -> List[Dict[str, Any]]:
        """Clear existing roles for *project_id* and insert the preset's roles.

        Returns the newly inserted role rows sorted by order.
        Raises ``KeyError`` when the preset is not found.
        """
        detail = self.get_preset(preset_id)
        if detail is None:
            raise KeyError(f"Preset '{preset_id}' not found")

        # Clear existing roles atomically.
        await role_repo.delete_for_project(project_id)

        now = datetime.utcnow().isoformat()
        inserted = []
        for role in sorted(detail.roles, key=lambda r: r.order):
            row = {
                "role_id": str(uuid.uuid4()),
                "project_id": project_id,
                "role_kind": role.role_kind.value,
                "display_name": role.display_name,
                "system_prompt": role.system_prompt,
                "model_id": role.model_id,
                "temperature": role.temperature,
                "max_tokens": role.max_tokens,
                "enabled": role.enabled,
                "order": role.order,
                "created_at": now,
                "updated_at": now,
            }
            created = await role_repo.create(row)
            inserted.append(created)

        return inserted
