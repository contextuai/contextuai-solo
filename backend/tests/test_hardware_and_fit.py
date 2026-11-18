"""SPEC-27: Hardware X-Ray & Per-Quant Fit Engine tests."""
from services.hardware import get_hardware_profile, clear_hardware_cache
from services.model_fit_engine import (
    classify_model_fit,
    select_best_model_for_machine,
)


def test_get_hardware_profile_structure():
    clear_hardware_cache()
    profile = get_hardware_profile(rescan=True)
    assert "total_ram_gb" in profile
    assert "available_ram_gb" in profile
    assert "cpu" in profile
    assert profile["cpu"]["logical_cores"] >= 1
    assert "recommended_backend" in profile
    assert profile["total_ram_gb"] > 0


def test_classify_model_fit_across_hardware_tiers():
    model_7b = {
        "id": "qwen2.5-7b-instruct",
        "name": "Qwen 2.5 7B Instruct",
        "size_gb": 4.7,
        "quantization": "Q4_K_M",
        "context_window": 32768,
        "categories": ["general"],
        "quality_tier": "great",
        "is_recommended": True,
    }

    # 1. 16GB RAM + 8GB NVIDIA RTX GPU -> fits_gpu
    rtx_profile = {
        "total_ram_gb": 16.0,
        "available_ram_gb": 12.0,
        "gpu_vendor": "nvidia",
        "gpu_name": "NVIDIA GeForce RTX 4060",
        "gpu_vram_gb": 8.0,
        "apple_unified_memory": False,
        "avx2": True,
    }
    fit_gpu = classify_model_fit(model_7b, rtx_profile)
    assert fit_gpu["verdict"] == "fits_gpu"
    assert fit_gpu["estimated_tps"] >= 20
    assert fit_gpu["recommended_n_ctx"] >= 4096

    # 2. 16GB RAM CPU-only laptop -> partial_offload
    cpu_profile = {
        "total_ram_gb": 16.0,
        "available_ram_gb": 10.0,
        "gpu_vendor": None,
        "gpu_name": None,
        "gpu_vram_gb": None,
        "apple_unified_memory": False,
        "avx2": True,
    }
    fit_cpu = classify_model_fit(model_7b, cpu_profile)
    assert fit_cpu["verdict"] == "partial_offload"
    assert fit_cpu["recommended_n_ctx"] >= 4096

    # 3. 4GB RAM tiny machine -> wont_fit
    tiny_profile = {
        "total_ram_gb": 4.0,
        "available_ram_gb": 2.0,
        "gpu_vendor": None,
        "gpu_name": None,
        "gpu_vram_gb": None,
        "apple_unified_memory": False,
        "avx2": True,
    }
    fit_tiny = classify_model_fit(model_7b, tiny_profile)
    assert fit_tiny["verdict"] == "wont_fit"


def test_select_best_model_for_machine():
    catalog = [
        {
            "id": "small-1.5b",
            "name": "Small 1.5B",
            "size_gb": 1.1,
            "quantization": "Q4_K_M",
            "context_window": 32768,
            "categories": ["general"],
            "quality_tier": "good",
            "is_recommended": True,
        },
        {
            "id": "mid-7b",
            "name": "Mid 7B",
            "size_gb": 4.7,
            "quantization": "Q4_K_M",
            "context_window": 32768,
            "categories": ["general", "coding"],
            "quality_tier": "great",
            "is_recommended": True,
        },
        {
            "id": "huge-70b",
            "name": "Huge 70B",
            "size_gb": 42.0,
            "quantization": "Q4_K_M",
            "context_window": 32768,
            "categories": ["general"],
            "quality_tier": "best",
            "is_recommended": False,
        },
    ]
    rtx_8gb = {
        "total_ram_gb": 16.0,
        "available_ram_gb": 12.0,
        "gpu_vendor": "nvidia",
        "gpu_name": "RTX 4060",
        "gpu_vram_gb": 8.0,
        "apple_unified_memory": False,
        "avx2": True,
    }
    best = select_best_model_for_machine(catalog, rtx_8gb, category="general")
    assert best is not None
    assert best["id"] == "mid-7b"
    assert best["fit"]["verdict"] == "fits_gpu"
