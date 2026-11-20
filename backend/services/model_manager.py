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

DEFAULT_MODELS_DIR = os.getenv(
    "MODELS_DIR",
    os.path.join(os.path.expanduser("~"), ".contextuai-solo", "models"),
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

        from .local_model_seeder import _strip_vendor_prefix
        filename_to_catalog = {}
        for entry in LOCAL_MODEL_CATALOG:
            fn = entry["hf_filename"].lower()
            filename_to_catalog[fn] = entry
            stripped = _strip_vendor_prefix(fn)
            if stripped != fn:
                filename_to_catalog[stripped] = entry

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

            try:
                from services.enterprise_policy import resolve_expected_sha256
                expected_sha = resolve_expected_sha256(
                    model_id=info.get("id"),
                    filename=f.name,
                    catalog_entry=catalog_entry,
                )
                if expected_sha:
                    info["expected_sha256"] = expected_sha
            except Exception:
                pass

            installed.append(info)

        return installed

    def is_installed(self, model_id: str) -> bool:
        """Check if a catalog model is already downloaded (root or chat/ subdir).

        Also checks for files without vendor prefix (e.g. manually downloaded
        ``gemma-4-...`` matching catalog entry ``google_gemma-4-...``).
        """
        from .model_catalog import get_model
        from .local_model_seeder import _strip_vendor_prefix
        entry = get_model(model_id)
        if not entry:
            return False
        filename = entry["hf_filename"]
        stripped = _strip_vendor_prefix(filename)
        candidates = [filename] if stripped == filename else [filename, stripped]

        for name in candidates:
            # For sharded files, check if the first shard exists
            if self._is_sharded_filename(name):
                if (Path(self.models_dir) / name).exists() or (Path(self.models_dir) / "chat" / name).exists():
                    return True
            else:
                if (Path(self.models_dir) / name).exists() or (Path(self.models_dir) / "chat" / name).exists():
                    return True
        return False

    def get_model_path(self, model_id: str) -> Optional[str]:
        """Get the local path for an installed model (checks root and chat/).

        Also checks for files without vendor prefix.
        """
        from .model_catalog import get_model
        from .local_model_seeder import _strip_vendor_prefix
        entry = get_model(model_id)
        if not entry:
            return None
        filename = entry["hf_filename"]
        stripped = _strip_vendor_prefix(filename)
        candidates = [filename] if stripped == filename else [filename, stripped]
        for name in candidates:
            for search_dir in [Path(self.models_dir), Path(self.models_dir) / "chat"]:
                path = search_dir / name
                if path.exists():
                    return str(path)
        return None

    # ── Download ────────────────────────────────────────────────────────────

    async def download_model(
        self, model_id: str, hf_token: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download a GGUF model from HuggingFace. Yields SSE progress dicts."""
        from .model_catalog import get_model

        entry = get_model(model_id)
        if not entry:
            yield {"status": "error", "detail": f"Model '{model_id}' not found in catalog"}
            return

        repo_id = entry.get("hf_repo") or "enterprise"
        filename = entry["hf_filename"]
        download_url = (entry.get("download_url") or "").strip() or None
        dest_path = os.path.join(self.models_dir, filename)

        if os.path.isfile(dest_path):
            try:
                from services.enterprise_policy import (
                    ModelIntegrityError,
                    resolve_expected_sha256,
                    verify_gguf_sha256,
                )
                expected_sha = resolve_expected_sha256(
                    model_id=model_id, filename=filename, catalog_entry=entry
                )
                verify_gguf_sha256(dest_path, expected_sha)
            except ModelIntegrityError as exc:
                try:
                    os.unlink(dest_path)
                except OSError:
                    pass
                self._audit_integrity_failed(model_id, dest_path, str(exc), expected_sha)
                yield {"status": "error", "detail": str(exc)}
                return
            except Exception:
                pass

            size = os.path.getsize(dest_path)
            logger.info("Model %s already exists at %s (%.2f GB)", model_id, dest_path, size / (1024**3))
            yield {
                "status": "done",
                "path": dest_path,
                "completed": size,
                "total": size,
                "percent": 100.0,
                "already_exists": True,
            }
            return

        egress_target = download_url or f"https://huggingface.co/{repo_id}"
        if egress_target.startswith(("http://", "https://")):
            try:
                from services.net_guard import assert_egress_allowed
                assert_egress_allowed(egress_target, "model_download")
            except ImportError:
                pass
            except Exception as exc:
                yield {"status": "error", "detail": str(exc)}
                return

        if model_id in self._active_downloads:
            yield {"status": "error", "detail": "This model is already downloading."}
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

        # ── Pre-flight: verify download source is reachable ──────────────
        if not download_url or download_url.startswith(("http://", "https://")):
            import urllib.request
            import urllib.error

            preflight_url = download_url or f"https://huggingface.co/api/models/{repo_id}"
            try:
                req = urllib.request.Request(preflight_url, method="HEAD")
                if not download_url:
                    effective_token = hf_token or os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
                    if effective_token:
                        req.add_header("Authorization", f"Bearer {effective_token}")
                urllib.request.urlopen(req, timeout=15)
                logger.info("Pre-flight OK for %s", model_id)
            except urllib.error.HTTPError:
                pass  # HTTP errors mean the server is reachable
            except (urllib.error.URLError, OSError) as exc:
                host_label = preflight_url if download_url else "huggingface.co"
                reason = str(getattr(exc, "reason", exc))
                if "getaddrinfo" in reason.lower() or "name or service" in reason.lower():
                    detail = f"Cannot reach {host_label} — please check your internet connection."
                elif "timed out" in reason.lower():
                    detail = f"Connection to {host_label} timed out. Please check your connection and try again."
                elif "certificate" in reason.lower() or "ssl" in reason.lower():
                    detail = (
                        f"SSL error connecting to {host_label}. If you use a corporate "
                        "proxy or VPN, it may be interfering with secure connections."
                    )
                else:
                    detail = f"Cannot reach {host_label}: {reason}"
                logger.warning("Pre-flight failed for %s: %s", model_id, detail)
                yield {"status": "error", "detail": detail}
                self._active_downloads.pop(model_id, None)
                return
            except Exception as exc:
                logger.warning("Pre-flight error for %s: %s", model_id, exc)

        yield {
            "status": "connecting",
            "model_id": model_id,
            "detail": (
                f"Connected to {download_url}, starting download..."
                if download_url
                else "Connected to HuggingFace, starting download..."
            ),
        }

        try:
            async for event in self._run_and_stream(
                repo_id, filename, model_id, dest_path, hf_token=hf_token, download_url=download_url
            ):
                yield event
        except Exception as exc:
            logger.exception("Download failed: %s", model_id)
            yield {"status": "error", "detail": str(exc)}

    @staticmethod
    def _is_sharded_filename(filename: str) -> bool:
        """Check if a filename is a sharded GGUF (e.g. model-00001-of-00003.gguf)."""
        import re
        return bool(re.search(r'-\d{5}-of-\d{5}\.gguf$', filename))

    @staticmethod
    def _shard_pattern(filename: str) -> str:
        """Convert a shard filename to a glob pattern matching all shards.

        e.g. 'model-00001-of-00003.gguf' -> 'model-*-of-*.gguf'
        """
        import re
        return re.sub(r'-\d{5}-of-\d{5}\.gguf$', '-*-of-*.gguf', filename)

    @staticmethod
    def _audit_integrity_failed(
        model_id: str, path: str, reason: str, expected_sha256: Optional[str] = None
    ) -> None:
        try:
            from models.audit_models import AuditAction, AuditSeverity
            from services.audit_service import audit_log_sync
            audit_log_sync(
                getattr(AuditAction, "MODEL_INTEGRITY_FAILED", "model.integrity_failed"),
                resource_type="model",
                resource_id=model_id,
                details={
                    "path": path,
                    "expected_sha256": expected_sha256,
                    "reason": reason,
                },
                severity=AuditSeverity.ERROR,
            )
        except Exception:
            pass

    @staticmethod
    def _audit_model_downloaded(
        model_id: str,
        path: str,
        size_bytes: int,
        sha256: Optional[str],
        verified: bool,
        source_url: str,
    ) -> None:
        try:
            from models.audit_models import AuditAction, AuditSeverity
            from services.audit_service import audit_log_sync
            audit_log_sync(
                getattr(AuditAction, "MODEL_DOWNLOADED", "model.downloaded"),
                resource_type="model",
                resource_id=model_id,
                details={
                    "path": path,
                    "size_bytes": size_bytes,
                    "sha256": sha256,
                    "verified": verified,
                    "source_url": source_url,
                },
                severity=AuditSeverity.INFO,
            )
        except Exception:
            pass

    async def _run_and_stream(
        self,
        repo_id: str,
        filename: str,
        model_id: str,
        dest_path: str,
        hf_token: Optional[str] = None,
        download_url: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the blocking downloader in a thread and yield its progress events."""
        import queue as _queue

        progress_queue: _queue.Queue = _queue.Queue()
        loop = asyncio.get_event_loop()
        download_future = loop.run_in_executor(
            None,
            self._download_files,
            repo_id, filename, model_id, progress_queue, hf_token, download_url,
        )
        # The worker checks the cancel flag between chunks, so it always
        # terminates; clear its slot whenever it does (including after the
        # SSE client disconnects and this generator is gone).
        download_future.add_done_callback(
            lambda _f: self._active_downloads.pop(model_id, None)
        )

        while not download_future.done():
            await asyncio.sleep(0.3)
            while True:
                try:
                    yield progress_queue.get_nowait()
                except _queue.Empty:
                    break

        # Drain remaining progress
        while True:
            try:
                yield progress_queue.get_nowait()
            except _queue.Empty:
                break

        result = download_future.result()
        if result.get("cancelled"):
            yield {"status": "cancelled", "model_id": model_id}
        elif result.get("error"):
            yield {"status": "error", "detail": result["error"]}
        else:
            yield {
                "status": "done",
                "path": result.get("path", dest_path),
                "completed": result.get("size", 0),
                "total": result.get("size", 0),
                "percent": 100.0,
            }

    def _download_files(
        self,
        repo_id: str,
        filename: str,
        model_id: str,
        progress_queue,
        hf_token: Optional[str] = None,
        download_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Blocking download via plain HTTPS GET from enterprise mirror or HuggingFace (runs in thread).

        Deliberately avoids hf_hub_download: plain ranged GETs work through
        corporate proxies/firewalls that break the Xet transfer protocol,
        resume from ``.part`` files, and honour cancellation between chunks.
        """
        import re
        import requests
        from urllib.parse import quote, unquote, urlparse
        from urllib.request import url2pathname

        try:
            entry = None
            try:
                from .model_catalog import get_model
                entry = get_model(model_id)
            except Exception:
                entry = None

            if not download_url and entry:
                download_url = (entry.get("download_url") or "").strip() or None

            egress_target = download_url or f"https://huggingface.co/{repo_id}"
            is_http_source = egress_target.startswith(("http://", "https://"))
            record_egress = None
            if is_http_source:
                try:
                    from services.net_guard import assert_egress_allowed, record_egress as _rec
                    assert_egress_allowed(egress_target, "model_download")
                    record_egress = _rec
                except ImportError:
                    record_egress = None
                except Exception as exc:
                    return {"error": str(exc)}

            if self._is_sharded_filename(filename):
                m = re.search(r"-(\d{5})-of-(\d{5})\.gguf$", filename)
                total_shards = int(m.group(2))
                base = re.sub(r"-\d{5}-of-\d{5}\.gguf$", "", filename)
                filenames = [
                    f"{base}-{i:05d}-of-{total_shards:05d}.gguf"
                    for i in range(1, total_shards + 1)
                ]
            else:
                filenames = [filename]

            # Check if catalog entry specifies a paired multimodal projector (mmproj)
            mmproj_fn = entry.get("mmproj_filename") if entry else None
            if mmproj_fn and mmproj_fn not in filenames:
                filenames.append(mmproj_fn)

            # Support local file:// URI or filesystem path for air-gapped enterprise mirrors
            if download_url and not is_http_source:
                parsed_dl = urlparse(download_url)
                if parsed_dl.scheme == "file":
                    src_path = Path(url2pathname(unquote(parsed_dl.path or "")))
                else:
                    src_path = Path(download_url).expanduser()
                if not src_path.is_file():
                    return {"error": f"Model source file not found: {src_path}"}
                Path(self.models_dir).mkdir(parents=True, exist_ok=True)
                dest = os.path.join(self.models_dir, filename)
                shutil.copy2(src_path, dest)
                total_size = os.path.getsize(dest)
                downloaded_paths = [dest]
            else:
                session = requests.Session()
                parsed_target = urlparse(egress_target)
                is_hf_host = (parsed_target.hostname or "").lower().endswith("huggingface.co")
                token = (
                    (hf_token or "").strip()
                    or os.getenv("HF_TOKEN")
                    or os.getenv("HUGGING_FACE_HUB_TOKEN")
                )
                if token and is_hf_host:
                    session.headers["Authorization"] = f"Bearer {token}"

                # Resolve sizes up front for overall progress + disk-space check
                jobs = []  # (url, dest_path, size_or_None)
                for name in filenames:
                    if download_url and name == filename:
                        url = download_url
                    else:
                        url = f"https://huggingface.co/{repo_id}/resolve/main/{quote(name)}"
                    dest = os.path.join(self.models_dir, name)
                    size = None
                    try:
                        head = session.head(url, allow_redirects=True, timeout=30)
                        if head.status_code < 400:
                            size = int(head.headers.get("Content-Length") or 0) or None
                        elif head.status_code not in (405, 501):
                            err = self._friendly_http_error(head.status_code, url if download_url else repo_id)
                            if err:
                                return {"error": err}
                    except requests.RequestException:
                        pass  # let the GET below surface the real error
                    jobs.append((url, dest, size))

                total_bytes = sum(s for (_u, _d, s) in jobs if s) or None
                if total_bytes:
                    already = sum(
                        os.path.getsize(d + ".part")
                        for (_u, d, _s) in jobs
                        if os.path.isfile(d + ".part")
                    )
                    free = shutil.disk_usage(self.models_dir).free
                    if free < (total_bytes - already) + 1024 ** 3:
                        return {"error": (
                            f"Not enough disk space: this model needs "
                            f"{(total_bytes - already) / 1024 ** 3:.1f} GB plus 1 GB headroom, "
                            f"but only {free / 1024 ** 3:.1f} GB is free."
                        )}

                completed_offset = 0
                for url, dest, _size in jobs:
                    result = self._stream_one(
                        session, url, dest, model_id, progress_queue,
                        completed_offset, total_bytes,
                    )
                    if result.get("cancelled") or result.get("error"):
                        return result
                    completed_offset += result["size"]

                dest = jobs[0][1]
                downloaded_paths = [d for (_u, d, _s) in jobs]
                total_size = sum(os.path.getsize(d) for d in downloaded_paths)

            # Verify SHA-256 checksum against catalog entry / enterprise policy
            from services.enterprise_policy import (
                ModelIntegrityError,
                resolve_expected_sha256,
                verify_gguf_sha256,
            )
            expected_sha256 = resolve_expected_sha256(
                model_id=model_id,
                filename=filename,
                catalog_entry=entry,
            )
            try:
                verification = verify_gguf_sha256(dest, expected_sha256)
            except ModelIntegrityError as exc:
                for p in downloaded_paths:
                    try:
                        if os.path.isfile(p):
                            os.unlink(p)
                    except OSError:
                        pass
                self._audit_integrity_failed(model_id, dest, str(exc), expected_sha256)
                return {"error": str(exc)}

            if record_egress and is_http_source:
                record_egress(egress_target, "model_download", total_size)

            self._audit_model_downloaded(
                model_id=model_id,
                path=dest,
                size_bytes=total_size,
                sha256=verification.get("sha256"),
                verified=bool(verification.get("verified")),
                source_url=egress_target,
            )
            logger.info(
                "Download complete: %s (%d file(s), %.2f GB, sha256_verified=%s)",
                model_id, len(downloaded_paths), total_size / (1024 ** 3), verification.get("verified"),
            )
            return {
                "path": dest,
                "size": total_size,
                "sha256": verification.get("sha256"),
                "verified": verification.get("verified"),
            }
        except Exception as exc:
            logger.exception("Download error for %s", model_id)
            return {"error": self._friendly_exception(exc)}

    def _stream_one(
        self, session, url: str, dest: str, model_id: str, progress_queue,
        base_completed: int, overall_total: Optional[int],
    ) -> Dict[str, Any]:
        """Stream one file to ``dest`` with resume, cancellation, and progress."""
        import requests

        part_path = dest + ".part"
        resume_from = os.path.getsize(part_path) if os.path.isfile(part_path) else 0
        headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}

        with session.get(
            url, stream=True, headers=headers, timeout=(15, 60), allow_redirects=True
        ) as resp:
            if resp.status_code == 416:
                # The .part file already covers the full range — finalise it
                os.replace(part_path, dest)
                return {"size": os.path.getsize(dest)}
            if resume_from and resp.status_code == 200:
                resume_from = 0  # server ignored the Range header — restart
            if resp.status_code >= 400:
                err = self._friendly_http_error(resp.status_code, url)
                return {"error": err or f"HTTP {resp.status_code} from HuggingFace"}

            content_len = int(resp.headers.get("Content-Length") or 0)
            file_total = resume_from + content_len if content_len else None

            completed = resume_from
            last_emit = 0.0
            window_start = time.time()
            window_bytes = 0
            with open(part_path, "ab" if resume_from else "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if self._active_downloads.get(model_id):
                        logger.info("Download cancelled: %s", model_id)
                        return {"cancelled": True}  # keep .part for resume
                    if not chunk:
                        continue
                    fh.write(chunk)
                    completed += len(chunk)
                    window_bytes += len(chunk)

                    now = time.time()
                    if now - last_emit >= 0.3:
                        last_emit = now
                        total = overall_total or file_total
                        done_bytes = base_completed + completed
                        speed = window_bytes / max(now - window_start, 0.001)
                        window_start, window_bytes = now, 0
                        progress_queue.put({
                            "status": "downloading",
                            "model_id": model_id,
                            "completed": done_bytes,
                            "total": total or 0,
                            "percent": round(done_bytes / total * 100, 1) if total else 0.0,
                            "completed_mb": round(done_bytes / (1024 * 1024), 1),
                            "total_mb": round(total / (1024 * 1024), 1) if total else 0.0,
                            "speed": round(speed),
                        })

            if file_total and completed != file_total:
                return {"error": (
                    f"Download incomplete: received {completed / (1024 ** 2):.0f} MB of "
                    f"{file_total / (1024 ** 2):.0f} MB. Try again — it will resume "
                    "where it left off."
                )}
            os.replace(part_path, dest)
            return {"size": completed}

    @staticmethod
    def _friendly_http_error(status: int, context: str) -> Optional[str]:
        """Map an HTTP status from HuggingFace to an actionable message."""
        if status in (401, 403):
            return (
                "This model is gated on HuggingFace and requires authentication. "
                "Visit the model page on huggingface.co, accept the license, then "
                "add your HuggingFace access token in Settings → AI Providers "
                f"(or set HF_TOKEN). ({context})"
            )
        if status == 404:
            return (
                f"File not found on HuggingFace ({context}). The repo or filename "
                "may have been renamed — try updating the app."
            )
        if status == 429:
            return (
                "HuggingFace is rate-limiting anonymous downloads from your network. "
                "Add a free HuggingFace access token in Settings → AI Providers "
                "(or set HF_TOKEN) for higher download limits."
            )
        if status >= 500:
            return f"HuggingFace server error (HTTP {status}). Try again in a few minutes."
        return None

    @staticmethod
    def _friendly_exception(exc: Exception) -> str:
        """Map a network exception to an actionable message."""
        import requests

        if isinstance(exc, requests.exceptions.SSLError):
            return (
                "SSL error connecting to HuggingFace. A corporate proxy, VPN, or "
                "antivirus is likely intercepting secure connections. If your IT "
                "department provides a CA certificate, set the REQUESTS_CA_BUNDLE "
                "environment variable to its path and restart the app."
            )
        if isinstance(exc, requests.exceptions.Timeout):
            return (
                "The download stalled — no data received. Check your connection "
                "and try again; the download will resume where it left off."
            )
        if isinstance(exc, requests.exceptions.ConnectionError):
            return (
                "Cannot reach HuggingFace download servers. Check your internet "
                "connection, and make sure your firewall allows huggingface.co "
                "and cdn-lfs.huggingface.co on port 443."
            )
        return str(exc)

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

        model_path = self.get_model_path(model_id)
        if not model_path:
            return {"status": "error", "detail": f"Model '{model_id}' is not installed"}
        path = Path(model_path)

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

    # ── Custom model download & local import ────────────────────────────────

    async def download_custom(
        self, hf_repo: str, hf_filename: str, hf_token: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Download any GGUF file from HuggingFace by repo + filename."""
        dest_path = os.path.join(self.models_dir, hf_filename)

        if os.path.isfile(dest_path):
            size = os.path.getsize(dest_path)
            yield {"status": "done", "path": dest_path, "completed": size, "total": size, "percent": 100.0}
            return

        try:
            from services.net_guard import assert_egress_allowed
            assert_egress_allowed(f"https://huggingface.co/{hf_repo}", "model_download")
        except ImportError:
            pass
        except Exception as exc:
            yield {"status": "error", "detail": str(exc)}
            return

        model_id = f"custom:{hf_repo}/{hf_filename}"
        if model_id in self._active_downloads:
            yield {"status": "error", "detail": "This file is already downloading."}
            return
        self._active_downloads[model_id] = False

        yield {"status": "starting", "repo": hf_repo, "filename": hf_filename, "completed": 0, "total": 0, "percent": 0.0}

        try:
            async for event in self._run_and_stream(
                hf_repo, hf_filename, model_id, dest_path, hf_token=hf_token
            ):
                yield event
        except Exception as exc:
            yield {"status": "error", "detail": str(exc)}

    def import_local_gguf(
        self, source_path: str, copy_file: bool = False
    ) -> Dict[str, Any]:
        """Import an existing local .gguf file into the models directory (SPEC-08).

        Validates that the file exists, has a ``.gguf`` extension, and starts with
        the ``GGUF`` magic bytes. Attempts a symlink/hardlink by default (unless
        ``copy_file=True``), falling back to ``shutil.copy2`` on Windows when
        symlinks are not permitted.
        """
        if not source_path or not isinstance(source_path, str):
            raise ValueError("source_path is required")

        src = Path(source_path).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"GGUF file not found: {source_path}")

        if src.suffix.lower() != ".gguf":
            raise ValueError(f"File must have a .gguf extension (got {src.name!r})")

        with open(src, "rb") as fh:
            magic = fh.read(4)
        if magic != b"GGUF":
            raise ValueError(
                f"File {src.name!r} is not a valid GGUF binary (invalid magic header)"
            )

        Path(self.models_dir).mkdir(parents=True, exist_ok=True)
        dest = Path(self.models_dir) / src.name
        method = "existing"

        if dest.resolve() != src:
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            if copy_file:
                shutil.copy2(src, dest)
                method = "copied"
            else:
                try:
                    os.symlink(src, dest)
                    method = "symlinked"
                except OSError:
                    try:
                        os.link(src, dest)
                        method = "hardlinked"
                    except OSError:
                        shutil.copy2(src, dest)
                        method = "copied"

        size_bytes = dest.stat().st_size
        stem = dest.stem.lower().replace(" ", "-")
        return {
            "status": "imported",
            "id": f"local:custom-{stem}",
            "filename": dest.name,
            "path": str(dest),
            "size_gb": round(size_bytes / (1024 ** 3), 2),
            "method": method,
        }


# ── Singleton ───────────────────────────────────────────────────────────────

model_manager = ModelManager()
