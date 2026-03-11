"""
Shared Claude Models Utility

Provides available Claude model definitions for non-chat modules
(Workspace, Automations, CodeMorph) that use Claude Agent SDK directly.

Includes Smart Model Routing: when model_id is "auto", the complexity
analyzer picks Haiku/Sonnet/Opus based on task context.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

AUTO_MODEL_ID = "auto"

# Claude models available for agent-based modules
CLAUDE_AGENT_MODELS = [
    {
        "model_id": "claude-sonnet-4-6",
        "name": "Claude Sonnet 4.6",
        "label": "Claude Sonnet 4.6 (Recommended)",
        "description": "Balanced performance and cost. Best for most tasks.",
        "tier": "recommended",
        "input_cost_per_1k": 0.003,
        "output_cost_per_1k": 0.015,
    },
    {
        "model_id": "claude-haiku-4-5-20251001",
        "name": "Claude Haiku 4.5",
        "label": "Claude Haiku 4.5 (Faster)",
        "description": "Fastest response time, lower cost. Good for simple tasks.",
        "tier": "fast",
        "input_cost_per_1k": 0.001,
        "output_cost_per_1k": 0.005,
    },
    {
        "model_id": "claude-opus-4-6",
        "name": "Claude Opus 4.6",
        "label": "Claude Opus 4.6 (Most Capable)",
        "description": "Most capable model. Best for complex reasoning and analysis.",
        "tier": "premium",
        "input_cost_per_1k": 0.015,
        "output_cost_per_1k": 0.075,
    },
]

DEFAULT_MODEL_ID = "claude-sonnet-4-6"


def get_available_models() -> List[Dict[str, Any]]:
    """Return list of available Claude models for agent-based modules."""
    return CLAUDE_AGENT_MODELS


def get_model_by_id(model_id: str) -> Optional[Dict[str, Any]]:
    """Look up a Claude model by its model_id."""
    for model in CLAUDE_AGENT_MODELS:
        if model["model_id"] == model_id:
            return model
    return None


def is_auto_model(model_id: Optional[str]) -> bool:
    """Check if the model_id is the auto/smart routing sentinel."""
    return model_id == AUTO_MODEL_ID


def resolve_auto_model(
    prompt: str = "",
    agent_count: int = 1,
    agent_category: Optional[str] = None,
    agent_categories: Optional[List[str]] = None,
    file_count: int = 0,
    migration_type: Optional[str] = None,
) -> str:
    """
    Resolve 'auto' model_id to a concrete model using the complexity analyzer.

    Returns the resolved model_id (e.g., 'claude-sonnet-4-6').
    """
    from services.complexity_analyzer import complexity_analyzer

    result = complexity_analyzer.analyze(
        prompt=prompt,
        agent_count=agent_count,
        agent_category=agent_category,
        agent_categories=agent_categories,
        file_count=file_count,
        migration_type=migration_type,
    )

    resolved = result["model_id"]
    logger.info(
        f"Auto-resolved model: {resolved} (score={result['score']}, "
        f"tier={result['tier']}, reason={result['reason']})"
    )
    return resolved


def validate_model_id(model_id: Optional[str]) -> str:
    """
    Validate and resolve a model_id.

    Returns the model_id if valid, 'auto' if auto, or the default model_id if None/invalid.
    """
    if not model_id:
        return DEFAULT_MODEL_ID
    if is_auto_model(model_id):
        return AUTO_MODEL_ID
    model = get_model_by_id(model_id)
    if model:
        return model_id
    # Fall back to default if invalid
    return DEFAULT_MODEL_ID
