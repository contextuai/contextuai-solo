"""
Sample Crew Seeder — preloads a couple of ready-to-run example crews so new
users can see how Crews work (and the writer -> reviewer -> finalizer pattern)
without building one from scratch.

Unlike ``crew_template_seeder`` (which fills the unused ``crew_templates``
collection), this seeds real, runnable crews into the ``crews`` collection for
the desktop user, so they appear directly on the Crews page.

Idempotency
-----------
Seeding runs once ever, gated by a flag doc in ``app_meta``. This means a user
who deletes a sample crew won't have it silently reappear on the next launch.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DESKTOP_USER_ID = "desktop-user"
SEED_FLAG_ID = "sample_crews_seeded_v1"

# A finalizer turns the reviewer's critique into the finished deliverable.
# Kept in sync with the frontend crew-builder FINALIZER_INSTRUCTIONS.
FINALIZER_INSTRUCTIONS = (
    "You are the Finalizer for this crew. You receive the previous draft and "
    "the reviewer's feedback. Apply the feedback and produce the FINAL, "
    "ready-to-publish deliverable.\n\n"
    "Output ONLY the finished result exactly as it should be delivered — no "
    "preamble, scorecard, headings, or commentary. Do not write 'Here is' or "
    "'Final version:'. Return just the deliverable itself."
)

# Each sample is a list of steps. A step either references a library agent by
# id (its system_prompt becomes the instructions) or is the custom finalizer.
SAMPLE_CREWS: List[Dict[str, Any]] = [
    {
        "name": "LinkedIn Content Pipeline (Sample)",
        "description": (
            "A 3-step content team: a Social Media Manager drafts a LinkedIn "
            "post, a Brand Voice Guardian reviews it, and a Finalizer applies "
            "the feedback to produce a publish-ready post."
        ),
        "mode": "sequential",
        "tags": ["sample", "content", "linkedin"],
        "steps": [
            {"library_agent_id": "marketing_sales-social-media-manager", "role": "writer"},
            {"library_agent_id": "social_engagement-brand-voice-guardian", "role": "reviewer"},
            {"finalizer": True},
        ],
    },
    {
        "name": "Blog → Social Repurposer (Sample)",
        "description": (
            "Turns a piece of source content into a polished social post: a "
            "Content Repurposer adapts it, a Brand Voice Guardian reviews, and "
            "a Finalizer outputs the ready-to-post version."
        ),
        "mode": "sequential",
        "tags": ["sample", "content", "repurpose"],
        "steps": [
            {"library_agent_id": "social_engagement-content-repurposer", "role": "writer"},
            {"library_agent_id": "social_engagement-brand-voice-guardian", "role": "reviewer"},
            {"finalizer": True},
        ],
    },
]


async def _already_seeded(db) -> bool:
    try:
        doc = await db["app_meta"].find_one({"_id": SEED_FLAG_ID})
        return doc is not None
    except Exception:
        return False


async def _mark_seeded(db) -> None:
    try:
        await db["app_meta"].insert_one(
            {"_id": SEED_FLAG_ID, "seeded_at": datetime.utcnow().isoformat()}
        )
    except Exception:
        logger.debug("Could not write sample-crew seed flag", exc_info=True)


async def _build_agent(
    step: Dict[str, Any], order: int, agent_repo
) -> Optional[Dict[str, Any]]:
    """Resolve one step into a crew agent config, or None if unresolvable."""
    if step.get("finalizer"):
        return {
            "name": "Finalizer",
            "role": "editor",
            "instructions": FINALIZER_INSTRUCTIONS,
            "order": order,
        }

    lib_id = step.get("library_agent_id")
    lib_agent = await agent_repo.get_by_id(lib_id)
    if not lib_agent or not lib_agent.get("system_prompt"):
        logger.warning(
            "Sample crew seeder: library agent '%s' not found — skipping sample", lib_id
        )
        return None

    return {
        "name": lib_agent.get("name") or lib_id,
        "role": step.get("role", "custom"),
        "instructions": lib_agent["system_prompt"],
        "library_agent_id": lib_id,
        "order": order,
    }


async def seed_sample_crews(db) -> int:
    """Seed the example crews once. Returns the number created."""
    try:
        from repositories.crew_repository import CrewRepository
        from repositories.workspace_agent_repository import WorkspaceAgentRepository

        if await _already_seeded(db):
            return 0

        crew_repo = CrewRepository(db)
        agent_repo = WorkspaceAgentRepository(db)

        created = 0
        for sample in SAMPLE_CREWS:
            # Skip if a crew with this name already exists for the user.
            existing = await crew_repo.get_by_name(DESKTOP_USER_ID, sample["name"])
            if existing:
                continue

            agents: List[Dict[str, Any]] = []
            ok = True
            for i, step in enumerate(sample["steps"]):
                agent = await _build_agent(step, i, agent_repo)
                if agent is None:
                    ok = False
                    break
                agents.append(agent)
            if not ok:
                continue

            crew_data = {
                "name": sample["name"],
                "description": sample["description"],
                "agents": agents,
                "execution_config": {"mode": sample["mode"], "timeout_seconds": 600},
                "memory_enabled": True,
                "tags": sample.get("tags", []),
                "kind": "crew",
            }
            await crew_repo.create_crew(DESKTOP_USER_ID, crew_data)
            created += 1
            logger.info("Seeded sample crew: %s", sample["name"])

        await _mark_seeded(db)
        return created
    except Exception:
        logger.exception("Failed to seed sample crews (non-fatal)")
        return 0
