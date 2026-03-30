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
                    "hf_repo": catalog_entry.get("hf_repo"),
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
        import queue as _queue
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

        # ── Pre-flight: verify HuggingFace is reachable ──────────────────
        # Check both the API (metadata) and CDN (file downloads) domains.
        # Windows firewalls often block one but not the other.
        import urllib.request
        import urllib.error

        preflight_domains = [
            ("huggingface.co", f"https://huggingface.co/api/models/{repo_id}"),
            ("cdn-lfs.huggingface.co", "https://cdn-lfs.huggingface.co"),
        ]
        for domain, url in preflight_domains:
            try:
                req = urllib.request.Request(url, method="HEAD")
                urllib.request.urlopen(req, timeout=15)
            except urllib.error.HTTPError:
                # HTTP errors (403, 404) mean the server is reachable — that's fine
                pass
            except urllib.error.URLError as exc:
                reason = str(exc.reason) if hasattr(exc, "reason") else str(exc)
                if "getaddrinfo" in reason.lower() or "name or service" in reason.lower():
                    detail = (
                        f"Cannot resolve {domain} — check your internet connection. "
                        f"If you are behind a firewall, allow outbound HTTPS (port 443) "
                        f"for huggingface.co and cdn-lfs.huggingface.co."
                    )
                elif "timed out" in reason.lower():
                    detail = (
                        f"Connection to {domain} timed out. "
                        f"This is often caused by a firewall or proxy blocking HTTPS. "
                        f"Allow outbound port 443 for huggingface.co and "
                        f"cdn-lfs.huggingface.co in your Windows Firewall settings."
                    )
                elif "certificate" in reason.lower() or "ssl" in reason.lower():
                    detail = (
                        f"SSL/certificate error connecting to {domain}. "
                        f"If you use a corporate proxy, its CA certificate may need "
                        f"to be trusted by Python. Try setting the REQUESTS_CA_BUNDLE "
                        f"environment variable to your proxy's CA bundle."
                    )
                else:
                    detail = f"Cannot reach {domain}: {reason}"
                logger.warning("Pre-flight failed for %s (%s): %s", model_id, domain, detail)
                yield {"status": "error", "detail": detail}
                self._active_downloads.pop(model_id, None)
                return
            except Exception as exc:
                logger.warning("Pre-flight error for %s (%s): %s", model_id, domain, exc)
                # Non-fatal — proceed anyway
                pass

        yield {
            "status": "connecting",
            "model_id": model_id,
            "detail": "Connected to HuggingFace, starting download...",
        }

        # Thread-safe queue for progress updates from the blocking download
        progress_queue: _queue.Queue = _queue.Queue()

        try:
            loop = asyncio.get_event_loop()
            download_future = loop.run_in_executor(
                None,
                self._download_with_progress,
                repo_id, filename, dest_path, model_id, progress_queue,
            )

            # Poll progress queue while download runs
            last_progress_time = time.time()
            got_first_progress = False
            while not download_future.done():
                await asyncio.sleep(0.3)
                # Drain all queued progress updates
                drained_any = False
                while True:
                    try:
                        update = progress_queue.get_nowait()
                        yield update
                        drained_any = True
                        got_first_progress = True
                    except _queue.Empty:
                        break
                if drained_any:
                    last_progress_time = time.time()
                # If no progress for 60s and we never got any, the download is likely blocked
                elif not got_first_progress and (time.time() - last_progress_time) > 60:
                    logger.warning("Download stalled for %s — no progress after 60s", model_id)
                    yield {
                        "status": "error",
                        "detail": (
                            "Download appears stalled — no data received for 60 seconds. "
                            "This is usually caused by a firewall or proxy blocking "
                            "downloads from cdn-lfs.huggingface.co. Check your "
                            "Windows Firewall outbound rules for port 443."
                        ),
                    }
                    self._active_downloads[model_id] = True  # signal cancellation
                    break

            # If stall detector fired, don't wait for the thread — it may hang
            if self._active_downloads.get(model_id):
                # Thread is still blocking in hf_hub_download; clean up partial file
                if os.path.isfile(dest_path):
                    try:
                        os.remove(dest_path)
                    except OSError:
                        pass
                # Don't call download_future.result() — it may never return
                return

            # Get final result
            result = download_future.result()

            # Drain remaining progress
            while True:
                try:
                    update = progress_queue.get_nowait()
                    yield update
                except _queue.Empty:
                    break

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
            logger.exception("Download failed: %s", model_id)
            yield {"status": "error", "detail": str(exc)}
        finally:
            self._active_downloads.pop(model_id, None)

    def _download_with_progress(
        self, repo_id: str, filename: str, dest_path: str, model_id: str,
        progress_queue=None,
    ) -> Dict[str, Any]:
        """Blocking download using huggingface_hub (runs in thread).

        If *progress_queue* is supplied, intermediate progress dicts are
        pushed so the async caller can yield them as SSE events.
        """
        try:
            from huggingface_hub import hf_hub_download

            # Set a connection timeout so downloads don't hang forever
            # if the CDN is unreachable after the pre-flight passed.
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")

            tqdm_cls = None
            if progress_queue is not None:
                tqdm_cls = self._make_progress_tqdm(progress_queue, model_id)

            downloaded_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=self.models_dir,
                local_dir_use_symlinks=False,
                tqdm_class=tqdm_cls,
            )

            size = os.path.getsize(downloaded_path)
            logger.info("Download complete: %s (%.2f GB)", downloaded_path, size / (1024**3))
            return {"path": downloaded_path, "size": size}

        except Exception as exc:
            logger.exception("HuggingFace download error")
            return {"error": str(exc)}

    @staticmethod
    def _make_progress_tqdm(progress_queue, model_id: str):
        """Create a tqdm-compatible class that pushes progress into a queue."""
        import tqdm as _tqdm

        class _QueueTqdm(_tqdm.tqdm):
            """Custom tqdm that reports progress via a thread-safe queue."""

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._last_reported = 0.0
                self._sent_initial = False

            def update(self, n=1):
                super().update(n)
                if self.total and self.total > 0:
                    # Emit 0% immediately so frontend switches from "Preparing" to progress bar
                    if not self._sent_initial:
                        self._sent_initial = True
                        total_mb = self.total / (1024 * 1024)
                        completed_mb = self.n / (1024 * 1024)
                        progress_queue.put({
                            "status": "downloading",
                            "model_id": model_id,
                            "completed": self.n,
                            "total": self.total,
                            "percent": round((self.n / self.total) * 100, 1),
                            "completed_mb": round(completed_mb, 1),
                            "total_mb": round(total_mb, 1),
                        })
                    percent = (self.n / self.total) * 100
                    # Throttle: only emit if progress changed by >= 0.5%
                    if percent - self._last_reported >= 0.5 or percent >= 100:
                        self._last_reported = percent
                        completed_mb = self.n / (1024 * 1024)
                        total_mb = self.total / (1024 * 1024)
                        progress_queue.put({
                            "status": "downloading",
                            "model_id": model_id,
                            "completed": self.n,
                            "total": self.total,
                            "percent": round(percent, 1),
                            "completed_mb": round(completed_mb, 1),
                            "total_mb": round(total_mb, 1),
                            "speed": self.format_dict.get("rate", 0),
                        })

        return _QueueTqdm

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
