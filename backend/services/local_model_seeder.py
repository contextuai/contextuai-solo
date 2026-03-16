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

    # Build filename → catalog lookup
    filename_to_catalog: Dict[str, Dict] = {}
    for entry in LOCAL_MODEL_CATALOG:
        filename_to_catalog[entry["hf_filename"].lower()] = entry

    collection = db["models"]

    # Find which GGUF files are on disk
    installed_ids: set = set()
    synced = 0

    for f in models_path.glob("*.gguf"):
        catalog_entry = filename_to_catalog.get(f.name.lower())
        if not catalog_entry:
            continue  # Unknown GGUF — skip

        model_id = f"local:{catalog_entry['id']}"
        installed_ids.add(model_id)

        doc = _catalog_to_model_doc(catalog_entry, str(f))

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
            logger.info("Registered local model: %s (%s)", catalog_entry["name"], f.name)

        synced += 1

    # Remove stale entries (models that were deleted from disk)
    async for stale in collection.find({"model_metadata.runtime": "llama-cpp"}):
        stale_id = stale.get("_id") or stale.get("id")
        if stale_id and stale_id not in installed_ids:
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
        "model": entry["id"],
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
