"""
Complexity Analyzer Service for Smart Model Routing

Heuristic-based scoring that determines task complexity and recommends
the optimal Claude model (Haiku/Sonnet/Opus) — no AI calls needed.

Score thresholds:
  < 25  → Haiku (fast, cheap)
  25-70 → Sonnet (balanced)
  > 70  → Opus (most capable)
"""

import logging
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Model IDs mapped by tier
TIER_MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

# Reasoning keywords that suggest higher complexity
REASONING_KEYWORDS = [
    "analyze", "compare", "design", "architect", "complex",
    "evaluate", "synthesize", "critique", "optimize", "strategize",
    "debug", "refactor", "migrate", "integrate", "security",
]

# Agent categories that inherently require stronger models
HIGH_COMPLEXITY_CATEGORIES = {"architect", "reviewer", "c_suite", "legal_compliance"}


class ComplexityAnalyzer:
    """Heuristic-based complexity scorer for Smart Model Routing."""

    def analyze(
        self,
        prompt: str = "",
        agent_count: int = 1,
        agent_category: Optional[str] = None,
        agent_categories: Optional[List[str]] = None,
        file_count: int = 0,
        migration_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Score task complexity and recommend a model.

        Args:
            prompt: The user prompt or task description
            agent_count: Number of agents involved
            agent_category: Single agent category (for single-agent tasks)
            agent_categories: List of agent categories (for multi-agent tasks)
            file_count: Number of files involved (CodeMorph)
            migration_type: Migration type string (CodeMorph)
            context: Additional context dict

        Returns:
            {score, model_id, tier, reason}
        """
        score = 0
        reasons = []

        # 1. Prompt length scoring
        word_count = len(prompt.split()) if prompt else 0
        if word_count < 50:
            score += 5
            reasons.append(f"short prompt ({word_count} words)")
        elif word_count <= 200:
            score += 15
            reasons.append(f"medium prompt ({word_count} words)")
        else:
            score += 25
            reasons.append(f"long prompt ({word_count} words)")

        # 2. Reasoning keyword scoring (cap at 25)
        keyword_score = 0
        matched_keywords = []
        prompt_lower = prompt.lower() if prompt else ""
        for keyword in REASONING_KEYWORDS:
            if keyword in prompt_lower:
                keyword_score += 5
                matched_keywords.append(keyword)
        keyword_score = min(keyword_score, 25)
        score += keyword_score
        if matched_keywords:
            reasons.append(f"reasoning keywords: {', '.join(matched_keywords[:5])}")

        # 3. Agent count scoring
        if agent_count <= 1:
            score += 5
        elif agent_count <= 3:
            score += 15
            reasons.append(f"{agent_count} agents")
        else:
            score += 25
            reasons.append(f"{agent_count} agents (complex team)")

        # 4. Agent category bonus
        categories = set()
        if agent_category:
            categories.add(agent_category.lower())
        if agent_categories:
            categories.update(c.lower() for c in agent_categories)

        high_cats = categories & HIGH_COMPLEXITY_CATEGORIES
        if high_cats:
            score += 10
            reasons.append(f"high-complexity role: {', '.join(high_cats)}")

        # 5. CodeMorph-specific scoring
        if file_count > 20:
            score += 15
            reasons.append(f"large codebase ({file_count} files)")

        if migration_type and migration_type.lower() in ("framework_migration", "code_conversion"):
            score += 15
            reasons.append(f"complex migration: {migration_type}")

        # Determine tier and model
        if score > 70:
            tier = "opus"
        elif score >= 25:
            tier = "sonnet"
        else:
            tier = "haiku"

        model_id = TIER_MODEL_MAP[tier]

        result = {
            "score": score,
            "model_id": model_id,
            "tier": tier,
            "reason": "; ".join(reasons) if reasons else "default scoring",
        }

        logger.info(f"Complexity analysis: score={score}, tier={tier}, model={model_id} ({'; '.join(reasons)})")
        return result


# Singleton
complexity_analyzer = ComplexityAnalyzer()
