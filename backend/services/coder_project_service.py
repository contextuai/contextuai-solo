"""Coder Project Service — wiring layer for the router.

Pulls together the repository, template service and run service. Validates
folder paths, scaffolds templates on create, and resolves the run command
from either the project's template or folder heuristics.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from models.coder_models import CoderProjectCreate
from repositories.coder_project_repository import CoderProjectRepository
from services.coder_run_service import CoderRunService
from services.coder_template_service import CoderTemplateService

logger = logging.getLogger(__name__)


class CoderProjectService:
    def __init__(
        self,
        repo: CoderProjectRepository,
        template_service: CoderTemplateService,
        run_service: CoderRunService,
    ):
        self.repo = repo
        self.templates = template_service
        self.runs = run_service

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_project(self, payload: CoderProjectCreate) -> Dict[str, Any]:
        """Create a new project row and (optionally) scaffold a template."""
        folder = payload.folder_path
        # Create the folder if it doesn't exist; reject if it's a file.
        if os.path.exists(folder):
            if not os.path.isdir(folder):
                raise ValueError(f"folder_path exists but is not a directory: {folder}")
        else:
            os.makedirs(folder, exist_ok=True)

        # Scaffold template (if any) BEFORE persisting so a scaffold failure
        # doesn't leave a half-created project row behind.
        if payload.template_id:
            template = self.templates.get_template(payload.template_id)
            if template is None:
                raise ValueError(f"Unknown template_id: {payload.template_id}")
            try:
                self.templates.scaffold_into_folder(payload.template_id, folder)
            except FileExistsError as exc:
                # Folder already had files — abort cleanly so the caller can
                # surface a 4xx and let the user pick a different folder.
                raise ValueError(str(exc)) from exc

        runtime = payload.runtime or "auto"
        # If template chose a runtime, prefer it over the request hint.
        if payload.template_id:
            t = self.templates.get_template(payload.template_id)
            if t and t.runtime:
                runtime = t.runtime

        row = await self.repo.create(
            name=payload.name,
            folder_path=folder,
            template_id=payload.template_id,
            runtime=runtime,
        )
        return row

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        return await self.repo.get_by_id(project_id)

    async def list_projects(self) -> list[Dict[str, Any]]:
        return await self.repo.list_all()

    async def update_project(
        self, project_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        # Mirror set_trusted's status promotion when ``trusted`` is in the patch.
        if "trusted" in data:
            update = {k: v for k, v in data.items() if k != "trusted"}
            updated = await self.repo.set_trusted(project_id, bool(data["trusted"]))
            if update:
                updated = await self.repo.update(project_id, update)
            return updated
        return await self.repo.update(project_id, data)

    async def delete_project(self, project_id: str) -> bool:
        # Stop a running process first so we don't leak a child.
        if self.runs.is_running(project_id):
            await self.runs.stop(project_id)
        return await self.repo.delete(project_id)

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def _resolve_run_command(
        self,
        project: Dict[str, Any],
        override: Optional[str],
    ) -> Optional[str]:
        if override:
            return override
        template_id = project.get("template_id")
        if template_id:
            manifest = self.templates.get_raw_manifest(template_id)
            if manifest and manifest.get("run_command"):
                return manifest["run_command"]
        cmd, _port = self.templates.infer_run_command(
            project.get("folder_path") or ""
        )
        return cmd

    async def start_project(
        self,
        project_id: str,
        command_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        project = await self.repo.get_by_id(project_id)
        if not project:
            raise LookupError(f"Project not found: {project_id}")
        if not project.get("trusted"):
            raise PermissionError(
                "Project must be marked trusted before running commands."
            )

        command = self._resolve_run_command(project, command_override)
        if not command:
            raise ValueError(
                "No run command available — provide one via the request body."
            )

        # Stash on the dict for the run service (avoids re-resolving).
        project["_resolved_run_command"] = command

        result = await self.runs.start(project, command_override=command)
        if result.get("status") == "started":
            await self.repo.update_last_run(project_id)
            await self.repo.set_status(project_id, "running")
        return result

    async def stop_project(self, project_id: str) -> bool:
        killed = await self.runs.stop(project_id)
        await self.repo.set_status(project_id, "stopped")
        return killed
