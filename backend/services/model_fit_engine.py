"""
Per-Quant Model Fit & Dynamic Context Engine (SPEC-27 & SPEC-15).

Classifies whether any GGUF model (catalog entry or raw HF file) fits in the
user's GPU VRAM or system RAM, estimates generation speed (tok/s), computes
the optimal dynamic context window (4096 to 65536), and picks the best model
for the machine.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.hardware import get_hardware_profile

logger = logging.getLogger(__name__)

_CONTEXT_TIERS = [4096, 8192, 16384, 32768, 65536]

_QUALITY_ORDER = {
    "basic": 1,
    "good": 2,
    "great": 3,
    "best": 4,
}


def _compute_recommended_n_ctx(
    free_mem_gb: float,
    model_max_ctx: int = 32768,
) -> int:
    """Choose the largest power-of-two context (4096..65536) that fits safely in free memory."""
    # Rough rule: ~0.5 GB KV cache per 8K context on Q8/FP16 for typical 7B-14B models
    if free_mem_gb >= 12.0:
        target = 65536
    elif free_mem_gb >= 6.0:
        target = 32768
    elif free_mem_gb >= 3.0:
        target = 16384
    elif free_mem_gb >= 1.5:
        target = 8192
    else:
        target = 4096

    capped = min(target, max(4096, model_max_ctx or 32768))
    best = 4096
    for tier in _CONTEXT_TIERS:
        if tier <= capped:
            best = tier
    return best


def classify_model_fit(
    model_entry: Dict[str, Any],
    hardware_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Classify how well ``model_entry`` fits on ``hardware_profile`` (SPEC-27).

    Returns a dict with:
    - ``verdict``: ``"fits_gpu"`` | ``"partial_offload"`` | ``"wont_fit"``
    - ``badge_label``: human-friendly badge string
    - ``estimated_tps``: estimated generation tokens/sec
    - ``recommended_n_ctx``: 4096..65536
    - ``reason``: plain-English explanation
    """
    hw = hardware_profile or get_hardware_profile()
    total_ram_gb = float(hw.get("total_ram_gb") or 8.0)
    gpu_vram_gb = float(hw.get("gpu_vram_gb") or 0.0)
    has_gpu = bool(hw.get("has_gpu", gpu_vram_gb > 0) and gpu_vram_gb > 0)
    unified_memory = bool(hw.get("unified_memory") or hw.get("apple_unified_memory"))
    est_bw_gbs = float(hw.get("estimated_bandwidth_gbs") or (250.0 if has_gpu else 45.0))

    size_gb = float(model_entry.get("size_gb") or 0.0)
    if size_gb <= 0:
        ram_req = float(model_entry.get("ram_required_gb") or 4.0)
        size_gb = round(ram_req * 0.75, 2)

    ram_required_gb = float(
        model_entry.get("ram_required_gb") or max(1.0, round(size_gb * 1.25, 1))
    )
    model_max_ctx = int(model_entry.get("context_window") or 32768)

    # Overhead for KV cache + runtime buffers (~1.2 GB minimum or 15% of weights)
    kv_overhead_gb = max(0.8, round(size_gb * 0.18, 2))
    needed_vram_gb = round(size_gb + kv_overhead_gb, 2)

    # Case 1: Fits completely inside GPU VRAM (or Apple Silicon unified memory budget)
    if has_gpu and gpu_vram_gb >= needed_vram_gb:
        free_vram = max(0.0, gpu_vram_gb - size_gb)
        rec_ctx = _compute_recommended_n_ctx(free_vram, model_max_ctx)
        raw_tps = (est_bw_gbs / max(size_gb, 0.4)) * 0.55
        est_tps = int(max(12, min(180, round(raw_tps))))
        gpu_label = "Unified Memory" if unified_memory else f"{gpu_vram_gb:.0f}GB VRAM"
        return {
            "verdict": "fits_gpu",
            "badge_label": f"Runs Fast in GPU (~{est_tps} tok/s)",
            "estimated_tps": est_tps,
            "recommended_n_ctx": rec_ctx,
            "reason": (
                f"Model weights ({size_gb:.1f} GB) fit completely in {gpu_label} "
                f"with {free_vram:.1f} GB headroom for a {rec_ctx:,}-token context window."
            ),
        }

    # Case 2: Doesn't fit in total system RAM at all
    # Allow slight tolerance: usable system RAM is ~total_ram_gb - 1.5 GB OS reserve
    usable_system_ram_gb = max(1.0, total_ram_gb - 1.5)
    if size_gb > usable_system_ram_gb and ram_required_gb > total_ram_gb:
        return {
            "verdict": "wont_fit",
            "badge_label": f"Won't Fit (Needs ~{ram_required_gb:.0f} GB RAM)",
            "estimated_tps": 0,
            "recommended_n_ctx": 4096,
            "reason": (
                f"Needs ~{ram_required_gb:.0f} GB memory ({size_gb:.1f} GB weights), "
                f"but your system has {total_ram_gb:.0f} GB total RAM."
            ),
        }

    # Case 3: Fits in system RAM (CPU inference or partial GPU+CPU offload)
    free_ram = max(0.0, usable_system_ram_gb - size_gb)
    rec_ctx = _compute_recommended_n_ctx(free_ram, min(model_max_ctx, 32768))
    cpu_bw = 55.0 if has_gpu else 42.0
    raw_tps = (cpu_bw / max(size_gb, 0.5)) * 0.5
    est_tps = int(max(3, min(45, round(raw_tps))))
    mode_desc = "Partial GPU Offload" if has_gpu else "CPU Mode"
    return {
        "verdict": "partial_offload",
        "badge_label": f"{mode_desc} (~{est_tps} tok/s)",
        "estimated_tps": est_tps,
        "recommended_n_ctx": rec_ctx,
        "reason": (
            f"Fits in {total_ram_gb:.0f} GB system RAM ({mode_desc.lower()}). "
            f"Recommended context window: {rec_ctx:,} tokens."
        ),
    }


def select_best_model_for_machine(
    catalog: List[Dict[str, Any]],
    hardware_profile: Optional[Dict[str, Any]] = None,
    category: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Select the single best model from ``catalog`` for ``hardware_profile`` (SPEC-27)."""
    if not catalog:
        return None

    hw = hardware_profile or get_hardware_profile()
    candidates: List[Dict[str, Any]] = []

    for entry in catalog:
        if category and category not in (entry.get("categories") or []):
            continue
        fit = classify_model_fit(entry, hw)
        if fit["verdict"] == "wont_fit":
            continue
        enriched = dict(entry)
        enriched["fit"] = fit
        candidates.append(enriched)

    if not candidates:
        return None

    def _score(m: Dict[str, Any]):
        fit = m["fit"]
        is_gpu = 1 if fit["verdict"] == "fits_gpu" else 0
        # Prefer models with strong tool + reasoning support that run at >= 18 tok/s
        fast_enough = 1 if fit["estimated_tps"] >= 18 else 0
        quality = _QUALITY_ORDER.get(m.get("quality_tier", "good"), 2)
        rec_flag = 1 if m.get("recommended") else 0
        tools_flag = 1 if m.get("supports_tools") else 0
        params = float(m.get("parameter_count") or 0.0)
        return (is_gpu, fast_enough, quality, tools_flag, rec_flag, params)

    candidates.sort(key=_score, reverse=True)
    return candidates[0]
