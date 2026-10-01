"""Tests for the curated local model catalog and download filename fallback.

Pure-Python checks — no network, llama-cpp, or real GGUF files required.
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from services.model_catalog import (
    LOCAL_MODEL_CATALOG,
    MODEL_CATEGORIES,
    QUALITY_TIERS,
    RAM_CAP_GB,
    SPEED_TIERS,
    get_catalog,
    get_model,
    get_recommended,
)
from services.model_manager import ModelManager


REQUIRED_FIELDS = {
    "id", "name", "family", "provider", "parameter_size", "parameter_count",
    "size_gb", "ram_required_gb", "ram_recommended_gb", "categories",
    "description", "quantization", "context_window", "supports_vision",
    "supports_tools", "quality_tier", "speed_tier", "hf_repo", "hf_filename",
    "chat_template", "released",
}


# ── Catalog integrity ──────────────────────────────────────────────────────

@pytest.mark.parametrize("entry", LOCAL_MODEL_CATALOG, ids=lambda e: e["id"])
def test_entry_is_well_formed(entry):
    assert REQUIRED_FIELDS <= entry.keys()
    assert entry["quality_tier"] in QUALITY_TIERS
    assert entry["speed_tier"] in SPEED_TIERS
    assert entry["categories"] and set(entry["categories"]) <= MODEL_CATEGORIES.keys()
    assert re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", entry["released"])
    assert entry["ram_required_gb"] <= entry["ram_recommended_gb"]
    assert entry["ram_required_gb"] <= RAM_CAP_GB
    assert entry["size_gb"] < entry["ram_required_gb"]
    assert entry["hf_filename"].endswith(".gguf")
    assert entry["hf_repo"].count("/") == 1
    if not entry.get("legacy"):
        # The pinned file must be the advertised quant — the download
        # fallback in model_manager matches replacement files on it too.
        assert entry["quantization"].lower() in entry["hf_filename"].lower()


def test_ids_and_filenames_are_unique():
    ids = [m["id"] for m in LOCAL_MODEL_CATALOG]
    filenames = [m["hf_filename"].lower() for m in LOCAL_MODEL_CATALOG]
    assert len(ids) == len(set(ids))
    assert len(filenames) == len(set(filenames))


def test_ids_stay_unique_under_openai_compat_fuzzy_matching():
    # routers/openai_compat._resolve_model strips "-", "." and spaces
    normalized = [re.sub(r"[-. ]", "", m["id"]) for m in LOCAL_MODEL_CATALOG]
    assert len(normalized) == len(set(normalized))


def test_catalog_has_current_models_at_every_size():
    current = [m for m in LOCAL_MODEL_CATALOG if not m.get("legacy")]
    for ram_gb in (4, 8, 16, 32):
        assert any(m["ram_required_gb"] <= ram_gb for m in current), ram_gb
    assert any("coding" in m["categories"] for m in current)


# ── Ordering / recommendations ─────────────────────────────────────────────

def test_get_catalog_lists_current_models_newest_first_then_legacy():
    models = get_catalog()
    flags = [bool(m.get("legacy")) for m in models]
    assert flags == sorted(flags), "legacy entries must come after current ones"

    current = [m["released"] for m in models if not m.get("legacy")]
    assert current == sorted(current, reverse=True)


def test_get_catalog_filters_by_ram_and_category():
    models = get_catalog(max_ram_gb=8, category="coding")
    assert models
    assert all(m["ram_required_gb"] <= 8 and "coding" in m["categories"] for m in models)


@pytest.mark.parametrize("ram_gb", [8, 16, 32, 64])
def test_get_recommended_prefers_current_generation(ram_gb):
    recommended = get_recommended(ram_gb, limit=5)
    assert len(recommended) == 5
    assert not any(m.get("legacy") for m in recommended)
    assert all(m["ram_required_gb"] <= ram_gb for m in recommended)


def test_get_recommended_falls_back_to_legacy_when_nothing_current_fits():
    recommended = get_recommended(1, limit=5)
    assert [m["id"] for m in recommended][0] == "qwen3.5-0.8b"
    assert any(m.get("legacy") for m in recommended)


def test_legacy_entries_stay_resolvable():
    # Installed legacy models must keep resolving for chat/dispatcher lookups
    assert get_model("qwen2.5-7b")["legacy"] is True
    assert get_model("qwen2.5-coder-7b") is not None


# ── Download filename fallback ─────────────────────────────────────────────

def _resolve_with_listing(files, filename="Qwen3.8-27B-Q4_K_M.gguf", quant="Q4_K_M"):
    api = MagicMock()
    api.list_repo_files.return_value = files
    with patch("huggingface_hub.HfApi", return_value=api):
        return ModelManager(models_dir="/tmp/unused")._resolve_repo_filename(
            "unsloth/Qwen3.8-27B-GGUF", filename, quant,
        )


def test_resolve_keeps_pinned_filename_when_present():
    files = ["Qwen3.8-27B-Q4_K_M.gguf", "Qwen3.8-27B-UD-Q4_K_M.gguf"]
    assert _resolve_with_listing(files) == "Qwen3.8-27B-Q4_K_M.gguf"


def test_resolve_falls_back_to_same_quant_when_pinned_file_deleted():
    files = [
        "README.md",
        "mmproj-F16.gguf",
        "Qwen3.8-27B-UD-Q4_K_XL.gguf",
        "Qwen3.8-27B-UD-Q4_K_M.gguf",
        "Qwen3.8-27B-Q5_K_M.gguf",
        "BF16/Qwen3.8-27B-BF16-00001-of-00002.gguf",
    ]
    assert _resolve_with_listing(files) == "Qwen3.8-27B-UD-Q4_K_M.gguf"


def test_resolve_returns_pinned_filename_when_no_same_quant_exists():
    files = ["Qwen3.8-27B-Q5_K_M.gguf", "Qwen3.8-27B-Q4_K_S.gguf"]
    assert _resolve_with_listing(files) == "Qwen3.8-27B-Q4_K_M.gguf"


def test_resolve_returns_pinned_filename_when_listing_fails():
    api = MagicMock()
    api.list_repo_files.side_effect = OSError("offline")
    with patch("huggingface_hub.HfApi", return_value=api):
        result = ModelManager(models_dir="/tmp/unused")._resolve_repo_filename(
            "bartowski/Qwen3.8-27B-GGUF", "Qwen3.8-27B-Q4_K_M.gguf", "Q4_K_M",
        )
    assert result == "Qwen3.8-27B-Q4_K_M.gguf"


def test_resolve_skips_listing_for_sharded_filenames():
    with patch("huggingface_hub.HfApi") as hf_api:
        result = ModelManager(models_dir="/tmp/unused")._resolve_repo_filename(
            "Qwen/Qwen2.5-14B-Instruct-GGUF",
            "qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf",
            "Q4_K_M",
        )
    hf_api.assert_not_called()
    assert result == "qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf"


def test_fallback_download_is_stored_under_catalog_filename(tmp_path):
    manager = ModelManager(models_dir=str(tmp_path))
    dest = tmp_path / "Qwen3.8-27B-Q4_K_M.gguf"

    def fake_download(repo_id, filename, local_dir, **kwargs):
        path = tmp_path / filename
        path.write_bytes(b"gguf")
        return str(path)

    with patch("huggingface_hub.hf_hub_download", side_effect=fake_download):
        result = manager._download_with_progress(
            "unsloth/Qwen3.8-27B-GGUF", "Qwen3.8-27B-UD-Q4_K_M.gguf", str(dest), "qwen3.8-27b",
        )

    assert result == {"path": str(dest), "size": 4}
    assert dest.exists()
    assert not (tmp_path / "Qwen3.8-27B-UD-Q4_K_M.gguf").exists()
