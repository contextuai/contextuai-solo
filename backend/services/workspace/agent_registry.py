"""
Agent Registry Service for AI Team Workspace Feature

Provides a centralized registry for managing and accessing workspace agents,
including dependency validation and execution order recommendations.
"""

import logging
from typing import Dict, Any, List, Optional

from repositories.workspace_agent_repository import WorkspaceAgentRepository

# Configure logging
logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Singleton registry for workspace agents.

    Provides methods for accessing agents, validating dependencies,
    and determining optimal execution order.
    """

    _instance: Optional['AgentRegistry'] = None

    def __new__(cls) -> 'AgentRegistry':
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the agent registry."""
        # Only initialize once
        if not hasattr(self, '_initialized'):
            self._initialized = True
            logger.debug("AgentRegistry initialized")

    async def get_all_agents(
        self,
        agent_repo: WorkspaceAgentRepository
    ) -> List[Dict[str, Any]]:
        """
        Get all active agents from the repository.

        Args:
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            List of all active agent documents
        """
        try:
            agents = await agent_repo.get_all_active()
            logger.debug(f"Retrieved {len(agents)} active agents")
            return agents

        except Exception as e:
            logger.error(f"Error getting all agents: {e}")
            return []

    async def get_agent(
        self,
        agent_id: str,
        agent_repo: WorkspaceAgentRepository
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single agent by ID.

        Args:
            agent_id: ID of the agent
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            Agent document or None if not found
        """
        try:
            agent = await agent_repo.get_by_id(agent_id)
            if agent:
                logger.debug(f"Retrieved agent: {agent.get('name', agent_id)}")
            else:
                logger.warning(f"Agent not found: {agent_id}")
            return agent

        except Exception as e:
            logger.error(f"Error getting agent {agent_id}: {e}")
            return None

    async def get_agents_by_ids(
        self,
        agent_ids: List[str],
        agent_repo: WorkspaceAgentRepository
    ) -> List[Dict[str, Any]]:
        """
        Get multiple agents by their IDs.

        Args:
            agent_ids: List of agent IDs to retrieve
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            List of agent documents (may be fewer than requested if some not found)
        """
        try:
            if not agent_ids:
                return []

            agents = await agent_repo.get_by_ids(agent_ids)

            found_count = len(agents)
            requested_count = len(agent_ids)

            if found_count < requested_count:
                found_ids = {a.get("agent_id") for a in agents}
                missing = set(agent_ids) - found_ids
                logger.warning(f"Some agents not found: {missing}")

            logger.debug(f"Retrieved {found_count}/{requested_count} agents")
            return agents

        except Exception as e:
            logger.error(f"Error getting agents by IDs: {e}")
            return []

    async def validate_execution_order(
        self,
        agent_ids: List[str],
        agent_repo: WorkspaceAgentRepository
    ) -> Dict[str, Any]:
        """
        Validate that agent execution order satisfies dependencies.

        Checks that for each agent, all agents it requires (from agent.config.requires)
        appear earlier in the execution order.

        Args:
            agent_ids: Ordered list of agent IDs
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            Dictionary with 'valid' boolean, 'errors' list, and 'warnings' list
        """
        errors: List[str] = []
        warnings: List[str] = []

        try:
            if not agent_ids:
                return {
                    "valid": False,
                    "errors": ["No agents specified"],
                    "warnings": []
                }

            # Get all agents
            agents = await agent_repo.get_by_ids(agent_ids)
            agent_map = {a.get("agent_id"): a for a in agents}

            # Check if all agents were found
            found_ids = set(agent_map.keys())
            missing = set(agent_ids) - found_ids
            if missing:
                errors.append(f"Agents not found: {', '.join(missing)}")

            # Build set of agents that have appeared before each position
            processed = set()

            for idx, agent_id in enumerate(agent_ids):
                agent = agent_map.get(agent_id)
                if not agent:
                    continue

                # Get agent requirements
                config = agent.get("config", {})
                requires = config.get("requires", [])

                if requires:
                    # Check if all required agents have been processed
                    for required_id in requires:
                        if required_id not in found_ids:
                            warnings.append(
                                f"Agent '{agent.get('name')}' requires '{required_id}' "
                                f"which is not in the team"
                            )
                        elif required_id not in processed:
                            errors.append(
                                f"Agent '{agent.get('name')}' requires '{required_id}' "
                                f"but it appears later in the execution order"
                            )

                processed.add(agent_id)

            is_valid = len(errors) == 0
            logger.debug(f"Execution order validation: valid={is_valid}, errors={len(errors)}")

            return {
                "valid": is_valid,
                "errors": errors,
                "warnings": warnings
            }

        except Exception as e:
            logger.error(f"Error validating execution order: {e}")
            return {
                "valid": False,
                "errors": [f"Validation error: {str(e)}"],
                "warnings": []
            }

    async def get_recommended_order(
        self,
        agent_ids: List[str],
        agent_repo: WorkspaceAgentRepository
    ) -> Dict[str, Any]:
        """
        Get recommended execution order based on agent dependencies.

        Uses topological sort to determine optimal order based on
        agent.config.requires fields.

        Args:
            agent_ids: List of agent IDs to order
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            Dictionary with 'order' list of agent IDs and 'agents' list with details
        """
        try:
            if not agent_ids:
                return {
                    "order": [],
                    "agents": [],
                    "error": None
                }

            # Get all agents
            agents = await agent_repo.get_by_ids(agent_ids)
            agent_map = {a.get("agent_id"): a for a in agents}
            agent_set = set(agent_ids)

            # Build dependency graph
            # graph[agent_id] = list of agent_ids that must come BEFORE this agent
            graph: Dict[str, List[str]] = {}

            for agent_id in agent_ids:
                agent = agent_map.get(agent_id)
                if not agent:
                    graph[agent_id] = []
                    continue

                config = agent.get("config", {})
                requires = config.get("requires", [])

                # Only include requirements that are in our agent set
                graph[agent_id] = [r for r in requires if r in agent_set]

            # Topological sort using Kahn's algorithm
            # Calculate in-degrees
            in_degree: Dict[str, int] = {agent_id: 0 for agent_id in agent_ids}
            for agent_id, deps in graph.items():
                for dep in deps:
                    if dep in in_degree:
                        in_degree[agent_id] = in_degree.get(agent_id, 0) + 1

            # Start with nodes that have no dependencies
            queue = [agent_id for agent_id, degree in in_degree.items() if degree == 0]

            # Sort queue by category priority (architects first, then developers, etc.)
            category_priority = {
                "architect": 1,
                "designer": 2,
                "developer": 3,
                "engineer": 3,
                "tester": 4,
                "reviewer": 5,
                "documenter": 6
            }

            def get_priority(agent_id: str) -> int:
                agent = agent_map.get(agent_id, {})
                category = agent.get("category", "developer")
                return category_priority.get(category, 10)

            queue.sort(key=get_priority)

            ordered: List[str] = []

            while queue:
                # Take agent with no remaining dependencies
                current = queue.pop(0)
                ordered.append(current)

                # Reduce in-degree for agents that depend on current
                for agent_id in agent_ids:
                    if current in graph.get(agent_id, []):
                        in_degree[agent_id] -= 1
                        if in_degree[agent_id] == 0:
                            queue.append(agent_id)
                            queue.sort(key=get_priority)

            # Check for cycles
            if len(ordered) < len(agent_ids):
                # There's a cycle - return original order with warning
                remaining = [a for a in agent_ids if a not in ordered]
                ordered.extend(remaining)
                logger.warning("Circular dependency detected in agent requirements")
                return {
                    "order": ordered,
                    "agents": [agent_map.get(a) for a in ordered if agent_map.get(a)],
                    "warning": "Circular dependency detected; some agents may not execute in optimal order"
                }

            logger.debug(f"Recommended order: {ordered}")

            return {
                "order": ordered,
                "agents": [agent_map.get(a) for a in ordered if agent_map.get(a)],
                "error": None
            }

        except Exception as e:
            logger.error(f"Error getting recommended order: {e}")
            return {
                "order": agent_ids,  # Return original order on error
                "agents": [],
                "error": str(e)
            }

    async def get_agents_by_category(
        self,
        category: str,
        agent_repo: WorkspaceAgentRepository
    ) -> List[Dict[str, Any]]:
        """
        Get agents by category.

        Args:
            category: Agent category (architect, developer, tester, etc.)
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            List of agents in the specified category
        """
        try:
            agents = await agent_repo.get_by_category(category)
            logger.debug(f"Retrieved {len(agents)} agents in category '{category}'")
            return agents

        except Exception as e:
            logger.error(f"Error getting agents by category: {e}")
            return []

    async def get_agents_by_capability(
        self,
        capability: str,
        agent_repo: WorkspaceAgentRepository
    ) -> List[Dict[str, Any]]:
        """
        Get agents with a specific capability.

        Args:
            capability: Capability to search for
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            List of agents with the specified capability
        """
        try:
            agents = await agent_repo.get_by_capability(capability)
            logger.debug(f"Retrieved {len(agents)} agents with capability '{capability}'")
            return agents

        except Exception as e:
            logger.error(f"Error getting agents by capability: {e}")
            return []


# Create singleton instance
agent_registry = AgentRegistry()
