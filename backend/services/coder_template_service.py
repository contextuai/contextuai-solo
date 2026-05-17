"""Coder Template Service.

Reads template manifests from a directory tree at
``coder-templates/<id>/manifest.json`` (relative to the repo root). Each
template ships a ``files/`` subfolder containing the actual scaffold the
user gets when they create a project with that template.

Configurable lookup root via the ``CODER_TEMPLATE_DIR`` env var; default is
``<repo>/coder-templates/``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from models.coder_models import CoderTemplateInfo

logger = logging.getLogger(__name__)


def _default_template_dir() -> Path:
    here = Path(__file__).resolve()
    # backend/services/coder_template_service.py → repo root is parents[2]
    repo_root = here.parents[2]
    return repo_root / "coder-templates"


class CoderTemplateService:
    """Catalog of starter templates + light scaffolder."""

    def __init__(self, template_dir: Optional[str] = None):
        env_dir = os.environ.get("CODER_TEMPLATE_DIR")
        self.template_dir: Path = Path(
            template_dir or env_dir or _default_template_dir()
        )

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def _load_manifest(self, manifest_path: Path) -> Optional[dict]:
        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("Failed to load template manifest: %s", manifest_path)
            return None

    def list_templates(self) -> List[CoderTemplateInfo]:
        """Return all manifests under the template directory."""
        if not self.template_dir.exists():
            logger.warning(
                "Coder template dir does not exist: %s", self.template_dir
            )
            return []

        out: List[CoderTemplateInfo] = []
        for child in sorted(self.template_dir.iterdir()):
            if not child.is_dir():
                continue
            manifest = child / "manifest.json"
            if not manifest.exists():
                continue
            data = self._load_manifest(manifest)
            if not data:
                continue
            try:
                out.append(
                    CoderTemplateInfo(
                        id=data.get("id") or child.name,
                        name=data.get("name") or child.name,
                        description=data.get("description") or "",
                        runtime=data.get("runtime") or "auto",
                        init_commands=list(data.get("init_commands") or []),
                        starter_prompt=data.get("starter_prompt") or "",
                    )
                )
            except Exception:
                logger.exception("Invalid template manifest at %s", manifest)
        return out

    def get_template(self, template_id: str) -> Optional[CoderTemplateInfo]:
        for t in self.list_templates():
            if t.id == template_id:
                return t
        return None

    def get_raw_manifest(self, template_id: str) -> Optional[dict]:
        """Return the unparsed manifest dict (so callers can read
        ``run_command`` / ``preview_port`` not exposed via CoderTemplateInfo)."""
        manifest_path = self.template_dir / template_id / "manifest.json"
        if not manifest_path.exists():
            return None
        return self._load_manifest(manifest_path)

    # ------------------------------------------------------------------
    # Scaffolding
    # ------------------------------------------------------------------

    def scaffold_into_folder(
        self,
        template_id: str,
        dest_folder: str,
        force: bool = False,
    ) -> None:
        """Copy the template's ``files/`` subfolder into ``dest_folder``.

        Aborts if dest_folder is non-empty unless ``force=True``. Existing
        files at the destination are not overwritten unless ``force=True``.
        """
        src = self.template_dir / template_id / "files"
        if not src.exists() or not src.is_dir():
            raise FileNotFoundError(
                f"Template '{template_id}' has no files/ folder at {src}"
            )

        dest = Path(dest_folder)
        dest.mkdir(parents=True, exist_ok=True)

        # Refuse to scaffold over a non-empty folder unless force=True.
        if any(dest.iterdir()) and not force:
            raise FileExistsError(
                f"Destination {dest} is not empty; refusing to scaffold "
                f"(pass force=True to override)."
            )

        for entry in src.rglob("*"):
            rel = entry.relative_to(src)
            target = dest / rel
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                if target.exists() and not force:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry, target)

    # ------------------------------------------------------------------
    # Run command inference (for ad-hoc projects without a template)
    # ------------------------------------------------------------------

    def infer_run_command(
        self, folder_path: str
    ) -> Tuple[Optional[str], Optional[int]]:
        """Best-effort run command + preview port inference.

        Heuristics:
          - ``package.json``  → ``npm run dev`` on port 5173
          - ``requirements.txt`` → ``python main.py``
          - ``index.html``    → ``python -m http.server 8080`` on port 8080

        Returns (command, preview_port) or (None, None).
        """
        folder = Path(folder_path)
        if not folder.exists():
            return (None, None)

        if (folder / "package.json").exists():
            return ("npm run dev", 5173)
        if (folder / "requirements.txt").exists():
            return ("python main.py", None)
        if (folder / "index.html").exists():
            return ("python -m http.server 8080", 8080)
        return (None, None)
