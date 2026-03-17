"""
Local Model Manager

Handles model downloads from HuggingFace, filesystem management, hardware
detection, and installed model tracking.  No external dependencies beyond
``huggingface_hub`` and ``psutil``.
"""

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODELS_DIR = os.path.join(
    os.path.expanduser("~"), ".contextuai-solo", "models"
)

RAM_CAP_GB = 64


class ModelManager:
    """Download, delete, and inventory local GGUF models."""

    def __init__(self, models_dir: Optional[str] = None):
        self.models_dir = models_dir or DEFAULT_MODELS_DIR
        Path(self.models_dir).mkdir(parents=True, exist_ok=True)
        self._active_downloads: Dict[str, bool] = {}
        logger.info("ModelManager ready — models dir: %s", self.models_dir)

    # ── System info ─────────────────────────────────────────────────────────

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Detect system RAM and GPU, capped at 64 GB for recommendations."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            total_ram = round(mem.total / (1024 ** 3))
            available_ram = round(mem.available / (1024 ** 3))
        except (ImportError, AttributeError) as exc:
            logger.warning("psutil unavailable (%s) — falling back to platform detection", exc)
            total_ram, available_ram = ModelManager._fallback_ram()


        gpu_info = ModelManager._detect_gpu()

        capped_ram = min(total_ram, RAM_CAP_GB)
        if capped_ram >= 48:
            max_params = "70B"
        elif capped_ram >= 24:
            max_params = "32B"
        elif capped_ram >= 16:
            max_params = "14B"
        elif capped_ram >= 10:
            max_params = "8B"
        elif capped_ram >= 6:
            max_params = "3B"
        else:
            max_params = "1B"

        return {
            "total_ram_gb": total_ram,
            "available_ram_gb": available_ram,
            "capped_ram_gb": capped_ram,
            "os": platform.system().lower(),
            "arch": platform.machine(),
            "gpu": gpu_info.get("name") if gpu_info else None,
            "gpu_vram_gb": gpu_info.get("vram_gb") if gpu_info else None,
            "max_recommended_params": max_params,
        }

    @staticmethod
    def _fallback_ram():
        """Detect RAM without psutil (Windows wmic / Linux meminfo)."""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["wmic", "OS", "get", "TotalVisibleMemorySize", "/value"],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.strip().splitlines():
                    if "=" in line:
                        kb = int(line.split("=")[1].strip())
                        total = round(kb / (1024 ** 2))
                        return total, max(total // 2, 4)
            else:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal"):
                            kb = int(line.split()[1])
                            total = round(kb / (1024 ** 2))
                            return total, max(total // 2, 4)
        except Exception:
            pass
        return 8, 4

    @staticmethod
    def _detect_gpu() -> Optional[Dict[str, Any]]:
        """Best-effort GPU detection via nvidia-smi."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                name = parts[0].strip()
                vram_mb = int(parts[1].strip()) if len(parts) > 1 else 0
                return {"name": name, "vram_gb": round(vram_mb / 1024, 1)}
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        return None

    # ── Installed models ────────────────────────────────────────────────────

    def list_installed(self) -> List[Dict[str, Any]]:
        """Scan models directory (and chat/ subdir) and return installed model info."""
        from .model_catalog import LOCAL_MODEL_CATALOG

        models_path = Path(self.models_dir)
        if not models_path.exists():
            return []

        filename_to_catalog = {}
        for entry in LOCAL_MODEL_CATALOG:
            filename_to_catalog[entry["hf_filename"].lower()] = entry

        # Scan both root and chat/ subdirectory (legacy download location)
        gguf_files = list(sorted(models_path.glob("*.gguf")))
        chat_dir = models_path / "chat"
        if chat_dir.exists():
            gguf_files.extend(sorted(chat_dir.glob("*.gguf")))
        # Dedupe by filename (prefer root over chat/)
        seen: set = set()
        unique_files = []
        for f in gguf_files:
            if f.name.lower() not in seen:
                seen.add(f.name.lower())
                unique_files.append(f)

        installed = []
        for f in unique_files:
            size_gb = round(f.stat().st_size / (1024 ** 3), 2)
            modified = f.stat().st_mtime
            catalog_entry = filename_to_catalog.get(f.name.lower())

            info: Dict[str, Any] = {
                "filename": f.name,
                "path": str(f),
                "size_gb": size_gb,
                "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(modified)),
            }

            if catalog_entry:
                info.update({
                    "id": catalog_entry["id"],
                    "name": catalog_entry["name"],
                    "provider": catalog_entry["provider"],
                    "parameter_size": catalog_entry["parameter_size"],
                    "categories": catalog_entry["categories"],
                    "ram_required_gb": catalog_entry["ram_required_gb"],
                })
            else:
                info.update({
                    "id": f.stem.lower(),
                    "name": f.stem,
                    "provider": "Custom",
                    "parameter_size": "Unknown",
                    "categories": ["general"],
                    "ram_required_gb": None,
                })

            installed.append(info)

        return installed

    def is_installed(self, model_id: str) -> bool:
        """Check if a catalog model is already downloaded (root or chat/ subdir)."""
        from .model_catalog import get_model
        entry = get_model(model_id)
        if not entry:
            return False
        filename = entry["hf_filename"]
        return (
            (Path(self.models_dir) / filename).exists()
            or (Path(self.models_dir) / "chat" / filename).exists()
        )

    def get_model_path(self, model_id: str) -> Optional[str]:
        """Get the local path for an installed model (checks root and chat/)."""
        from .model_catalog import get_model
        entry = get_model(model_id)
        if not entry:
            return None
        filename = entry["hf_filename"]
        for search_dir in [Path(self.models_dir), Path(self.models_dir) / "chat"]:
            path = search_dir / filename
            if path.exists():
                return str(path)
        return None

    # ── Download ────────────────────────────────────────────────────────────

    async def download_model(
        self, model_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download a GGUF model from HuggingFace. Yields SSE progress dicts."""
        from .model_catalog import get_model

        entry = get_model(model_id)
        if not entry:
            yield {"status": "error", "detail": f"Model '{model_id}' not found in catalog"}
            return

        repo_id = entry["hf_repo"]
        filename = entry["hf_filename"]
        dest_path = os.path.join(self.models_dir, filename)

        if os.path.isfile(dest_path):
            size = os.path.getsize(dest_path)
            yield {"status": "done", "path": dest_path, "completed": size, "total": size, "percent": 100.0}
            return

        self._active_downloads[model_id] = False

        yield {
            "status": "starting",
            "model_id": model_id,
            "repo": repo_id,
            "filename": filename,
            "completed": 0,
            "total": 0,
            "percent": 0.0,
        }

        try:
            result = await asyncio.to_thread(
                self._download_with_progress,
                repo_id, filename, dest_path, model_id,
            )

            if self._active_downloads.get(model_id):
                if os.path.isfile(dest_path):
                    os.remove(dest_path)
                yield {"status": "cancelled", "model_id": model_id}
            elif result.get("error"):
                yield {"status": "error", "detail": result["error"]}
            else:
                yield {
                    "status": "done",
                    "path": dest_path,
                    "completed": result.get("size", 0),
                    "total": result.get("size", 0),
                    "percent": 100.0,
                }
        except Exception as exc:
            logger.exception("Download failed: %s", model_id)
            yield {"status": "error", "detail": str(exc)}
        finally:
            self._active_downloads.pop(model_id, None)

    def _download_with_progress(
        self, repo_id: str, filename: str, dest_path: str, model_id: str
    ) -> Dict[str, Any]:
        """Blocking download using huggingface_hub (runs in thread)."""
        try:
            from huggingface_hub import hf_hub_download

            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=self.models_dir,
                local_dir_use_symlinks=False,
            )

            size = os.path.getsize(downloaded_path)
            logger.info("Download complete: %s (%.2f GB)", downloaded_path, size / (1024**3))
            return {"path": downloaded_path, "size": size}

        except Exception as exc:
            logger.exception("HuggingFace download error")
            return {"error": str(exc)}

    def cancel_download(self, model_id: str) -> bool:
        """Request cancellation of an active download."""
        if model_id in self._active_downloads:
            self._active_downloads[model_id] = True
            return True
        return False

    # ── Delete ──────────────────────────────────────────────────────────────

    def delete_model(self, model_id: str) -> Dict[str, Any]:
        """Delete a downloaded model file."""
        from .model_catalog import get_model

        entry = get_model(model_id)
        if not entry:
            for m in self.list_installed():
                if m["id"] == model_id:
                    path = m["path"]
                    os.remove(path)
                    return {"status": "deleted", "model_id": model_id, "path": path}
            return {"status": "error", "detail": f"Model '{model_id}' not found"}

        path = Path(self.models_dir) / entry["hf_filename"]
        if not path.exists():
            return {"status": "error", "detail": f"Model '{model_id}' is not installed"}

        freed_gb = round(path.stat().st_size / (1024 ** 3), 2)
        os.remove(path)
        logger.info("Deleted model: %s (freed %.2f GB)", path, freed_gb)

        return {
            "status": "deleted",
            "model_id": model_id,
            "freed_gb": freed_gb,
        }

    # ── Disk usage ──────────────────────────────────────────────────────────

    def get_disk_usage(self) -> Dict[str, Any]:
        """Report total disk space used by downloaded models."""
        models_path = Path(self.models_dir)
        if not models_path.exists():
            return {"models_gb": 0, "model_count": 0, "disk_free_gb": 0, "disk_total_gb": 0}

        total = sum(f.stat().st_size for f in models_path.glob("*.gguf"))
        count = len(list(models_path.glob("*.gguf")))

        disk = shutil.disk_usage(self.models_dir)
        return {
            "models_gb": round(total / (1024 ** 3), 2),
            "model_count": count,
            "disk_free_gb": round(disk.free / (1024 ** 3), 1),
            "disk_total_gb": round(disk.total / (1024 ** 3), 1),
        }

    # ── Custom model download ───────────────────────────────────────────────

    async def download_custom(
        self, hf_repo: str, hf_filename: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download any GGUF file from HuggingFace by repo + filename."""
        dest_path = os.path.join(self.models_dir, hf_filename)

        if os.path.isfile(dest_path):
            size = os.path.getsize(dest_path)
            yield {"status": "done", "path": dest_path, "completed": size, "total": size, "percent": 100.0}
            return

        yield {"status": "starting", "repo": hf_repo, "filename": hf_filename, "completed": 0, "total": 0, "percent": 0.0}

        try:
            result = await asyncio.to_thread(
                self._download_with_progress,
                hf_repo, hf_filename, dest_path, f"custom:{hf_repo}",
            )
            if result.get("error"):
                yield {"status": "error", "detail": result["error"]}
            else:
                yield {
                    "status": "done",
                    "path": dest_path,
                    "completed": result.get("size", 0),
                    "total": result.get("size", 0),
                    "percent": 100.0,
                }
        except Exception as exc:
            yield {"status": "error", "detail": str(exc)}


# ── Singleton ───────────────────────────────────────────────────────────────

model_manager = ModelManager()
