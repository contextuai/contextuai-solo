"""
CloudProviderService — onboarding + live probes for cloud LLM providers.

Each provider type has its own probe shape:

- Anthropic: POST /v1/messages with a 1-token "ping"
- OpenAI:    GET  /v1/models
- Google:    GET  /v1beta/models?key=<api_key>
- Bedrock:   bedrock.list_foundation_models() (boto3, run via asyncio.to_thread)

All probes wrap their failures and return a structured ``CloudProviderTestResponse``
rather than raising — the caller never sees an unhandled exception escape.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

from models.cloud_provider_models import (
    MASK,
    SENSITIVE_KEYS,
    CloudProviderCreate,
    CloudProviderListResponse,
    CloudProviderResponse,
    CloudProviderTestResponse,
    CloudProviderType,
    CloudProviderUpdate,
    mask_config,
)
from repositories.cloud_provider_repository import CloudProviderRepository

logger = logging.getLogger(__name__)

PROBE_TIMEOUT_SECONDS = 10.0

# Module-level credentials cache: provider_type -> (expires_at_monotonic, config_dict).
# Keeps chatty inference paths from hammering SQLite on every call. TTL 60s.
_CREDS_CACHE_TTL = 60.0
_creds_cache: Dict[str, tuple] = {}


class CloudProviderService:
    """Business logic for cloud provider onboarding."""

    def __init__(self, db):
        self.db = db
        self.repo = CloudProviderRepository(db)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_with_masked_keys(self) -> CloudProviderListResponse:
        rows = await self.repo.list_all()
        return CloudProviderListResponse(
            success=True,
            providers=[CloudProviderResponse.from_row(r) for r in rows],
            total_count=len(rows),
        )

    async def get(self, provider_id: str) -> CloudProviderResponse:
        row = await self.repo.get_by_id(provider_id)
        if not row:
            raise HTTPException(404, f"Cloud provider '{provider_id}' not found")
        return CloudProviderResponse.from_row(row)

    # ------------------------------------------------------------------
    # Create / update / delete
    # ------------------------------------------------------------------

    async def create_or_update(
        self, payload: CloudProviderCreate
    ) -> CloudProviderResponse:
        """Upsert by provider_type — one row per type.

        If a row already exists for the same type, merge the new config into
        the existing one and refresh display_name. Otherwise insert a new row.
        """
        ptype = payload.provider_type.value
        display_name = payload.display_name or _default_display_name(ptype)
        merged_config = _strip_masks(payload.config or {}, ptype)

        existing = await self.repo.get_by_type(ptype)
        if existing:
            # Merge non-masked values onto existing config so partial updates work.
            merged = dict(existing.get("config") or {})
            merged.update(merged_config)
            saved = await self.repo.update(
                existing.get("provider_id") or existing.get("id") or existing.get("_id"),
                {
                    "display_name": display_name,
                    "config": merged,
                },
            ) or existing
        else:
            saved = await self.repo.create(
                provider_type=ptype,
                display_name=display_name,
                config=merged_config,
            )

        self.invalidate_cache(ptype)
        # Seed this provider's models on Save (the seeder gates on the saved
        # config having the required credential, not on a network probe — so
        # models become selectable immediately without blocking the save).
        await self._sync_cloud_models_safe()
        return CloudProviderResponse.from_row(saved)

    async def update(
        self, provider_id: str, payload: CloudProviderUpdate
    ) -> CloudProviderResponse:
        existing = await self.repo.get_by_id(provider_id)
        if not existing:
            raise HTTPException(404, f"Cloud provider '{provider_id}' not found")

        update: Dict[str, Any] = {}
        if payload.display_name is not None:
            update["display_name"] = payload.display_name
        if payload.config is not None:
            ptype = existing.get("provider_type") or ""
            stripped = _strip_masks(payload.config, ptype)
            merged = dict(existing.get("config") or {})
            merged.update(stripped)
            update["config"] = merged

        if not update:
            raise HTTPException(400, "Nothing to update")

        updated = await self.repo.update(provider_id, update)
        if not updated:
            raise HTTPException(404, f"Cloud provider '{provider_id}' not found")
        self.invalidate_cache(updated.get("provider_type"))
        return CloudProviderResponse.from_row(updated)

    async def delete(self, provider_id: str) -> None:
        existing = await self.repo.get_by_id(provider_id)
        deleted = await self.repo.delete(provider_id)
        if not deleted:
            raise HTTPException(404, f"Cloud provider '{provider_id}' not found")
        if existing:
            self.invalidate_cache(existing.get("provider_type"))
        else:
            self.invalidate_cache()
        # Remove this provider's seeded model rows now that it's gone.
        await self._sync_cloud_models_safe()

    # ------------------------------------------------------------------
    # Credentials lookup (used by inference paths)
    # ------------------------------------------------------------------

    async def get_credentials(
        self, provider_type: str
    ) -> Optional[Dict[str, Any]]:
        """Return the unmasked config dict for a provider type, or None.

        Cached for ``_CREDS_CACHE_TTL`` seconds so chat / automation paths
        don't hit SQLite on every call. Cache invalidated on save / delete.
        """
        now = time.monotonic()
        cached = _creds_cache.get(provider_type)
        if cached and cached[0] > now:
            return cached[1]

        row = await self.repo.get_by_type(provider_type)
        if not row:
            # Cache the negative result briefly to dampen probe storms.
            _creds_cache[provider_type] = (now + _CREDS_CACHE_TTL, None)  # type: ignore[assignment]
            return None
        cfg = dict(row.get("config") or {})
        _creds_cache[provider_type] = (now + _CREDS_CACHE_TTL, cfg)
        return cfg

    def invalidate_cache(self, provider_type: Optional[str] = None) -> None:
        """Wipe the credentials cache for one provider type or all of them."""
        if provider_type is None:
            _creds_cache.clear()
        else:
            _creds_cache.pop(provider_type, None)

    async def _sync_cloud_models_safe(self) -> None:
        """Re-seed cloud-model rows after a provider save. Never raises."""
        try:
            from services.cloud_model_seeder import sync_cloud_models_to_db
            await sync_cloud_models_to_db(self.db)
        except Exception:
            logger.exception(
                "Failed to re-sync cloud models after provider save (non-fatal)"
            )

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------

    async def test_connection(
        self,
        provider_type: str,
        config: Dict[str, Any],
    ) -> CloudProviderTestResponse:
        """Probe the provider with the given config. Never raises."""
        cfg = config or {}
        start = time.monotonic()
        try:
            if provider_type == CloudProviderType.ANTHROPIC.value:
                ok, error = await _probe_anthropic(cfg)
            elif provider_type == CloudProviderType.OPENAI.value:
                ok, error = await _probe_openai(cfg)
            elif provider_type == CloudProviderType.GOOGLE.value:
                ok, error = await _probe_google(cfg)
            elif provider_type == CloudProviderType.BEDROCK.value:
                ok, error = await _probe_bedrock(cfg)
            elif provider_type == CloudProviderType.OLLAMA.value:
                ok, error = await _probe_ollama(cfg)
            elif provider_type == CloudProviderType.OPENAI_COMPAT.value:
                ok, error = await _probe_openai(cfg, require_key=False)
            else:
                ok, error = False, f"Unsupported provider type: {provider_type!r}"
        except Exception as exc:  # safety net
            logger.exception("Cloud provider probe raised unexpectedly")
            ok, error = False, _short_error(exc)

        latency_ms = int((time.monotonic() - start) * 1000)
        return CloudProviderTestResponse(ok=ok, latency_ms=latency_ms, error=error)

    async def test_existing(self, provider_id: str) -> CloudProviderTestResponse:
        row = await self.repo.get_by_id(provider_id)
        if not row:
            raise HTTPException(404, f"Cloud provider '{provider_id}' not found")
        ptype = row.get("provider_type") or ""
        cfg = row.get("config") or {}
        result = await self.test_connection(ptype, cfg)
        await self.repo.set_test_result(
            row.get("provider_id") or row.get("id") or row.get("_id"),
            result.ok,
            result.error,
        )
        # Connection state changed — refresh the seeded model rows so a now-
        # connected provider's models become selectable immediately.
        self.invalidate_cache(ptype)
        await self._sync_cloud_models_safe()
        return result


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------

async def _probe_anthropic(cfg: Dict[str, Any]):
    # Validate via GET /v1/models (no hardcoded model-name dependency — the old
    # /v1/messages ping used claude-3-haiku-20240307, which Anthropic retired,
    # so the probe failed for every valid key).
    api_key = cfg.get("api_key") or ""
    if not api_key:
        return False, "Missing api_key"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models", headers=headers
            )
        if 200 <= resp.status_code < 300:
            return True, None
        return False, _extract_error_message(resp, default=f"HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        return False, _short_error(exc)


async def _probe_openai(cfg: Dict[str, Any], *, require_key: bool = True):
    """Probe an OpenAI(-compatible) server via GET ``{base_url}/models``.

    For real OpenAI ``require_key=True`` and ``base_url`` defaults to
    ``https://api.openai.com/v1``. For a custom OpenAI-compatible server
    (``openai_compat``) the key is optional and ``base_url`` comes from config.
    """
    api_key = cfg.get("api_key") or ""
    base_url = (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    if require_key and not api_key:
        return False, "Missing api_key"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
            resp = await client.get(f"{base_url}/models", headers=headers)
        if 200 <= resp.status_code < 300:
            return True, None
        return False, _extract_error_message(resp, default=f"HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        return False, (
            f"Could not reach {base_url} ({_short_error(exc)})"
            if not require_key else _short_error(exc)
        )


async def _probe_google(cfg: Dict[str, Any]):
    api_key = cfg.get("api_key") or ""
    if not api_key:
        return False, "Missing api_key"
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
            )
        if 200 <= resp.status_code < 300:
            return True, None
        return False, _extract_error_message(resp, default=f"HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        return False, _short_error(exc)


async def _probe_ollama(cfg: Dict[str, Any]):
    """Probe a local Ollama server by listing its pulled models.

    Ollama is key-less; the only config is an optional ``base_url`` (defaults
    to ``http://localhost:11434``). A 2xx from ``/api/tags`` means the server
    is reachable.
    """
    base_url = (cfg.get("base_url") or "http://localhost:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
            resp = await client.get(f"{base_url}/api/tags")
        if 200 <= resp.status_code < 300:
            return True, None
        return False, _extract_error_message(resp, default=f"HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        return False, (
            f"Could not reach Ollama at {base_url} — is `ollama serve` running? "
            f"({_short_error(exc)})"
        )


async def _probe_bedrock(cfg: Dict[str, Any]):
    import asyncio

    region = cfg.get("aws_region")
    access_key = cfg.get("aws_access_key_id")
    secret = cfg.get("aws_secret_access_key")
    if not (region and access_key and secret):
        return False, "Missing aws_region / aws_access_key_id / aws_secret_access_key"

    try:
        import boto3  # noqa: WPS433
        from botocore.exceptions import BotoCoreError, ClientError  # noqa: WPS433
    except Exception as exc:  # boto3 not installed
        return False, f"boto3 unavailable: {_short_error(exc)}"

    def _call():
        client = boto3.client(
            "bedrock",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret,
        )
        return client.list_foundation_models()

    try:
        await asyncio.to_thread(_call)
        return True, None
    except (ClientError, BotoCoreError) as exc:
        return False, _short_error(exc)
    except Exception as exc:
        return False, _short_error(exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_display_name(provider_type: str) -> str:
    return {
        "anthropic": "Anthropic",
        "openai": "OpenAI",
        "google": "Google AI",
        "bedrock": "AWS Bedrock",
        "ollama": "Ollama (Local)",
        "openai_compat": "OpenAI-Compatible",
    }.get(provider_type, provider_type.title())


def _strip_masks(config: Dict[str, Any], provider_type: str) -> Dict[str, Any]:
    """Drop masked sentinel values so they don't overwrite real stored creds.

    The UI re-submits the masked ``"***"`` placeholder when the user edits a
    saved provider without retyping the secret. Treat that as "leave existing
    value untouched" rather than "overwrite secret with literal ***".
    """
    out: Dict[str, Any] = {}
    sensitive = SENSITIVE_KEYS.get(provider_type, set())
    for key, value in (config or {}).items():
        if key in sensitive and value == MASK:
            continue
        out[key] = value
    return out


def _extract_error_message(resp: httpx.Response, default: str = "request failed") -> str:
    try:
        body = resp.json()
    except Exception:
        return f"{default}: {resp.text[:200]}" if resp.text else default
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if msg:
                return str(msg)[:300]
        if isinstance(err, str):
            return err[:300]
        msg = body.get("message")
        if msg:
            return str(msg)[:300]
    return default


def _short_error(exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    if len(msg) > 300:
        msg = msg[:297] + "..."
    return msg
