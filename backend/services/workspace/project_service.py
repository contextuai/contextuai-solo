"""
Project Service for AI Team Workspace Feature

Provides business logic for validating and managing workspace projects,
including team composition validation and credit checks.
"""

import logging
from typing import Dict, Any, List, Optional

from repositories.workspace_project_repository import WorkspaceProjectRepository
from repositories.workspace_agent_repository import WorkspaceAgentRepository
from repositories.workspace_usage_repository import WorkspaceUsageRepository

# Configure logging
logger = logging.getLogger(__name__)


class ProjectService:
    """
    Service for workspace project management.

    Provides methods for validating project configurations, team composition,
    and credit checks before project execution.
    """

    # Valid complexity levels
    COMPLEXITY_LEVELS = ["simple", "medium", "complex", "enterprise"]

    # Minimum and maximum team sizes
    MIN_TEAM_SIZE = 1
    MAX_TEAM_SIZE = 10

    # Valid project statuses
    VALID_STATUSES = ["active", "archived", "completed", "paused"]

    async def validate_project(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate project configuration data.

        Args:
            project_data: Project configuration to validate

        Returns:
            Dictionary with 'valid' boolean and 'errors' list
        """
        errors: List[str] = []

        try:
            # Check required fields
            required_fields = ["name", "description", "tech_stack", "complexity", "team_agent_ids"]
            for field in required_fields:
                if field not in project_data or not project_data.get(field):
                    errors.append(f"Missing required field: {field}")

            # Validate name length
            name = project_data.get("name", "")
            if name and (len(name) < 3 or len(name) > 100):
                errors.append("Project name must be between 3 and 100 characters")

            # Validate description length
            description = project_data.get("description", "")
            if description and len(description) > 2000:
                errors.append("Description must not exceed 2000 characters")

            # Validate complexity level
            complexity = project_data.get("complexity", "")
            if complexity and complexity not in self.COMPLEXITY_LEVELS:
                errors.append(f"Invalid complexity level. Must be one of: {', '.join(self.COMPLEXITY_LEVELS)}")

            # Validate tech stack
            tech_stack = project_data.get("tech_stack", [])
            if tech_stack and not isinstance(tech_stack, list):
                errors.append("tech_stack must be a list")
            elif tech_stack and len(tech_stack) > 20:
                errors.append("tech_stack cannot exceed 20 items")

            # Validate team size
            team_agent_ids = project_data.get("team_agent_ids", [])
            if team_agent_ids:
                if not isinstance(team_agent_ids, list):
                    errors.append("team_agent_ids must be a list")
                elif len(team_agent_ids) < self.MIN_TEAM_SIZE:
                    errors.append(f"Team must have at least {self.MIN_TEAM_SIZE} agent")
                elif len(team_agent_ids) > self.MAX_TEAM_SIZE:
                    errors.append(f"Team cannot exceed {self.MAX_TEAM_SIZE} agents")
                elif len(team_agent_ids) != len(set(team_agent_ids)):
                    errors.append("Duplicate agents in team_agent_ids")

            logger.debug(f"Project validation result: valid={len(errors) == 0}, errors={errors}")

            return {
                "valid": len(errors) == 0,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"Error validating project: {e}")
            return {
                "valid": False,
                "errors": [f"Validation error: {str(e)}"]
            }

    async def validate_team_composition(
        self,
        agent_ids: List[str],
        agent_repo: WorkspaceAgentRepository
    ) -> Dict[str, Any]:
        """
        Validate team agent composition and compatibility.

        Checks that all agents exist, are active, and can work together.

        Args:
            agent_ids: List of agent IDs to validate
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            Dictionary with 'valid' boolean, 'errors' list, and 'agents' list
        """
        errors: List[str] = []
        agents: List[Dict[str, Any]] = []

        try:
            if not agent_ids:
                return {
                    "valid": False,
                    "errors": ["No agents specified"],
                    "agents": []
                }

            # Fetch all agents
            agents = await agent_repo.get_by_ids(agent_ids)

            # Check if all agents were found
            found_ids = {agent.get("agent_id") for agent in agents}
            missing_ids = set(agent_ids) - found_ids
            if missing_ids:
                errors.append(f"Agents not found: {', '.join(missing_ids)}")

            # Check if all agents are active
            inactive_agents = [
                agent.get("name", agent.get("agent_id"))
                for agent in agents
                if not agent.get("is_active", False)
            ]
            if inactive_agents:
                errors.append(f"Inactive agents: {', '.join(inactive_agents)}")

            # Check for required agent categories (at least one developer-type)
            categories = {agent.get("category") for agent in agents}
            developer_categories = {"developer", "architect", "engineer"}
            if not categories.intersection(developer_categories):
                errors.append("Team must include at least one developer, architect, or engineer agent")

            logger.debug(f"Team composition validation: valid={len(errors) == 0}, agent_count={len(agents)}")

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "agents": agents
            }

        except Exception as e:
            logger.error(f"Error validating team composition: {e}")
            return {
                "valid": False,
                "errors": [f"Validation error: {str(e)}"],
                "agents": []
            }

    async def check_credits(
        self,
        user_id: str,
        agent_ids: List[str],
        complexity: str,
        usage_repo: WorkspaceUsageRepository
    ) -> Dict[str, Any]:
        """
        Verify user has enough credits for project execution.

        Args:
            user_id: ID of the user
            agent_ids: List of agent IDs in the project team
            complexity: Project complexity level
            usage_repo: WorkspaceUsageRepository instance

        Returns:
            Dictionary with 'has_credits' boolean, 'required' int, 'available' int
        """
        try:
            # Calculate estimated credits required
            estimated_credits = await self._estimate_credits(agent_ids, complexity)

            # Get available credits
            available_credits = await usage_repo.get_remaining_credits(user_id)

            has_credits = available_credits >= estimated_credits

            logger.debug(
                f"Credit check for user {user_id}: required={estimated_credits}, "
                f"available={available_credits}, has_credits={has_credits}"
            )

            return {
                "has_credits": has_credits,
                "required": estimated_credits,
                "available": available_credits,
                "shortfall": max(0, estimated_credits - available_credits)
            }

        except Exception as e:
            logger.error(f"Error checking credits: {e}")
            return {
                "has_credits": False,
                "required": 0,
                "available": 0,
                "shortfall": 0,
                "error": str(e)
            }

    async def calculate_estimated_cost(
        self,
        agent_ids: List[str],
        complexity: str,
        agent_repo: WorkspaceAgentRepository
    ) -> Dict[str, Any]:
        """
        Calculate cost estimate for project execution.

        Args:
            agent_ids: List of agent IDs in the project team
            complexity: Project complexity level
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            Dictionary with cost breakdown by agent and total
        """
        try:
            # Get agents
            agents = await agent_repo.get_by_ids(agent_ids)

            # Base cost per agent per complexity level
            complexity_multipliers = {
                "simple": 0.5,
                "medium": 1.0,
                "complex": 2.0,
                "enterprise": 5.0
            }
            multiplier = complexity_multipliers.get(complexity, 1.0)

            # Base cost per agent (in credits)
            base_cost_per_agent = 10

            agent_costs = []
            total_credits = 0

            for agent in agents:
                agent_cost = int(base_cost_per_agent * multiplier)
                total_credits += agent_cost
                agent_costs.append({
                    "agent_id": agent.get("agent_id"),
                    "agent_name": agent.get("name"),
                    "category": agent.get("category"),
                    "credits": agent_cost
                })

            # Calculate USD cost (assuming $0.10 per credit)
            credit_value_usd = 0.10
            total_usd = total_credits * credit_value_usd

            logger.debug(f"Cost estimate: {total_credits} credits (${total_usd:.2f})")

            return {
                "total_credits": total_credits,
                "total_usd": total_usd,
                "complexity": complexity,
                "complexity_multiplier": multiplier,
                "agent_costs": agent_costs,
                "agent_count": len(agents)
            }

        except Exception as e:
            logger.error(f"Error calculating estimated cost: {e}")
            return {
                "total_credits": 0,
                "total_usd": 0.0,
                "error": str(e)
            }

    async def get_project_with_agents(
        self,
        project_id: str,
        project_repo: WorkspaceProjectRepository,
        agent_repo: WorkspaceAgentRepository
    ) -> Optional[Dict[str, Any]]:
        """
        Get project with resolved agent details.

        Args:
            project_id: ID of the project
            project_repo: WorkspaceProjectRepository instance
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            Project document with 'agents' field containing full agent details,
            or None if project not found
        """
        try:
            # Get project
            project = await project_repo.get_by_id(project_id)
            if not project:
                logger.warning(f"Project not found: {project_id}")
                return None

            # Get agents
            agent_ids = project.get("team_agent_ids", [])
            if agent_ids:
                agents = await agent_repo.get_by_ids(agent_ids)
                project["agents"] = agents
            else:
                project["agents"] = []

            logger.debug(f"Retrieved project {project_id} with {len(project['agents'])} agents")

            return project

        except Exception as e:
            logger.error(f"Error getting project with agents: {e}")
            return None

    async def _estimate_credits(self, agent_ids: List[str], complexity: str) -> int:
        """
        Internal method to estimate credits required.

        Args:
            agent_ids: List of agent IDs
            complexity: Project complexity level

        Returns:
            Estimated credits required
        """
        complexity_multipliers = {
            "simple": 0.5,
            "medium": 1.0,
            "complex": 2.0,
            "enterprise": 5.0
        }
        multiplier = complexity_multipliers.get(complexity, 1.0)
        base_cost_per_agent = 10

        return int(len(agent_ids) * base_cost_per_agent * multiplier)


# Create singleton instance
project_service = ProjectService()
