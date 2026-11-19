"""
Enterprise Policy, Catalog Governance & GGUF SHA-256 Verification (Issue #79).

Precedence (highest to lowest):
  1. Environment variables:
       - ``VESPER_AIRPLANE_LOCK_ENFORCED``
       - ``VESPER_CATALOG_URL`` (fallback: ``CATALOG_JSON_URL``)
       - ``VESPER_CATALOG_EXCLUSIVE``
       - ``VESPER_REQUIRE_SHA256``
  2. Admin policy JSON file:
       - ``VESPER_POLICY_FILE`` env var -> ``~/.contextuai-solo/policy.json`` ->
         OS-managed path (``C:\\ProgramData\\Vesper\\policy.json`` on Windows,
         ``/etc/vesper/policy.json`` on Linux,
         ``/Library/Application Support/Vesper/policy.json`` on macOS)
  3. User enterprise settings JSON file:
       - ``VESPER_ENTERPRISE_SETTINGS_PATH`` env var ->
         ``~/.contextuai-solo/data/enterprise_settings.json``
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB streaming chunks for multi-GB GGUFs
_SHA256_CACHE_MAX = 256
_SHA256_CACHE: Dict[Tuple[str, int, int], str] = {}
_SHA256_LOCK = threading.Lock()

_WRITABLE_USER_FIELDS = ("catalog_url", "catalog_exclusive", "require_sha256", "allowed_model_sha256")
_KNOWN_POLICY_FIELDS = (
    "catalog_url",
    "catalog_exclusive",
    "require_sha256",
    "airplane_lock_enforced",
    "allowed_model_sha256",
)


class ModelIntegrityError(RuntimeError):
    """Raised when a GGUF file fails SHA-256 verification or lacks a required checksum."""


def _parse_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in ("1", "true", "yes", "on"):
            return True
        if cleaned in ("0", "false", "no", "off"):
            return False
    return None


def _normalize_sha256(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if cleaned.startswith("sha256:"):
        cleaned = cleaned[7:].strip()
    return cleaned or None


def _normalize_allowed_hashes(raw: Any) -> Optional[Union[Dict[str, str], List[str]]]:
    if isinstance(raw, dict):
        out: Dict[str, str] = {}
        for k, v in raw.items():
            norm_v = _normalize_sha256(str(v)) if v is not None else None
            if norm_v:
                out[str(k).strip()] = norm_v
        return out
    if isinstance(raw, list):
        out_list: List[str] = []
        for item in raw:
            norm_v = _normalize_sha256(str(item)) if item is not None else None
            if norm_v:
                out_list.append(norm_v)
        return out_list
    return None


def _get_os_admin_policy_path() -> Path:
    system = platform.system().lower()
    if system == "windows":
        prog_data = os.environ.get("ProgramData") or r"C:\ProgramData"
        return Path(prog_data) / "Vesper" / "policy.json"
    if system == "darwin":
        return Path("/Library/Application Support/Vesper/policy.json")
    return Path("/etc/vesper/policy.json")


def _resolve_admin_policy_file() -> Optional[Path]:
    env_file = (os.getenv("VESPER_POLICY_FILE") or "").strip()
    if env_file:
        candidate = Path(env_file).expanduser()
        return candidate if candidate.is_file() else None

    candidates = [
        Path.home() / ".contextuai-solo" / "policy.json",
        _get_os_admin_policy_path(),
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _resolve_user_settings_path() -> Path:
    env_path = (os.getenv("VESPER_ENTERPRISE_SETTINGS_PATH") or "").strip()
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".contextuai-solo" / "data" / "enterprise_settings.json"


def _resolve_sha256_cache_path() -> Path:
    env_path = (os.getenv("VESPER_SHA256_CACHE_PATH") or "").strip()
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".contextuai-solo" / "data" / "model_sha256_cache.json"


def _read_json_dict(path: Optional[Path]) -> Dict[str, Any]:
    if not path:
        return {}
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to parse JSON policy/settings file %s: %s", path, exc)
        return {}


def _lookup_cached_sha256(abs_path: str, size: int, mtime_ns: int) -> Optional[str]:
    cache_key = (abs_path, size, mtime_ns)
    with _SHA256_LOCK:
        cached = _SHA256_CACHE.get(cache_key)
        if cached is not None:
            return cached

        disk_entries = _read_json_dict(_resolve_sha256_cache_path())
        entry = disk_entries.get(abs_path)
        if isinstance(entry, dict):
            entry_sha = entry.get("sha256")
            if (
                entry.get("size") == size
                and entry.get("mtime_ns") == mtime_ns
                and isinstance(entry_sha, str)
                and entry_sha
            ):
                norm_sha = entry_sha.lower()
                if len(_SHA256_CACHE) >= _SHA256_CACHE_MAX:
                    _SHA256_CACHE.clear()
                _SHA256_CACHE[cache_key] = norm_sha
                return norm_sha
    return None


def _store_cached_sha256(abs_path: str, size: int, mtime_ns: int, digest: str) -> None:
    cache_key = (abs_path, size, mtime_ns)
    norm_sha = digest.lower()
    with _SHA256_LOCK:
        if len(_SHA256_CACHE) >= _SHA256_CACHE_MAX:
            _SHA256_CACHE.clear()
        _SHA256_CACHE[cache_key] = norm_sha

        cache_path = _resolve_sha256_cache_path()
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            disk_entries = _read_json_dict(cache_path)
            disk_entries[abs_path] = {
                "size": size,
                "mtime_ns": mtime_ns,
                "sha256": norm_sha,
            }
            tmp_path = cache_path.parent / f".{cache_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            tmp_path.write_text(json.dumps(disk_entries, indent=2), encoding="utf-8")
            os.replace(tmp_path, cache_path)
        except Exception as exc:
            logger.debug("Unable to persist SHA-256 cache %s: %s", cache_path, exc)


def get_cached_file_sha256(path: str) -> Optional[str]:
    """Return cached SHA-256 hex digest from RAM/disk if ``(size, mtime_ns)`` matches, else ``None``."""
    abs_path = os.path.abspath(os.path.expanduser(path))
    try:
        st = os.stat(abs_path)
    except OSError:
        return None
    return _lookup_cached_sha256(abs_path, int(st.st_size), int(st.st_mtime_ns))


def compute_file_sha256(path: str) -> str:
    """Compute SHA-256 hex digest using 8 MB chunks, cached in RAM and on disk."""
    abs_path = os.path.abspath(os.path.expanduser(path))
    st = os.stat(abs_path)
    size = int(st.st_size)
    mtime_ns = int(st.st_mtime_ns)

    cached = _lookup_cached_sha256(abs_path, size, mtime_ns)
    if cached is not None:
        return cached

    hasher = hashlib.sha256()
    with open(abs_path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    digest = hasher.hexdigest().lower()

    _store_cached_sha256(abs_path, size, mtime_ns, digest)
    return digest


def get_enterprise_policy() -> Dict[str, Any]:
    """Resolve effective enterprise policy from env vars -> admin policy -> user settings."""
    admin_path = _resolve_admin_policy_file()
    admin_data = _read_json_dict(admin_path)

    user_path = _resolve_user_settings_path()
    user_data = _read_json_dict(user_path)

    locked_fields: List[str] = []
    used_env = False

    def _mark_locked(field: str) -> None:
        if field not in locked_fields:
            locked_fields.append(field)

    # 1. catalog_url
    catalog_url: Optional[str] = None
    env_catalog_url = (os.getenv("VESPER_CATALOG_URL") or os.getenv("CATALOG_JSON_URL") or "").strip()
    if env_catalog_url:
        catalog_url = env_catalog_url
        _mark_locked("catalog_url")
        used_env = True
    elif "catalog_url" in admin_data and admin_data["catalog_url"] is not None:
        catalog_url = str(admin_data["catalog_url"]).strip() or None
        _mark_locked("catalog_url")
    elif "catalog_url" in user_data and user_data["catalog_url"] is not None:
        catalog_url = str(user_data["catalog_url"]).strip() or None

    # 2. catalog_exclusive
    catalog_exclusive: bool = False
    env_exclusive = _parse_bool(os.getenv("VESPER_CATALOG_EXCLUSIVE"))
    if env_exclusive is not None:
        catalog_exclusive = env_exclusive
        _mark_locked("catalog_exclusive")
        used_env = True
    elif "catalog_exclusive" in admin_data and _parse_bool(admin_data["catalog_exclusive"]) is not None:
        catalog_exclusive = bool(_parse_bool(admin_data["catalog_exclusive"]))
        _mark_locked("catalog_exclusive")
    elif "catalog_exclusive" in user_data and _parse_bool(user_data["catalog_exclusive"]) is not None:
        catalog_exclusive = bool(_parse_bool(user_data["catalog_exclusive"]))

    # 3. require_sha256
    require_sha256: bool = False
    env_req_sha = _parse_bool(os.getenv("VESPER_REQUIRE_SHA256"))
    if env_req_sha is not None:
        require_sha256 = env_req_sha
        _mark_locked("require_sha256")
        used_env = True
    elif "require_sha256" in admin_data and _parse_bool(admin_data["require_sha256"]) is not None:
        require_sha256 = bool(_parse_bool(admin_data["require_sha256"]))
        _mark_locked("require_sha256")
    elif "require_sha256" in user_data and _parse_bool(user_data["require_sha256"]) is not None:
        require_sha256 = bool(_parse_bool(user_data["require_sha256"]))

    # 4. airplane_lock_enforced (admin/env only)
    airplane_lock_enforced: bool = False
    env_lock = _parse_bool(os.getenv("VESPER_AIRPLANE_LOCK_ENFORCED"))
    if env_lock is not None:
        airplane_lock_enforced = env_lock
        _mark_locked("airplane_lock_enforced")
        used_env = True
    elif "airplane_lock_enforced" in admin_data and _parse_bool(admin_data["airplane_lock_enforced"]) is not None:
        airplane_lock_enforced = bool(_parse_bool(admin_data["airplane_lock_enforced"]))
        _mark_locked("airplane_lock_enforced")

    # 5. allowed_model_sha256
    allowed_model_sha256: Optional[Union[Dict[str, str], List[str]]] = None
    if "allowed_model_sha256" in admin_data and admin_data["allowed_model_sha256"] is not None:
        parsed_allowed = _normalize_allowed_hashes(admin_data["allowed_model_sha256"])
        if parsed_allowed is not None:
            allowed_model_sha256 = parsed_allowed
            _mark_locked("allowed_model_sha256")
    elif "allowed_model_sha256" in user_data and user_data["allowed_model_sha256"] is not None:
        parsed_allowed = _normalize_allowed_hashes(user_data["allowed_model_sha256"])
        if parsed_allowed is not None:
            allowed_model_sha256 = parsed_allowed

    # Explicit locked_fields list in admin policy (optional)
    if isinstance(admin_data.get("locked_fields"), list):
        for f in admin_data["locked_fields"]:
            if isinstance(f, str) and f in _KNOWN_POLICY_FIELDS:
                _mark_locked(f)

    if used_env:
        policy_source = "env"
    elif admin_path is not None:
        policy_source = "admin_policy"
    elif user_data:
        policy_source = "user_settings"
    else:
        policy_source = "default"

    return {
        "catalog_url": catalog_url,
        "catalog_exclusive": catalog_exclusive,
        "require_sha256": require_sha256,
        "airplane_lock_enforced": airplane_lock_enforced,
        "allowed_model_sha256": allowed_model_sha256,
        "locked_fields": locked_fields,
        "policy_source": policy_source,
        "policy_file": str(admin_path) if admin_path else None,
    }


def is_airplane_lock_policy_enforced() -> Tuple[bool, Optional[str]]:
    """Return ``(enforced, source)`` indicating if Airplane Lock is locked by policy."""
    env_lock = _parse_bool(os.getenv("VESPER_AIRPLANE_LOCK_ENFORCED"))
    if env_lock is not None:
        return (True, "env") if env_lock else (False, None)

    admin_path = _resolve_admin_policy_file()
    admin_data = _read_json_dict(admin_path)
    admin_lock = _parse_bool(admin_data.get("airplane_lock_enforced"))
    if admin_lock is True:
        return (True, "admin_policy")

    return (False, None)


def resolve_expected_sha256(
    model_id: Optional[str] = None,
    filename: Optional[str] = None,
    catalog_entry: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Look up expected SHA-256 from catalog entry or enterprise policy ``allowed_model_sha256``."""
    if catalog_entry and catalog_entry.get("sha256"):
        norm = _normalize_sha256(str(catalog_entry["sha256"]))
        if norm:
            return norm

    policy = get_enterprise_policy()
    allowed = policy.get("allowed_model_sha256")
    if not isinstance(allowed, dict) or not allowed:
        return None

    candidates: List[str] = []
    if model_id:
        mid = str(model_id).strip()
        candidates.append(mid)
        if mid.startswith("local:"):
            candidates.append(mid[len("local:"):])
    if catalog_entry and catalog_entry.get("id"):
        candidates.append(str(catalog_entry["id"]).strip())
    if filename:
        fn = str(filename).strip()
        candidates.append(fn)
        candidates.append(fn.lower())
    if catalog_entry and catalog_entry.get("hf_filename"):
        hfn = str(catalog_entry["hf_filename"]).strip()
        candidates.append(hfn)
        candidates.append(hfn.lower())

    lower_map = {str(k).strip().lower(): v for k, v in allowed.items()}
    for cand in candidates:
        if cand in allowed:
            return _normalize_sha256(allowed[cand])
        if cand.lower() in lower_map:
            return _normalize_sha256(lower_map[cand.lower()])

    return None


def verify_gguf_sha256(
    path: str,
    expected_sha256: Optional[str] = None,
    *,
    require_checksum: Optional[bool] = None,
) -> Dict[str, Any]:
    """Verify a GGUF file against an expected SHA-256 checksum or enterprise policy.

    Returns ``{"verified": bool, "sha256": actual, "expected_sha256": expected}``.
    Raises ``ModelIntegrityError`` on checksum mismatch or when checksum verification
    is required but no expected hash is available.
    """
    policy = get_enterprise_policy()
    effective_required = (
        bool(require_checksum)
        if require_checksum is not None
        else bool(policy.get("require_sha256", False))
    )
    expected = _normalize_sha256(expected_sha256)
    actual = compute_file_sha256(path)

    if expected is not None:
        if actual != expected:
            raise ModelIntegrityError(
                f"SHA-256 checksum mismatch for '{os.path.basename(path)}': "
                f"expected {expected}, got {actual}."
            )
        return {
            "verified": True,
            "sha256": actual,
            "expected_sha256": expected,
        }

    # Check policy list allowlist if configured
    allowed = policy.get("allowed_model_sha256")
    if isinstance(allowed, list) and len(allowed) > 0:
        allowed_set = {h for h in (_normalize_sha256(x) for x in allowed) if h}
        if actual in allowed_set:
            return {
                "verified": True,
                "sha256": actual,
                "expected_sha256": actual,
            }
        raise ModelIntegrityError(
            f"SHA-256 checksum '{actual}' for '{os.path.basename(path)}' "
            "is not in enterprise allowed_model_sha256 list."
        )

    if effective_required:
        raise ModelIntegrityError(
            f"Enterprise policy requires SHA-256 verification, but no expected "
            f"checksum is configured for '{os.path.basename(path)}'."
        )

    return {
        "verified": False,
        "sha256": actual,
        "expected_sha256": None,
    }


def save_user_enterprise_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Persist unlocked user enterprise preferences to disk.

    Raises ``PermissionError`` if ``patch`` attempts to change any field in
    ``locked_fields`` or ``airplane_lock_enforced``.
    """
    if not isinstance(patch, dict):
        raise ValueError("Policy patch must be a JSON object")

    current = get_enterprise_policy()
    locked = set(current.get("locked_fields") or [])

    normalized_updates: Dict[str, Any] = {}
    for key, raw_val in patch.items():
        if key not in _KNOWN_POLICY_FIELDS:
            continue

        if key == "catalog_url":
            norm_val: Any = str(raw_val).strip() or None if raw_val is not None else None
        elif key in ("catalog_exclusive", "require_sha256", "airplane_lock_enforced"):
            if raw_val is None:
                norm_val = current.get(key)
            else:
                parsed = _parse_bool(raw_val)
                if parsed is None:
                    raise ValueError(f"Invalid boolean value for '{key}': {raw_val!r}")
                norm_val = parsed
        elif key == "allowed_model_sha256":
            norm_val = _normalize_allowed_hashes(raw_val) if raw_val is not None else None
        else:
            norm_val = raw_val

        if key in locked:
            if norm_val != current.get(key):
                raise PermissionError(
                    f"Enterprise policy field '{key}' is locked by {current.get('policy_source')} "
                    "and cannot be modified."
                )
            continue

        if key == "airplane_lock_enforced":
            if norm_val != current.get("airplane_lock_enforced"):
                raise PermissionError(
                    "Field 'airplane_lock_enforced' can only be configured via "
                    "environment variable or admin policy file."
                )
            continue

        if key in _WRITABLE_USER_FIELDS:
            normalized_updates[key] = norm_val

    user_path = _resolve_user_settings_path()
    existing = _read_json_dict(user_path)
    existing.update(normalized_updates)
    user_path.parent.mkdir(parents=True, exist_ok=True)
    user_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    return get_enterprise_policy()
