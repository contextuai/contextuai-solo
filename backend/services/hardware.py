"""
Pure-Local Hardware X-Ray Probe (SPEC-27).

Detects CPU architecture/cores/SIMD (AVX2, NEON), system RAM, and GPUs across:
- NVIDIA (via nvidia-smi)
- Apple Silicon Unified Memory (via sysctl on macOS arm64)
- AMD Radeon & Intel Arc on Windows (via PowerShell CIM Win32_VideoController / wmic)
- AMD & Intel GPUs on Linux (via /sys/class/drm)

Makes zero network calls and caches the hardware profile in memory.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CACHED_PROFILE: Optional[Dict[str, Any]] = None


def clear_hardware_cache() -> None:
    """Clear the cached hardware profile."""
    global _CACHED_PROFILE
    _CACHED_PROFILE = None


def _detect_cpu() -> Dict[str, Any]:
    os_name = platform.system().lower()
    arch = (platform.machine() or "unknown").lower()
    logical_cores = os.cpu_count() or 4
    physical_cores = logical_cores

    try:
        import psutil
        phys = psutil.cpu_count(logical=False)
        if phys:
            physical_cores = phys
    except Exception:
        pass

    is_arm = "arm" in arch or "aarch64" in arch
    has_neon = is_arm
    has_avx2 = not is_arm and ("x86_64" in arch or "amd64" in arch)
    brand = platform.processor() or arch

    if os_name == "darwin":
        try:
            res = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=3,
            )
            if res.returncode == 0 and res.stdout.strip():
                brand = res.stdout.strip()
        except Exception:
            pass
    elif os_name == "linux":
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text(errors="ignore")
            for line in cpuinfo.splitlines():
                if line.lower().startswith("model name") and ":" in line:
                    brand = line.split(":", 1)[1].strip()
                    break
            has_avx2 = "avx2" in cpuinfo.lower()
        except Exception:
            pass

    return {
        "brand": brand,
        "arch": arch,
        "physical_cores": physical_cores,
        "logical_cores": logical_cores,
        "has_avx2": has_avx2,
        "has_neon": has_neon,
    }


def _detect_ram() -> Dict[str, float]:
    try:
        import psutil
        vm = psutil.virtual_memory()
        total_gb = round(vm.total / (1024 ** 3), 1)
        available_gb = round(vm.available / (1024 ** 3), 1)
        return {"total_ram_gb": total_gb, "available_ram_gb": available_gb}
    except Exception:
        return {"total_ram_gb": 8.0, "available_ram_gb": 4.0}


def _detect_nvidia_gpus() -> List[Dict[str, Any]]:
    gpus: List[Dict[str, Any]] = []
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if not parts or not parts[0]:
                    continue
                name = parts[0]
                vram_mb = float(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0.0
                free_mb = float(parts[2]) if len(parts) > 2 and parts[2].isdigit() else vram_mb
                gpus.append({
                    "name": name,
                    "vendor": "nvidia",
                    "vram_gb": round(vram_mb / 1024.0, 1),
                    "free_vram_gb": round(free_mb / 1024.0, 1),
                    "backend": "cuda",
                    "unified_memory": False,
                })
    except Exception:
        pass
    return gpus


def _detect_apple_silicon_gpu(total_ram_gb: float, available_ram_gb: float) -> List[Dict[str, Any]]:
    if platform.system().lower() != "darwin":
        return []
    arch = (platform.machine() or "").lower()
    if "arm" not in arch and "aarch64" not in arch:
        return []

    chip_name = "Apple Silicon GPU"
    try:
        res = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=3,
        )
        if res.returncode == 0 and res.stdout.strip():
            chip_name = f"{res.stdout.strip()} (Unified Memory)"
    except Exception:
        pass

    # macOS Metal allows ~75% of unified memory for GPU allocation by default
    usable_vram = round(total_ram_gb * 0.75, 1)
    free_vram = round(min(usable_vram, available_ram_gb), 1)
    return [{
        "name": chip_name,
        "vendor": "apple",
        "vram_gb": usable_vram,
        "free_vram_gb": free_vram,
        "backend": "metal",
        "unified_memory": True,
    }]


def _detect_windows_cim_gpus() -> List[Dict[str, Any]]:
    if platform.system().lower() != "windows":
        return []
    gpus: List[Dict[str, Any]] = []
    try:
        ps_cmd = (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name, AdapterRAM | ConvertTo-Json -Compress"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            raw = json.loads(res.stdout.strip())
            items = raw if isinstance(raw, list) else [raw]
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("Name") or "").strip()
                if not name:
                    continue
                low = name.lower()
                # Skip virtual/remote display adapters
                if any(s in low for s in ("basic display", "parsec", "virtual", "remote")):
                    continue
                # Skip NVIDIA here if already found via nvidia-smi
                if "nvidia" in low:
                    vendor = "nvidia"
                    backend = "cuda"
                elif "amd" in low or "radeon" in low:
                    vendor = "amd"
                    backend = "vulkan"
                elif "intel" in low or "arc" in low or "iris" in low:
                    vendor = "intel"
                    backend = "vulkan"
                else:
                    vendor = "unknown"
                    backend = "vulkan"

                adapter_ram = item.get("AdapterRAM") or 0
                try:
                    vram_gb = round(int(adapter_ram) / (1024 ** 3), 1)
                except (ValueError, TypeError):
                    vram_gb = 0.0

                gpus.append({
                    "name": name,
                    "vendor": vendor,
                    "vram_gb": vram_gb,
                    "free_vram_gb": vram_gb,
                    "backend": backend,
                    "unified_memory": False,
                })
    except Exception:
        pass
    return gpus


def _detect_linux_drm_gpus() -> List[Dict[str, Any]]:
    if platform.system().lower() != "linux":
        return []
    gpus: List[Dict[str, Any]] = []
    drm_root = Path("/sys/class/drm")
    if not drm_root.exists():
        return gpus

    try:
        for card_dir in sorted(drm_root.glob("card[0-9]*")):
            if "-" in card_dir.name:
                continue
            dev_dir = card_dir / "device"
            vram_file = dev_dir / "mem_info_vram_total"
            if vram_file.exists():
                try:
                    vram_bytes = int(vram_file.read_text().strip())
                    vram_gb = round(vram_bytes / (1024 ** 3), 1)
                except Exception:
                    vram_gb = 0.0
                gpus.append({
                    "name": f"AMD/DRM GPU ({card_dir.name})",
                    "vendor": "amd",
                    "vram_gb": vram_gb,
                    "free_vram_gb": vram_gb,
                    "backend": "vulkan",
                    "unified_memory": False,
                })
    except Exception:
        pass
    return gpus


def get_hardware_profile(rescan: bool = False) -> Dict[str, Any]:
    """Return a structured hardware profile for this machine (SPEC-27)."""
    global _CACHED_PROFILE
    if _CACHED_PROFILE is not None and not rescan:
        return dict(_CACHED_PROFILE)

    cpu = _detect_cpu()
    ram = _detect_ram()
    total_ram_gb = ram["total_ram_gb"]
    available_ram_gb = ram["available_ram_gb"]

    gpus: List[Dict[str, Any]] = []
    apple_gpus = _detect_apple_silicon_gpu(total_ram_gb, available_ram_gb)
    if apple_gpus:
        gpus.extend(apple_gpus)
    else:
        nv_gpus = _detect_nvidia_gpus()
        gpus.extend(nv_gpus)
        has_nv = bool(nv_gpus)

        for win_gpu in _detect_windows_cim_gpus():
            if has_nv and win_gpu["vendor"] == "nvidia":
                continue
            gpus.append(win_gpu)

        for drm_gpu in _detect_linux_drm_gpus():
            gpus.append(drm_gpu)

    # Pick the primary GPU (highest VRAM)
    primary_gpu: Optional[Dict[str, Any]] = None
    if gpus:
        primary_gpu = max(gpus, key=lambda g: g.get("vram_gb") or 0.0)

    has_gpu = bool(primary_gpu and (primary_gpu.get("vram_gb") or 0) >= 2.0)
    gpu_vram_gb = primary_gpu["vram_gb"] if primary_gpu else 0.0
    unified_memory = bool(primary_gpu and primary_gpu.get("unified_memory"))
    recommended_backend = primary_gpu["backend"] if has_gpu and primary_gpu else "cpu"

    # Estimate memory bandwidth (GB/s) for coarse tok/s estimation
    if unified_memory:
        est_bw_gbs = 200.0 if total_ram_gb >= 32 else 100.0
    elif has_gpu and primary_gpu:
        if primary_gpu["vendor"] == "nvidia":
            est_bw_gbs = 500.0 if gpu_vram_gb >= 12 else 300.0
        else:
            est_bw_gbs = 250.0
    else:
        est_bw_gbs = 45.0

    # Determine hardware tier summary
    effective_mem = max(total_ram_gb, gpu_vram_gb)
    if effective_mem >= 48:
        tier = "workstation"
        max_recommended_params = "70B"
    elif effective_mem >= 24:
        tier = "enthusiast"
        max_recommended_params = "32B"
    elif effective_mem >= 16:
        tier = "performance"
        max_recommended_params = "14B"
    elif effective_mem >= 8:
        tier = "mainstream"
        max_recommended_params = "8B"
    else:
        tier = "entry"
        max_recommended_params = "3B"

    profile = {
        "os": platform.system().lower(),
        "arch": cpu["arch"],
        "cpu": cpu,
        "total_ram_gb": total_ram_gb,
        "available_ram_gb": available_ram_gb,
        "has_gpu": has_gpu,
        "gpu": primary_gpu["name"] if primary_gpu else None,
        "gpu_vendor": primary_gpu["vendor"] if primary_gpu else None,
        "gpu_vram_gb": gpu_vram_gb,
        "unified_memory": unified_memory,
        "gpus": gpus,
        "recommended_backend": recommended_backend,
        "estimated_bandwidth_gbs": est_bw_gbs,
        "hardware_tier": tier,
        "max_recommended_params": max_recommended_params,
        "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _CACHED_PROFILE = profile
    return dict(profile)
