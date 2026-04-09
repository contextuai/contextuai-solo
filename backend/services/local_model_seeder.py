"""
Local Model Seeder

Syncs installed GGUF models into MongoDB so they appear in ``/api/v1/models/``
and can be selected by Chat, Workspace, and Crews — just like any cloud model.

Called on desktop startup. Idempotent: adds new models, removes stale entries,
updates existing ones.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.expanduser("~"), ".contextuai-solo", "models")

# Vendor prefixes used by community quantisers (e.g. bartowski).
# When matching filenames, we strip these so "gemma-4-..." matches "google_gemma-4-...".
_VENDOR_PREFIXES = ("google_", "meta-llama_", "microsoft_", "qwen_", "mistralai_")


def _strip_vendor_prefix(filename: str) -> str:
    """Remove a known vendor prefix from a GGUF filename for fuzzy matching."""
    lower = filename.lower()
    for prefix in _VENDOR_PREFIXES:
        if lower.startswith(prefix):
            return filename[len(prefix):]
    return filename


async def sync_local_models_to_db(db) -> int:
    """
    Scan the models directory for GGUF files and upsert them into the
    ``models`` collection so the standard ``/api/v1/models/`` endpoint
    returns them.

    Returns the number of models synced.
    """
    from services.model_catalog import LOCAL_MODEL_CATALOG

    models_path = Path(MODELS_DIR)
    if not models_path.exists():
        models_path.mkdir(parents=True, exist_ok=True)
        return 0

    # Build filename → catalog lookup (exact match + stripped-prefix match)
    filename_to_catalog: Dict[str, Dict] = {}
    for entry in LOCAL_MODEL_CATALOG:
        fn = entry["hf_filename"].lower()
        filename_to_catalog[fn] = entry
        # Also index without vendor prefix (e.g. "google_gemma-4-..." → "gemma-4-...")
        # so manually downloaded files without the prefix still match.
        stripped = _strip_vendor_prefix(fn)
        if stripped != fn:
            filename_to_catalog[stripped] = entry

    collection = db["models"]

    # Find which GGUF files are on disk (check root and chat/ subdir)
    installed_ids: set = set()
    synced = 0

    gguf_files = list(models_path.glob("*.gguf"))
    chat_dir = models_path / "chat"
    if chat_dir.exists():
        gguf_files.extend(chat_dir.glob("*.gguf"))

    for f in gguf_files:
        catalog_entry = filename_to_catalog.get(f.name.lower())

        if catalog_entry:
            model_id = f"local:{catalog_entry['id']}"
            doc = _catalog_to_model_doc(catalog_entry, str(f))
        else:
            # Unknown GGUF — register as a custom local model
            stem = f.stem.lower().replace(" ", "-")
            model_id = f"local:custom-{stem}"
            doc = _unknown_gguf_to_model_doc(f)

        installed_ids.add(model_id)

        # Upsert: insert or update
        existing = await collection.find_one({"_id": model_id})
        if existing:
            await collection.find_one_and_update(
                {"_id": model_id},
                {"$set": doc},
            )
        else:
            doc["_id"] = model_id
            await collection.insert_one(doc)
            name = catalog_entry["name"] if catalog_entry else f.stem
            logger.info("Registered local model: %s (%s)", name, f.name)

        synced += 1

    # Remove stale entries (models deleted from disk or old format entries)
    # Check both new format (local:*) and legacy format (local-*)
    async for stale in collection.find({}):
        stale_id = stale.get("_id") or stale.get("id") or ""
        provider = (stale.get("provider") or "").lower()
        runtime = (stale.get("model_metadata", {}).get("runtime") or "").lower()
        is_local_entry = (
            provider == "local"
            or runtime in ("local", "llama-cpp")
            or str(stale_id).startswith("local-")
            or str(stale_id).startswith("local:")
        )
        if is_local_entry and stale_id not in installed_ids:
            await collection.delete_one({"_id": stale_id})
            logger.info("Removed stale local model: %s", stale_id)

    if synced:
        logger.info("Synced %d local models to database", synced)

    return synced


def _catalog_to_model_doc(entry: Dict, file_path: str) -> Dict[str, Any]:
    """Convert a catalog entry + file path into a MongoDB model document."""
    model_id = f"local:{entry['id']}"
    return {
        "id": model_id,
        "name": f"{entry['name']} (Local)",
        "provider": "Local",
        "model": f"local:{entry['id']}",
        "max_tokens": 4096,
        "enabled": True,
        "description": entry["description"],
        "capabilities": entry["categories"],
        "input_cost": 0,
        "output_cost": 0,
        "context_window": entry["context_window"],
        "supports_vision": entry.get("supports_vision", False),
        "supports_function_calling": entry.get("supports_tools", False),
        "model_metadata": {
            "runtime": "llama-cpp",
            "local_model_id": entry["id"],
            "gguf_path": file_path,
            "family": entry["family"],
            "parameter_size": entry["parameter_size"],
            "parameter_count": entry["parameter_count"],
            "quantization": entry["quantization"],
            "ram_required_gb": entry["ram_required_gb"],
            "chat_template": entry.get("chat_template", "chatml"),
            "hf_repo": entry["hf_repo"],
            "hf_filename": entry["hf_filename"],
        },
    }


def _unknown_gguf_to_model_doc(file_path: Path) -> Dict[str, Any]:
    """Create a model document for an unknown GGUF file not in the catalog."""
    stem = file_path.stem
    model_id = f"local:custom-{stem.lower().replace(' ', '-')}"
    size_gb = round(file_path.stat().st_size / (1024 ** 3), 2)
    return {
        "id": model_id,
        "name": f"{stem} (Local)",
        "provider": "Local",
        "model": model_id,
        "max_tokens": 4096,
        "enabled": True,
        "description": f"Custom local model: {file_path.name}",
        "capabilities": ["general"],
        "input_cost": 0,
        "output_cost": 0,
        "context_window": 4096,
        "supports_vision": False,
        "supports_function_calling": False,
        "model_metadata": {
            "runtime": "llama-cpp",
            "local_model_id": f"custom-{stem.lower().replace(' ', '-')}",
            "gguf_path": str(file_path),
            "family": "unknown",
            "parameter_size": "Unknown",
            "parameter_count": 0,
            "quantization": "Unknown",
            "ram_required_gb": max(1, round(size_gb * 1.2)),
            "chat_template": "chatml",
            "hf_repo": None,
            "hf_filename": file_path.name,
        },
    }


async def get_default_local_model_id(db) -> Optional[str]:
    """
    Return the model ID of the best installed local model, or None.

    Prefers larger models (higher parameter count).
    """
    collection = db["models"]
    local_models: List[Dict] = []

    async for doc in collection.find({"model_metadata.runtime": "llama-cpp", "enabled": True}):
        local_models.append(doc)

    if not local_models:
        return None

    local_models.sort(
        key=lambda m: m.get("model_metadata", {}).get("parameter_count", 0),
        reverse=True,
    )

    best = local_models[0]
    return best.get("id") or best.get("_id")
