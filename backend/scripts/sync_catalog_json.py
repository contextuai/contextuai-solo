"""
Daily Living Model Catalog Updater (SPEC-34).

Queries HuggingFace Hub for newly trending verified GGUF repositories,
selects the sweet-spot Q4_K_M quant, and merges new entries into
`catalog/models.json` without overwriting hand-curated entries.

Usage (from repo root or backend/):
    python backend/scripts/sync_catalog_json.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "catalog" / "models.json"

VERIFIED_ORGS = (
    "qwen",
    "bartowski",
    "unsloth",
    "ggml-org",
    "lmstudio-community",
    "google",
    "mistralai",
)

FAMILY_LOGOS = {
    "qwen": "https://cdn.simpleicons.org/alibabacloud/FF6A00",
    "gemma": "https://cdn.simpleicons.org/googlegemini/4285F4",
    "llama": "https://cdn.simpleicons.org/meta/0467DF",
    "deepseek": "https://cdn.simpleicons.org/deepseek/4D6BFE",
    "mistral": "https://cdn.simpleicons.org/mistralai/FA520F",
    "phi": "https://cdn.simpleicons.org/microsoft/00A4EF",
    "smollm": "https://cdn.simpleicons.org/huggingface/FFD21E",
}


def _infer_family(repo_id: str) -> str:
    low = repo_id.lower()
    for fam in ("qwen", "gemma", "llama", "deepseek", "mistral", "phi", "smollm"):
        if fam in low:
            return fam
    return "custom"


def _infer_params(name: str) -> tuple[str, float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[bB]\b", name)
    if not m:
        return "7B", 7.0
    val = float(m.group(1))
    label = f"{int(val)}B" if val.is_integer() else f"{val}B"
    return label, val


def _slugify(repo_id: str) -> str:
    base = repo_id.split("/")[-1].lower()
    base = re.sub(r"-gguf$", "", base)
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:48]


def _pick_q4km(siblings: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    ggufs = [
        s for s in siblings
        if isinstance(s, dict)
        and str(s.get("rfilename", "")).lower().endswith(".gguf")
        and "mmproj" not in str(s.get("rfilename", "")).lower()
    ]
    for s in ggufs:
        if "q4_k_m" in str(s.get("rfilename", "")).lower():
            return s
    return ggufs[0] if ggufs else None


def sync_catalog(limit: int = 25, max_new: int = 5) -> int:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    existing_models: List[Dict[str, Any]] = payload.get("models", [])
    existing_ids = {m["id"] for m in existing_models}
    existing_repos = {m.get("hf_repo", "").lower() for m in existing_models}

    resp = httpx.get(
        "https://huggingface.co/api/models",
        params={"filter": "gguf", "sort": "trendingScore", "limit": limit},
        timeout=20.0,
    )
    resp.raise_for_status()
    repos = resp.json()

    added = 0
    for item in repos:
        if added >= max_new:
            break
        repo_id = item.get("id", "")
        owner = repo_id.split("/")[0].lower() if "/" in repo_id else ""
        if owner not in VERIFIED_ORGS or repo_id.lower() in existing_repos:
            continue

        detail = httpx.get(f"https://huggingface.co/api/models/{repo_id}", timeout=15.0)
        if detail.status_code != 200:
            continue
        info = detail.json()
        chosen = _pick_q4km(info.get("siblings", []))
        if not chosen:
            continue

        filename = chosen["rfilename"]
        size_bytes = int(chosen.get("size") or 0)
        size_gb = round(size_bytes / (1024 ** 3), 2) if size_bytes > 0 else 4.5
        if size_gb < 0.3 or size_gb > 48.0:
            continue

        mid = f"{_slugify(repo_id)}-q4km"
        if mid in existing_ids:
            continue

        fam = _infer_family(repo_id)
        param_str, param_num = _infer_params(repo_id)
        ram_req = max(2, int(round(size_gb * 1.25)))
        display_name = repo_id.split("/")[-1].replace("-GGUF", "").replace("_", " ").replace("-", " ")

        existing_models.append({
            "id": mid,
            "name": display_name[:52],
            "family": fam,
            "provider": repo_id.split("/")[0],
            "parameter_size": param_str,
            "parameter_count": param_num,
            "size_gb": size_gb,
            "ram_required_gb": ram_req,
            "ram_recommended_gb": ram_req + 4,
            "categories": ["general"],
            "description": f"Trending verified GGUF from {repo_id} ({param_str}).",
            "hf_repo": repo_id,
            "hf_filename": filename,
            "logo_url": FAMILY_LOGOS.get(fam, "https://cdn.simpleicons.org/huggingface/FFD21E"),
            "quantization": "Q4_K_M",
            "context_window": 32768,
            "supports_vision": "vl" in repo_id.lower() or "vision" in repo_id.lower(),
            "supports_tools": True,
            "quality_tier": "great",
            "speed_tier": "fast" if param_num <= 9 else "medium",
            "chat_template": "chatml",
            "is_new": True,
        })
        existing_ids.add(mid)
        existing_repos.add(repo_id.lower())
        added += 1

    if added > 0:
        payload["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload["models"] = existing_models
        CATALOG_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"Catalog sync complete: +{added} new models (total={len(existing_models)})")
    return added


if __name__ == "__main__":
    sync_catalog()
