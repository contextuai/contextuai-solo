"""
Cloud Model Seeder — register cloud-provider models in the ``models`` collection.

Mirrors ``local_model_seeder.py`` but for cloud providers (Anthropic, OpenAI,
Google). For each provider with a connected ``cloud_providers`` row we upsert
a small static catalog of user-facing model rows so the chat dropdown / crew
builder / automations pickers can list them alongside local GGUFs.

Document IDs are namespaced ``"<provider>:<model_short_id>"`` (e.g.
``"anthropic:claude-sonnet-4-6"``) — same prefix the inference dispatcher in
``automation_executor._call_model`` uses to route per-provider calls.

TODO: re-seed mid-session when a NEW provider is connected via the UI. Today
the seeder runs at startup and again from ``CloudProviderService.create_or_update``,
so saved keys produce model entries immediately.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_DISCOVERY_TIMEOUT_SECONDS = 10.0

OPENAI_BASE_URL = "https://api.openai.com/v1"

# Curated chat-model filter for OpenAI's /v1/models (it returns 100+ ids incl.
# tts / transcribe / audio / image / embedding / moderation / instruct /
# search variants and dated snapshots). Keep current general-purpose chat
# models; collapse dated snapshots to their base alias (gpt-4o, not
# gpt-4o-2024-05-13).
_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt")
_NON_CHAT_SUBSTRINGS = (
    "tts", "transcribe", "audio", "realtime", "image", "embedding", "embed",
    "moderation", "instruct", "search", "whisper", "dall", "-edit",
)
_DATE_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$|-\d{4}$")


def _is_current_chat_model(model_id: str) -> bool:
    low = model_id.lower()
    if not low.startswith(_CHAT_PREFIXES):
        return False
    if any(s in low for s in _NON_CHAT_SUBSTRINGS):
        return False
    if _DATE_SNAPSHOT.search(low):  # drop dated snapshots, keep base aliases
        return False
    return True

# (model_short_id, display_name, description)
ANTHROPIC_MODELS: List[Tuple[str, str, str]] = [
    ("claude-sonnet-4-6", "Claude Sonnet 4.6", "Anthropic — fast, balanced"),
    ("claude-opus-4-7", "Claude Opus 4.7", "Anthropic — top-tier reasoning"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5", "Anthropic — fastest"),
]

OPENAI_MODELS: List[Tuple[str, str, str]] = [
    ("gpt-4o", "GPT-4o", "OpenAI — balanced"),
    ("gpt-4o-mini", "GPT-4o mini", "OpenAI — fast/cheap"),
    ("o1-preview", "o1 Preview", "OpenAI — reasoning"),
]

GOOGLE_MODELS: List[Tuple[str, str, str]] = [
    ("gemini-2.0-flash", "Gemini 2.0 Flash", "Google — fast"),
    ("gemini-2.0-pro", "Gemini 2.0 Pro", "Google — top-tier"),
    ("gemini-1.5-pro", "Gemini 1.5 Pro", "Google — long context"),
]

_PROVIDER_CATALOGS: Dict[str, List[Tuple[str, str, str]]] = {
    "anthropic": ANTHROPIC_MODELS,
    "openai": OPENAI_MODELS,
    "google": GOOGLE_MODELS,
}

_PROVIDER_DISPLAY: Dict[str, str] = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
    "openai_compat": "OpenAI-Compatible",
}


async def _discover_openai_compat_models(
    base_url: str, api_key: Optional[str]
) -> List[str]:
    """Fetch model ids from an OpenAI-compatible server's ``/models`` endpoint.

    Raises on connectivity / HTTP error so the caller can preserve existing
    rows rather than wiping them on a transient outage.
    """
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=_DISCOVERY_TIMEOUT_SECONDS) as client:
        resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("data") if isinstance(data, dict) else data
    ids: List[str] = []
    for m in items or []:
        mid = (m or {}).get("id") if isinstance(m, dict) else None
        if mid:
            ids.append(str(mid))
    return ids


async def sync_cloud_models_to_db(db) -> int:
    """Upsert cloud model rows for each connected provider.

    Reads the ``cloud_providers`` collection and, for each row whose
    ``connected`` flag is True, inserts/updates the matching model entries
    in the ``models`` collection. Stale rows for a no-longer-connected
    provider are removed.

    Returns the count of seeded / refreshed model rows.
    """
    providers_coll = db["cloud_providers"]
    models_coll = db["models"]

    # Capture each provider's saved config so we can seed based on the
    # presence of the required credential (api_key), not on the `connected`
    # probe flag — which isn't set on Save, so gating on it left valid keys
    # with no selectable models.
    provider_cfgs: Dict[str, Dict[str, Any]] = {}
    openai_compat_cfg: Optional[Dict[str, Any]] = None
    async for row in providers_coll.find({}):
        ptype = row.get("provider_type")
        if not ptype:
            continue
        provider_cfgs[ptype] = dict(row.get("config") or {})
        if ptype == "openai_compat":
            openai_compat_cfg = dict(row.get("config") or {})

    seeded = 0
    desired_ids: set = set()

    for ptype, catalog in _PROVIDER_CATALOGS.items():
        cfg = provider_cfgs.get(ptype)
        # Static-catalog providers (anthropic/openai/google) need an api_key.
        # No row or no key → skip seeding (stale cleanup below removes any
        # previously-seeded rows for a now-removed provider).
        if not cfg or not cfg.get("api_key"):
            continue

        # OpenAI: discover the account's live models (filtered to current chat
        # models) so the list never rots (e.g. o1-preview being removed). Fall
        # back to the static catalog if discovery fails or returns nothing.
        entries = catalog
        if ptype == "openai":
            try:
                ids = await _discover_openai_compat_models(
                    OPENAI_BASE_URL, cfg.get("api_key")
                )
                chat_ids = sorted(i for i in ids if _is_current_chat_model(i))
                if chat_ids:
                    entries = [(i, i, "OpenAI") for i in chat_ids]
                    logger.info("OpenAI: discovered %d chat models", len(chat_ids))
            except Exception as exc:
                logger.warning(
                    "OpenAI model discovery failed (%s) — using static catalog", exc
                )

        for short_id, display_name, description in entries:
            doc_id = f"{ptype}:{short_id}"
            desired_ids.add(doc_id)
            doc = _build_model_doc(
                doc_id=doc_id,
                provider_type=ptype,
                short_id=short_id,
                display_name=display_name,
                description=description,
            )

            existing = await models_coll.find_one({"_id": doc_id})
            if existing:
                await models_coll.find_one_and_update(
                    {"_id": doc_id},
                    {"$set": doc},
                )
            else:
                doc_to_insert = dict(doc)
                doc_to_insert["_id"] = doc_id
                await models_coll.insert_one(doc_to_insert)
                logger.info("Registered cloud model: %s", doc_id)
            seeded += 1

    # Dynamic discovery for openai_compat — model ids come from the server's
    # own /v1/models, not a static catalog. Gate on the provider row existing
    # (not the `connected` flag): discovery validates connectivity itself, and
    # a freshly-saved provider hasn't been marked connected yet.
    if openai_compat_cfg:
        base_url = openai_compat_cfg.get("base_url") or ""
        api_key = openai_compat_cfg.get("api_key") or None
        discovered: Optional[List[str]] = None
        if base_url:
            try:
                discovered = await _discover_openai_compat_models(base_url, api_key)
            except Exception as exc:
                logger.warning(
                    "openai_compat model discovery failed (%s) — preserving existing rows",
                    exc,
                )
        if discovered is not None:
            for short_id in discovered:
                doc_id = f"openai_compat:{short_id}"
                desired_ids.add(doc_id)
                doc = _build_model_doc(
                    doc_id=doc_id,
                    provider_type="openai_compat",
                    short_id=short_id,
                    display_name=short_id,
                    description="OpenAI-compatible server",
                )
                existing = await models_coll.find_one({"_id": doc_id})
                if existing:
                    await models_coll.find_one_and_update({"_id": doc_id}, {"$set": doc})
                else:
                    doc_to_insert = dict(doc)
                    doc_to_insert["_id"] = doc_id
                    await models_coll.insert_one(doc_to_insert)
                    logger.info("Registered openai_compat model: %s", doc_id)
                seeded += 1
        else:
            # Discovery unavailable: keep whatever openai_compat rows exist so a
            # transient outage doesn't wipe the user's model list.
            async for row in models_coll.find({}):
                rid = row.get("_id") or row.get("id") or ""
                if isinstance(rid, str) and rid.startswith("openai_compat:"):
                    desired_ids.add(rid)

    # Remove stale cloud model rows: any row whose _id starts with a known
    # cloud prefix but no longer corresponds to a connected provider.
    known_prefixes = tuple(f"{p}:" for p in _PROVIDER_CATALOGS) + ("openai_compat:",)
    async for stale in models_coll.find({}):
        stale_id = stale.get("_id") or stale.get("id") or ""
        if not isinstance(stale_id, str):
            continue
        if not stale_id.startswith(known_prefixes):
            continue
        if stale_id in desired_ids:
            continue
        await models_coll.delete_one({"_id": stale_id})
        logger.info("Removed stale cloud model: %s", stale_id)

    if seeded:
        logger.info("Synced %d cloud model row(s) to database", seeded)

    return seeded


def _build_model_doc(
    *,
    doc_id: str,
    provider_type: str,
    short_id: str,
    display_name: str,
    description: str,
) -> Dict[str, Any]:
    return {
        "id": doc_id,
        "name": display_name,
        "description": description,
        "provider": _PROVIDER_DISPLAY.get(provider_type, provider_type.title()),
        "model": short_id,
        "enabled": True,
        "model_metadata": {
            "provider_type": provider_type,
            "hf_filename": None,
        },
    }
