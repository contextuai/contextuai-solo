"""
Phase 3 PR 3 — Inbound Router.

Sits in front of the legacy `trigger_service.check_and_dispatch` path.

When UNIFIED_CREWS=on, an incoming `ChannelMessage` is matched against every
crew that has a `triggers[type=reactive]` entry whose `connection_id` matches
the message's connection AND whose keywords/hashtags/mentions appear in the
message text. Exactly-one match → dispatch immediately. Multi-match → an LLM
disambiguator picks the best crew based on its name/description.

The router is intentionally additive: the call site checks the flag and falls
through to today's path if it's off, or if no reactive crew matches.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Map ChannelType.value → connection_id slug used in crew.triggers.connection_id.
# Single-user desktop = one auth per platform, so the platform name is the id.
PLATFORM_FROM_CHANNEL_TYPE = {
    "telegram": "telegram",
    "discord": "discord",
    "reddit": "reddit",
    "twitter": "twitter",
    "linkedin": "linkedin",
    "instagram": "instagram",
    "facebook": "facebook",
}


def _normalize(text: str) -> str:
    return (text or "").lower().strip()


def _trigger_matches(trigger: Dict[str, Any], text: str) -> bool:
    """Return True if any keyword/hashtag/mention substring-matches the text.

    Match rule: case-insensitive substring. Empty rule lists do not match —
    a reactive trigger with no rules at all should never have been saved
    (Pydantic validator on the model rejects it), but we defend here too.
    """
    haystack = _normalize(text)
    if not haystack:
        return False
    rules: List[str] = []
    rules.extend(trigger.get("keywords") or [])
    rules.extend(trigger.get("hashtags") or [])
    rules.extend(trigger.get("mentions") or [])
    if not rules:
        return False
    return any(_normalize(r) in haystack for r in rules if r and r.strip())


async def find_matching_crews(
    db,
    connection_id: str,
    text: str,
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Return [(crew, matching_trigger)] across all active crews."""
    matches: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    cursor = db["crews"].find({"status": "active"})
    async for crew in cursor:
        triggers = crew.get("triggers") or []
        for trigger in triggers:
            if (trigger or {}).get("type") != "reactive":
                continue
            if trigger.get("connection_id") != connection_id:
                continue
            if _trigger_matches(trigger, text):
                matches.append((crew, trigger))
                break  # one trigger per crew is enough to qualify
    return matches


async def disambiguate_with_llm(
    candidates: List[Dict[str, Any]],
    message_text: str,
) -> Dict[str, Any]:
    """Ask a cheap local model to pick the best crew. Falls back to first match
    on any failure — never block dispatch on LLM availability.
    """
    try:
        from services.local_model_service import LocalModelService
    except Exception:
        return candidates[0]

    try:
        svc = LocalModelService()
    except Exception:
        return candidates[0]

    options_lines = []
    for idx, crew in enumerate(candidates, start=1):
        name = crew.get("name") or "(unnamed)"
        desc = (crew.get("description") or "")[:200].replace("\n", " ")
        options_lines.append(f"{idx}. {name} — {desc}")
    options = "\n".join(options_lines)

    prompt = (
        "You are routing an inbound message to one of several crews.\n"
        "Pick the single best crew and reply with only its number.\n\n"
        f"Message:\n{message_text[:600]}\n\n"
        f"Crews:\n{options}\n\n"
        "Answer with just the number:"
    )

    try:
        # Use whichever local model is loaded; very short generation.
        result = await svc.generate(prompt=prompt, max_tokens=4, temperature=0.0)
        answer = (result or {}).get("response") or (result or {}).get("text") or ""
        match = re.search(r"\d+", answer)
        if match:
            idx = int(match.group(0)) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
    except Exception as exc:
        logger.info("LLM disambiguator unavailable, defaulting to first match: %s", exc)

    return candidates[0]


async def route_inbound(db, msg) -> Optional[Dict[str, Any]]:
    """
    Find a reactive-triggered crew for this message and dispatch it.

    Returns the dispatch result (with status / response / run_id), or None
    if no crew matched — call site should then fall through to the legacy
    trigger_service path.
    """
    channel_value = msg.channel_type.value if hasattr(msg.channel_type, "value") else str(msg.channel_type)
    connection_id = PLATFORM_FROM_CHANNEL_TYPE.get(channel_value)
    if not connection_id:
        return None

    matches = await find_matching_crews(db, connection_id, msg.text)
    if not matches:
        return None

    if len(matches) == 1:
        crew, trigger = matches[0]
    else:
        chosen = await disambiguate_with_llm([c for c, _ in matches], msg.text)
        # Map back to (crew, trigger)
        crew, trigger = next(((c, t) for c, t in matches if c is chosen), matches[0])

    crew_id = crew.get("crew_id")
    user_id = crew.get("user_id") or "desktop-user"

    # Dispatch via crew_service so the run record carries trigger metadata.
    from models.crew_models import RunCrewRequest
    from repositories.crew_repository import CrewRepository, CrewRunRepository
    from repositories.workspace_agent_repository import WorkspaceAgentRepository
    from services.crew_service import CrewService

    crew_repo = CrewRepository(db)
    run_repo = CrewRunRepository(db)
    agent_repo = WorkspaceAgentRepository(db)
    svc = CrewService(crew_repo=crew_repo, run_repo=run_repo, agent_repo=agent_repo)

    request = RunCrewRequest(input=msg.text)
    run = await svc.start_run(
        crew_id=crew_id,
        user_id=user_id,
        request=request,
        trigger_type="reactive",
        trigger_source=connection_id,
    )

    return {
        "status": "dispatched",
        "response": f"Crew '{crew.get('name')}' is processing your message…",
        "run_id": run.get("run_id"),
        "crew_id": crew_id,
        "trigger_source": connection_id,
    }
