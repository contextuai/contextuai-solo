"""
Living Model Catalog: Live HuggingFace GGUF Discovery & OTA Catalog Sync (SPEC-34).

Provides:
1. ``search_hf_gguf_models``: Live search/trending feed against HuggingFace Hub API
   with an optional verified-quantizer filter.
2. ``list_hf_repo_gguf_files``: Lists all ``.gguf`` files in a HuggingFace repo,
   separates companion ``mmproj`` vision projectors, runs every quant file through
   ``classify_model_fit()``, and highlights the recommended quant for the user's PC.
3. ``refresh_ota_catalog``: Merges new models from a cached/remote JSON manifest
   into ``LOCAL_MODEL_CATALOG`` without requiring an application reinstall.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import httpx

from services import model_catalog
from services.gguf_inspector import infer_quantization_from_filename
from services.hardware import get_hardware_profile
from services.model_fit_engine import classify_model_fit

logger = logging.getLogger(__name__)

VERIFIED_QUANTIZERS = (
    "unsloth",
    "bartowski",
    "qwen",
    "ggml-org",
    "lmstudio-community",
    "google",
    "mistralai",
)

DEFAULT_OTA_CACHE_PATH = os.getenv(
    "CATALOG_CACHE_PATH",
    os.path.join(os.path.expanduser("~"), ".contextuai-solo", "data", "catalog_cache.json"),
)
DEFAULT_OTA_CATALOG_URL = os.getenv(
    "VESPER_CATALOG_URL",
    os.getenv(
        "CATALOG_JSON_URL",
        "https://raw.githubusercontent.com/contextuai/vesper/main/catalog/models.json",
    ),
)
_MEIPASS = getattr(sys, "_MEIPASS", None)
DEFAULT_REPO_OTA_MANIFEST = (
    (Path(_MEIPASS) / "catalog" / "models.json")
    if _MEIPASS
    else (Path(__file__).resolve().parents[2] / "catalog" / "models.json")
)

# Snapshot of the built-in curated catalog so toggling exclusive mode off
# cleanly restores all built-in models while preserving list/dict object identity.
_BUILTIN_CATALOG_SNAPSHOT: List[Dict[str, Any]] = [
    copy.deepcopy(m) for m in model_catalog.LOCAL_MODEL_CATALOG
]
_EXCLUSIVE_MODE_ACTIVE: bool = False

# Preferred quant priority when multiple quants fit comfortably in GPU/RAM
_QUANT_PREFERENCE = {
    "Q4_K_M": 100,
    "Q4_K_L": 95,
    "Q5_K_M": 92,
    "Q5_K_S": 88,
    "Q4_K_S": 85,
    "Q6_K": 82,
    "Q8_0": 80,
    "Q4_0": 75,
    "IQ4_XS": 70,
    "Q3_K_M": 60,
    "Q2_K": 40,
    "F16": 30,
    "BF16": 30,
}


def _build_hf_headers(hf_token: Optional[str] = None) -> Dict[str, str]:
    token = (
        (hf_token or "").strip()
        or os.getenv("HF_TOKEN")
        or os.getenv("HUGGING_FACE_HUB_TOKEN")
    )
    headers = {"Accept": "application/json", "User-Agent": "ContextuAI-Solo/2027"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def search_hf_gguf_models(
    query: str = "",
    sort: str = "trending",
    limit: int = 20,
    verified_only: bool = True,
    hf_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Query HuggingFace Hub for GGUF repositories (SPEC-34)."""
    url = "https://huggingface.co/api/models"
    try:
        from services.net_guard import assert_egress_allowed, record_egress
        assert_egress_allowed(url, "hf_hub_search")
    except ImportError:
        record_egress = None

    params: Dict[str, Any] = {
        "filter": "gguf",
        "limit": min(max(limit * 3 if verified_only else limit, 10), 100),
    }
    if query and query.strip():
        params["search"] = query.strip()

    sort_map = {
        "trending": "trendingScore",
        "downloads": "downloads",
        "likes": "likes",
        "recent": "lastModified",
    }
    hf_sort = sort_map.get(sort, "trendingScore")
    params["sort"] = hf_sort
    if hf_sort in ("downloads", "likes", "lastModified"):
        params["direction"] = "-1"

    headers = _build_hf_headers(hf_token)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        items = resp.json()

    if record_egress:
        record_egress(url, "hf_hub_search", 0)

    results: List[Dict[str, Any]] = []
    verified_set = {q.lower() for q in VERIFIED_QUANTIZERS}

    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("id") or item.get("modelId") or "")
        if not repo_id or "/" not in repo_id:
            continue
        author = repo_id.split("/", 1)[0]
        is_verified = author.lower() in verified_set
        if verified_only and not is_verified:
            continue

        tags = item.get("tags") or []
        results.append({
            "repo_id": repo_id,
            "author": author,
            "name": repo_id.split("/", 1)[1],
            "downloads": int(item.get("downloads") or 0),
            "likes": int(item.get("likes") or 0),
            "last_modified": item.get("lastModified"),
            "verified_quantizer": is_verified,
            "pipeline_tag": item.get("pipeline_tag"),
            "supports_vision": any(t in ("image-text-to-text", "vision") for t in tags),
        })
        if len(results) >= limit:
            break

    return {
        "models": results,
        "count": len(results),
        "query": query,
        "sort": sort,
        "verified_only": verified_only,
    }


async def list_hf_repo_gguf_files(
    repo_id: str,
    hardware_profile: Optional[Dict[str, Any]] = None,
    hf_token: Optional[str] = None,
) -> Dict[str, Any]:
    """List all ``.gguf`` files in a HuggingFace repo and classify fit per quant (SPEC-34)."""
    if not repo_id or "/" not in repo_id:
        raise ValueError(f"Invalid HuggingFace repo_id: {repo_id!r}")

    url = f"https://huggingface.co/api/models/{repo_id}"
    try:
        from services.net_guard import assert_egress_allowed, record_egress
        assert_egress_allowed(url, "hf_repo_files")
    except ImportError:
        record_egress = None

    headers = _build_hf_headers(hf_token)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params={"blobs": "true"}, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    if record_egress:
        record_egress(url, "hf_repo_files", 0)

    hw = hardware_profile or get_hardware_profile()
    siblings = data.get("siblings") if isinstance(data, dict) else []
    quant_files: List[Dict[str, Any]] = []
    mmproj_files: List[Dict[str, Any]] = []

    for sib in siblings or []:
        if not isinstance(sib, dict):
            continue
        rfilename = str(sib.get("rfilename") or "")
        if not rfilename.lower().endswith(".gguf"):
            continue

        # Size can be at top-level 'size' or inside 'lfs.size'
        size_bytes = sib.get("size")
        if not size_bytes and isinstance(sib.get("lfs"), dict):
            size_bytes = sib["lfs"].get("size")
        size_bytes = int(size_bytes or 0)
        size_gb = round(size_bytes / (1024 ** 3), 2) if size_bytes > 0 else 4.0

        if "mmproj" in rfilename.lower():
            mmproj_files.append({
                "filename": rfilename,
                "size_bytes": size_bytes,
                "size_gb": size_gb,
            })
            continue

        quant = infer_quantization_from_filename(rfilename)
        synthetic_entry = {
            "id": f"{repo_id}/{rfilename}",
            "name": rfilename,
            "size_gb": size_gb,
            "ram_required_gb": max(1.0, round(size_gb * 1.25, 1)),
            "quantization": quant,
            "context_window": 32768,
        }
        fit = classify_model_fit(synthetic_entry, hw)
        quant_files.append({
            "filename": rfilename,
            "size_bytes": size_bytes,
            "size_gb": size_gb,
            "quantization": quant,
            "fit": fit,
            "is_recommended_quant": False,
        })

    # Choose the recommended quant for this hardware
    recommended_filename: Optional[str] = None
    fitting = [f for f in quant_files if f["fit"]["verdict"] != "wont_fit"]
    if fitting:
        def _quant_rank(f: Dict[str, Any]):
            verdict_score = 2 if f["fit"]["verdict"] == "fits_gpu" else 1
            q_pref = _QUANT_PREFERENCE.get(f["quantization"], 50)
            return (verdict_score, q_pref, -f["size_gb"])

        best = max(fitting, key=_quant_rank)
        best["is_recommended_quant"] = True
        recommended_filename = best["filename"]

    return {
        "repo_id": repo_id,
        "files": quant_files,
        "mmproj_files": mmproj_files,
        "recommended_filename": recommended_filename,
        "supports_vision": bool(mmproj_files),
    }


def _resolve_local_manifest_path(source_str: str) -> Optional[Path]:
    """Return a local filesystem ``Path`` if ``source_str`` is a local path or ``file://`` URI."""
    cleaned = (source_str or "").strip()
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    scheme = (parsed.scheme or "").lower()
    if scheme in ("http", "https"):
        return None
    if scheme == "file":
        raw_path = url2pathname(unquote(parsed.path or ""))
        if parsed.netloc and parsed.netloc.lower() not in ("", "localhost"):
            raw_path = f"//{parsed.netloc}{unquote(parsed.path or '')}"
        return Path(raw_path)
    if not scheme or (len(scheme) == 1 and scheme.isalpha()):
        return Path(cleaned).expanduser()
    return None


def restore_builtin_catalog() -> int:
    """Restore built-in ``LOCAL_MODEL_CATALOG`` and ``_CATALOG_BY_ID`` in place."""
    global _EXCLUSIVE_MODE_ACTIVE
    restored = [copy.deepcopy(m) for m in _BUILTIN_CATALOG_SNAPSHOT]
    model_catalog.LOCAL_MODEL_CATALOG[:] = restored
    model_catalog._CATALOG_BY_ID.clear()
    for item in restored:
        model_catalog._CATALOG_BY_ID[str(item["id"])] = item
    _EXCLUSIVE_MODE_ACTIVE = False
    return len(restored)


def _normalize_catalog_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    if "id" not in entry or "name" not in entry:
        return None
    has_hf = bool(entry.get("hf_repo") and entry.get("hf_filename"))
    download_url = str(entry.get("download_url") or "").strip()
    if not has_hf and not download_url:
        return None

    mid = str(entry["id"])
    hf_filename = str(entry.get("hf_filename") or "").strip()
    if not hf_filename and download_url:
        derived = Path(unquote(urlparse(download_url).path)).name
        hf_filename = derived if derived.lower().endswith(".gguf") else f"{mid}.gguf"

    hf_repo = str(entry.get("hf_repo") or "enterprise").strip()
    normalized: Dict[str, Any] = {
        "family": entry.get("family", "custom"),
        "provider": entry.get("provider", "Community"),
        "parameter_size": entry.get("parameter_size", "Unknown"),
        "parameter_count": float(entry.get("parameter_count") or 7.0),
        "size_gb": float(entry.get("size_gb") or 4.5),
        "ram_required_gb": int(entry.get("ram_required_gb") or 6),
        "ram_recommended_gb": int(entry.get("ram_recommended_gb") or 8),
        "categories": list(entry.get("categories") or ["general"]),
        "description": str(entry.get("description") or entry["name"]),
        "quantization": str(entry.get("quantization") or "Q4_K_M"),
        "context_window": int(entry.get("context_window") or 32768),
        "supports_vision": bool(entry.get("supports_vision", False)),
        "supports_tools": bool(entry.get("supports_tools", True)),
        "quality_tier": str(entry.get("quality_tier") or "great"),
        "speed_tier": str(entry.get("speed_tier") or "fast"),
        "chat_template": str(entry.get("chat_template") or "chatml"),
        "is_new": True,
        **entry,
        "id": mid,
        "hf_repo": hf_repo,
        "hf_filename": hf_filename,
    }
    if download_url:
        normalized["download_url"] = download_url
    if entry.get("sha256"):
        sha = str(entry["sha256"]).strip().lower()
        if sha.startswith("sha256:"):
            sha = sha[7:].strip()
        normalized["sha256"] = sha
    return normalized


def merge_catalog_entries(
    new_entries: List[Dict[str, Any]],
    *,
    replace_existing: bool = False,
) -> int:
    """Merge validated catalog entries into ``LOCAL_MODEL_CATALOG`` in-place.

    When ``replace_existing=True`` (enterprise exclusive mode), replaces
    ``LOCAL_MODEL_CATALOG`` and ``_CATALOG_BY_ID`` with only the validated entries
    while preserving the list/dict object identities imported by other modules.
    """
    global _EXCLUSIVE_MODE_ACTIVE

    validated: List[Dict[str, Any]] = []
    for entry in new_entries:
        norm = _normalize_catalog_entry(entry)
        if norm is not None:
            validated.append(norm)

    if replace_existing:
        model_catalog.LOCAL_MODEL_CATALOG[:] = validated
        model_catalog._CATALOG_BY_ID.clear()
        for item in validated:
            model_catalog._CATALOG_BY_ID[str(item["id"])] = item
        _EXCLUSIVE_MODE_ACTIVE = True
        return len(validated)

    if _EXCLUSIVE_MODE_ACTIVE:
        restore_builtin_catalog()

    added_or_updated = 0
    for normalized in validated:
        mid = str(normalized["id"])
        if mid in model_catalog._CATALOG_BY_ID:
            existing = model_catalog._CATALOG_BY_ID[mid]
            existing.update(normalized)
        else:
            model_catalog.LOCAL_MODEL_CATALOG.append(normalized)
            model_catalog._CATALOG_BY_ID[mid] = normalized
        added_or_updated += 1

    return added_or_updated


def _extract_models_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and "models" in payload and isinstance(payload["models"], list):
        return payload["models"]
    if isinstance(payload, list):
        return payload
    return []


async def refresh_ota_catalog(
    remote_url: Optional[str] = None,
    cache_path: Optional[str] = None,
    exclusive: Optional[bool] = None,
) -> Dict[str, Any]:
    """Refresh the curated model catalog from an enterprise/OTA manifest or local cache."""
    from services.enterprise_policy import get_enterprise_policy

    policy = get_enterprise_policy()
    effective_exclusive = (
        bool(exclusive)
        if exclusive is not None
        else bool(policy.get("catalog_exclusive", False))
    )
    policy_url = policy.get("catalog_url")
    candidate_url = (
        remote_url if remote_url is not None else (policy_url or DEFAULT_OTA_CATALOG_URL)
    ) or ""

    target_cache = Path(cache_path or DEFAULT_OTA_CACHE_PATH)
    entries_loaded: List[Dict[str, Any]] = []
    manifest_loaded = False
    source = "bundled"

    should_fetch_source = bool(candidate_url) and (
        remote_url is not None or policy_url is not None or cache_path is None
    )

    if should_fetch_source:
        local_manifest = _resolve_local_manifest_path(candidate_url)
        if local_manifest is not None:
            # Local filesystem paths & file:// URIs read directly without net_guard
            # so air-gapped enterprise deployments can sync under Airplane Lock.
            if not local_manifest.is_file():
                raise FileNotFoundError(f"Catalog manifest file not found: {local_manifest}")
            payload = json.loads(local_manifest.read_text(encoding="utf-8"))
            entries_loaded = _extract_models_from_payload(payload)
            manifest_loaded = True
            source = "local_file"
            if entries_loaded:
                target_cache.parent.mkdir(parents=True, exist_ok=True)
                target_cache.write_text(json.dumps(entries_loaded, indent=2), encoding="utf-8")
        else:
            try:
                try:
                    from services.net_guard import assert_egress_allowed, record_egress
                    assert_egress_allowed(candidate_url, "ota_catalog_sync")
                except ImportError:
                    record_egress = None

                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(candidate_url)
                    resp.raise_for_status()
                    payload = resp.json()

                if record_egress:
                    record_egress(
                        candidate_url,
                        "ota_catalog_sync",
                        len(resp.content) if resp.content else 0,
                    )

                entries_loaded = _extract_models_from_payload(payload)
                manifest_loaded = True
                source = "remote"
                if entries_loaded:
                    target_cache.parent.mkdir(parents=True, exist_ok=True)
                    target_cache.write_text(json.dumps(entries_loaded, indent=2), encoding="utf-8")
            except Exception as exc:
                # If caller or enterprise policy explicitly targeted this URL, surface the error
                if remote_url is not None or policy_url is not None:
                    raise
                logger.debug("Remote OTA catalog sync skipped (%s); falling back to local cache/manifest", exc)

    if not manifest_loaded and target_cache.is_file():
        try:
            raw = json.loads(target_cache.read_text(encoding="utf-8"))
            entries_loaded = _extract_models_from_payload(raw)
            if entries_loaded:
                manifest_loaded = True
                source = "cache"
        except Exception as exc:
            logger.warning("Failed to read OTA catalog cache at %s: %s", target_cache, exc)

    if not manifest_loaded and DEFAULT_REPO_OTA_MANIFEST.is_file():
        try:
            raw = json.loads(DEFAULT_REPO_OTA_MANIFEST.read_text(encoding="utf-8"))
            entries_loaded = _extract_models_from_payload(raw)
            if entries_loaded:
                manifest_loaded = True
                source = "manifest"
        except Exception as exc:
            logger.warning("Failed to read bundled OTA manifest: %s", exc)

    if manifest_loaded:
        merged_count = merge_catalog_entries(
            entries_loaded,
            replace_existing=effective_exclusive,
        )
    elif not effective_exclusive and _EXCLUSIVE_MODE_ACTIVE:
        restore_builtin_catalog()
        merged_count = 0
    else:
        merged_count = 0

    try:
        from models.audit_models import AuditAction, AuditSeverity
        from services.audit_service import audit_log_sync
        audit_log_sync(
            getattr(AuditAction, "CATALOG_REFRESHED", "catalog.refreshed"),
            resource_type="catalog",
            resource_id=source,
            details={
                "source": source,
                "merged_count": merged_count,
                "exclusive": effective_exclusive,
                "total_catalog_models": len(model_catalog.LOCAL_MODEL_CATALOG),
            },
            severity=AuditSeverity.INFO,
        )
    except Exception:
        pass

    return {
        "status": "ok",
        "source": source,
        "merged_count": merged_count,
        "total_catalog_models": len(model_catalog.LOCAL_MODEL_CATALOG),
        "exclusive": effective_exclusive,
        "catalog_url": candidate_url,
    }
