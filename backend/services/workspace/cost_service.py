"""
Cost Service for AI Team Workspace Feature

Provides cost estimation, credit calculation, and usage tracking
for workspace project executions.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from repositories.workspace_agent_repository import WorkspaceAgentRepository
from repositories.workspace_usage_repository import WorkspaceUsageRepository

# Configure logging
logger = logging.getLogger(__name__)


class CostService:
    """
    Service for cost estimation and usage tracking.

    Provides methods for calculating LLM costs, converting to credits,
    and tracking user usage.
    """

    # Credit value in USD
    CREDIT_VALUE_USD = 0.10

    # Complexity multipliers
    COMPLEXITY_MULTIPLIERS = {
        "simple": 0.5,
        "medium": 1.0,
        "complex": 2.0,
        "enterprise": 5.0
    }

    # Base token estimates per agent type/category
    BASE_TOKEN_ESTIMATES = {
        # Engineering categories
        "architect": {"input": 2000, "output": 4000},
        "designer": {"input": 1500, "output": 3000},
        "developer": {"input": 3000, "output": 6000},
        "engineer": {"input": 3000, "output": 6000},
        "tester": {"input": 2000, "output": 3000},
        "reviewer": {"input": 4000, "output": 2000},
        "documenter": {"input": 2000, "output": 5000},
        # Business categories
        "c_suite": {"input": 2000, "output": 3000},
        "startup_venture": {"input": 1500, "output": 2500},
        "marketing_sales": {"input": 1500, "output": 2500},
        "product_management": {"input": 1500, "output": 2500},
        "finance_operations": {"input": 1500, "output": 2000},
        "hr_people": {"input": 1200, "output": 2000},
        "legal_compliance": {"input": 1500, "output": 2500},
        "it_security": {"input": 2000, "output": 3000},
        "data_analytics": {"input": 2000, "output": 3000},
        "specialized": {"input": 1500, "output": 2500},
        "engineering": {"input": 3000, "output": 6000},
        "default": {"input": 2000, "output": 4000}
    }

    # Model pricing per 1M tokens (input/output in USD)
    MODEL_PRICING = {
        "anthropic.claude-3-5-sonnet-20241022-v2:0": {"input": 3.00, "output": 15.00},
        "anthropic.claude-3-5-haiku-20241022-v1:0": {"input": 0.80, "output": 4.00},
        "anthropic.claude-3-opus-20240229-v1:0": {"input": 15.00, "output": 75.00},
        "anthropic.claude-3-sonnet-20240229-v1:0": {"input": 3.00, "output": 15.00},
        "anthropic.claude-3-haiku-20240307-v1:0": {"input": 0.25, "output": 1.25},
        "amazon.titan-text-lite-v1": {"input": 0.30, "output": 0.40},
        "amazon.titan-text-express-v1": {"input": 0.80, "output": 1.60},
        # Claude Agent SDK short-form model IDs
        "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
        "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
        "claude-opus-4-6": {"input": 15.00, "output": 75.00},
        "default": {"input": 1.00, "output": 3.00}
    }

    async def estimate_cost(
        self,
        agent_ids: List[str],
        complexity: str,
        agent_repo: WorkspaceAgentRepository
    ) -> Dict[str, Any]:
        """
        Calculate LLM cost estimate for project execution.

        Args:
            agent_ids: List of agent IDs in the project team
            complexity: Project complexity level
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            Dictionary with cost breakdown
        """
        try:
            # Get agents
            agents = await agent_repo.get_by_ids(agent_ids)

            # Get complexity multiplier
            multiplier = self.get_complexity_multiplier(complexity)

            total_input_tokens = 0
            total_output_tokens = 0
            agent_estimates = []

            for agent in agents:
                category = agent.get("category", "default")
                token_estimates = self.BASE_TOKEN_ESTIMATES.get(
                    category,
                    self.BASE_TOKEN_ESTIMATES["default"]
                )

                # Apply complexity multiplier
                input_tokens = int(token_estimates["input"] * multiplier)
                output_tokens = int(token_estimates["output"] * multiplier)

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens

                # Get model for agent
                model_id = agent.get("model_id", "default")
                pricing = self.MODEL_PRICING.get(model_id, self.MODEL_PRICING["default"])

                # Calculate cost for this agent
                agent_cost_usd = (
                    (input_tokens / 1_000_000) * pricing["input"] +
                    (output_tokens / 1_000_000) * pricing["output"]
                )

                agent_estimates.append({
                    "agent_id": agent.get("agent_id"),
                    "agent_name": agent.get("name"),
                    "category": category,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "estimated_cost_usd": round(agent_cost_usd, 4)
                })

            # Calculate total cost
            # Using default pricing for total estimate
            default_pricing = self.MODEL_PRICING["default"]
            total_cost_usd = (
                (total_input_tokens / 1_000_000) * default_pricing["input"] +
                (total_output_tokens / 1_000_000) * default_pricing["output"]
            )

            # Convert to credits
            credits_required = self.calculate_credits_required(total_cost_usd)

            logger.debug(
                f"Cost estimate: {credits_required} credits (${total_cost_usd:.4f}) "
                f"for {len(agents)} agents at {complexity} complexity"
            )

            return {
                "credits_required": credits_required,
                "estimated_cost_usd": round(total_cost_usd, 4),
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "complexity": complexity,
                "complexity_multiplier": multiplier,
                "agent_estimates": agent_estimates,
                "agent_count": len(agents)
            }

        except Exception as e:
            logger.error(f"Error estimating cost: {e}")
            return {
                "credits_required": 0,
                "estimated_cost_usd": 0.0,
                "error": str(e)
            }

    def calculate_credits_required(self, cost_usd: float) -> int:
        """
        Convert USD cost to credits.

        Args:
            cost_usd: Cost in USD

        Returns:
            Number of credits required (rounded up)
        """
        if cost_usd <= 0:
            return 0

        # Round up to ensure we have enough credits
        import math
        credits = math.ceil(cost_usd / self.CREDIT_VALUE_USD)

        # Minimum of 1 credit for any non-zero cost
        return max(1, credits)

    def get_complexity_multiplier(self, complexity: str) -> float:
        """
        Get the multiplier for a complexity level.

        Args:
            complexity: Complexity level string

        Returns:
            Multiplier value (defaults to 1.0 for unknown complexity)
        """
        return self.COMPLEXITY_MULTIPLIERS.get(complexity, 1.0)

    async def track_usage(
        self,
        user_id: str,
        credits_used: int,
        cost_usd: float,
        usage_repo: WorkspaceUsageRepository
    ) -> Dict[str, Any]:
        """
        Record usage for billing tracking.

        Args:
            user_id: ID of the user
            credits_used: Number of credits consumed
            cost_usd: Actual cost in USD
            usage_repo: WorkspaceUsageRepository instance

        Returns:
            Updated usage record
        """
        try:
            # Get current month
            month = datetime.utcnow().strftime("%Y-%m")

            # Update usage
            result = await usage_repo.update_usage(
                user_id=user_id,
                month=month,
                credits_used=credits_used,
                cost=cost_usd
            )

            if result:
                logger.info(
                    f"Usage tracked for user {user_id}: "
                    f"{credits_used} credits (${cost_usd:.4f})"
                )
                return {
                    "success": True,
                    "usage": result,
                    "credits_used": credits_used,
                    "cost_usd": cost_usd
                }
            else:
                logger.warning(f"Failed to track usage for user {user_id}")
                return {
                    "success": False,
                    "error": "Failed to update usage record"
                }

        except Exception as e:
            logger.error(f"Error tracking usage: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_user_usage(
        self,
        user_id: str,
        usage_repo: WorkspaceUsageRepository
    ) -> Dict[str, Any]:
        """
        Get current month usage for a user.

        Args:
            user_id: ID of the user
            usage_repo: WorkspaceUsageRepository instance

        Returns:
            Usage summary for current month
        """
        try:
            # Get current month
            month = datetime.utcnow().strftime("%Y-%m")

            # Get usage record
            usage = await usage_repo.get_user_usage(user_id, month)

            if not usage:
                # No usage record - return defaults
                return {
                    "user_id": user_id,
                    "month": month,
                    "credits_allocated": 0,
                    "credits_used": 0,
                    "credits_remaining": 0,
                    "total_cost_usd": 0.0,
                    "execution_count": 0,
                    "plan_type": "free"
                }

            # Calculate remaining credits
            credits_allocated = usage.get("credits_allocated", 0)
            credits_used = usage.get("credits_used", 0)
            credits_remaining = max(0, credits_allocated - credits_used)

            logger.debug(
                f"User {user_id} usage: {credits_used}/{credits_allocated} credits "
                f"(${usage.get('total_cost', 0.0):.2f})"
            )

            return {
                "user_id": user_id,
                "month": month,
                "credits_allocated": credits_allocated,
                "credits_used": credits_used,
                "credits_remaining": credits_remaining,
                "total_cost_usd": usage.get("total_cost", 0.0),
                "execution_count": usage.get("execution_count", 0),
                "plan_type": usage.get("plan_type", "free"),
                "last_execution": usage.get("last_execution")
            }

        except Exception as e:
            logger.error(f"Error getting user usage: {e}")
            return {
                "user_id": user_id,
                "error": str(e)
            }

    async def has_sufficient_credits(
        self,
        user_id: str,
        credits_needed: int,
        usage_repo: WorkspaceUsageRepository
    ) -> bool:
        """
        Check if user has enough credits for an operation.

        Args:
            user_id: ID of the user
            credits_needed: Number of credits required
            usage_repo: WorkspaceUsageRepository instance

        Returns:
            True if user has sufficient credits
        """
        try:
            return await usage_repo.has_available_credits(user_id, credits_needed)

        except Exception as e:
            logger.error(f"Error checking credits: {e}")
            return False

    def calculate_actual_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Calculate actual cost based on token usage.

        Args:
            model_id: ID of the model used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        pricing = self.MODEL_PRICING.get(model_id, self.MODEL_PRICING["default"])

        cost_usd = (
            (input_tokens / 1_000_000) * pricing["input"] +
            (output_tokens / 1_000_000) * pricing["output"]
        )

        return round(cost_usd, 6)


# Create singleton instance
cost_service = CostService()
