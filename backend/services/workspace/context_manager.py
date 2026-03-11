"""
Context Manager for AI Team Workspace Feature

Manages execution context that flows between agents during workspace execution.
Tracks agent outputs, files created, and shared state.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from copy import deepcopy

# Configure logging
logger = logging.getLogger(__name__)


class ContextManager:
    """
    Manager for workspace execution context.

    Maintains the shared context that flows between agents during execution,
    including outputs, files created, and any shared state.
    """

    def __init__(self):
        """Initialize an empty context manager."""
        self._context: Dict[str, Any] = {
            "agent_outputs": {},
            "files_created": {},
            "shared_state": {},
            "execution_metadata": {
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
        }
        logger.debug("ContextManager initialized")

    def add_agent_output(
        self,
        agent_id: str,
        output: str,
        files_created: Optional[List[Dict[str, str]]] = None
    ) -> None:
        """
        Add an agent's output to the context.

        Args:
            agent_id: ID of the agent that produced the output
            output: The agent's text output
            files_created: Optional list of files created by the agent
                Each file dict should have 'filename' and 'content' keys
        """
        try:
            # Store agent output
            self._context["agent_outputs"][agent_id] = {
                "output": output,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Store files created by this agent
            if files_created:
                self._context["files_created"][agent_id] = files_created

                # Log file creation
                file_names = [f.get("filename", "unknown") for f in files_created]
                logger.debug(f"Agent {agent_id} created files: {file_names}")

            # Update metadata
            self._context["execution_metadata"]["updated_at"] = datetime.utcnow().isoformat()

            logger.info(f"Added output from agent {agent_id} to context")

        except Exception as e:
            logger.error(f"Error adding agent output to context: {e}")

    def get_context_for_agent(
        self,
        agent_id: str,
        agent_blueprint: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get relevant context for a specific agent.

        Filters the full context based on the agent's configuration,
        including outputs from agents it depends on.

        Args:
            agent_id: ID of the agent requesting context
            agent_blueprint: The agent's configuration/blueprint

        Returns:
            Dictionary with context relevant to this agent
        """
        try:
            # Get agent dependencies
            config = agent_blueprint.get("config", {})
            requires = config.get("requires", [])
            context_requirements = config.get("context_requirements", [])

            # Build filtered context
            filtered_context: Dict[str, Any] = {
                "previous_outputs": {},
                "available_files": [],
                "shared_state": self._context.get("shared_state", {})
            }

            # Include outputs from required agents
            for required_agent_id in requires:
                if required_agent_id in self._context["agent_outputs"]:
                    filtered_context["previous_outputs"][required_agent_id] = \
                        self._context["agent_outputs"][required_agent_id]

            # Include all files created so far
            all_files = []
            for agent_files in self._context["files_created"].values():
                all_files.extend(agent_files)
            filtered_context["available_files"] = all_files

            # Include any specifically requested context
            for req in context_requirements:
                if req in self._context:
                    filtered_context[req] = self._context[req]

            logger.debug(
                f"Built context for agent {agent_id} with "
                f"{len(filtered_context['previous_outputs'])} previous outputs and "
                f"{len(filtered_context['available_files'])} available files"
            )

            return filtered_context

        except Exception as e:
            logger.error(f"Error getting context for agent: {e}")
            return {
                "previous_outputs": {},
                "available_files": [],
                "shared_state": {}
            }

    def get_full_context(self) -> Dict[str, Any]:
        """
        Get the complete execution context.

        Returns:
            Dictionary with all context data
        """
        return deepcopy(self._context)

    def set_shared_state(self, key: str, value: Any) -> None:
        """
        Set a value in the shared state.

        Args:
            key: State key
            value: State value
        """
        self._context["shared_state"][key] = value
        self._context["execution_metadata"]["updated_at"] = datetime.utcnow().isoformat()
        logger.debug(f"Set shared state key '{key}'")

    def get_shared_state(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the shared state.

        Args:
            key: State key
            default: Default value if key not found

        Returns:
            State value or default
        """
        return self._context["shared_state"].get(key, default)

    def get_all_files(self) -> List[Dict[str, str]]:
        """
        Get all files created during execution.

        Returns:
            List of all file dictionaries
        """
        all_files = []
        for agent_files in self._context["files_created"].values():
            all_files.extend(agent_files)
        return all_files

    def get_files_by_agent(self, agent_id: str) -> List[Dict[str, str]]:
        """
        Get files created by a specific agent.

        Args:
            agent_id: ID of the agent

        Returns:
            List of file dictionaries created by the agent
        """
        return self._context["files_created"].get(agent_id, [])

    def get_agent_output(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the output from a specific agent.

        Args:
            agent_id: ID of the agent

        Returns:
            Agent output dictionary or None
        """
        return self._context["agent_outputs"].get(agent_id)

    def get_all_agent_outputs(self) -> Dict[str, Dict[str, Any]]:
        """
        Get outputs from all agents.

        Returns:
            Dictionary mapping agent_id to output data
        """
        return deepcopy(self._context["agent_outputs"])

    def serialize(self) -> Dict[str, Any]:
        """
        Convert context to a dictionary for storage.

        Returns:
            Serializable dictionary representation of the context
        """
        return deepcopy(self._context)

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> 'ContextManager':
        """
        Restore context from stored data.

        Args:
            data: Previously serialized context data

        Returns:
            Restored ContextManager instance
        """
        manager = cls()

        if data:
            manager._context = {
                "agent_outputs": data.get("agent_outputs", {}),
                "files_created": data.get("files_created", {}),
                "shared_state": data.get("shared_state", {}),
                "execution_metadata": data.get("execution_metadata", {
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                })
            }

        logger.debug("ContextManager restored from serialized data")
        return manager

    def clear(self) -> None:
        """Clear all context data."""
        self._context = {
            "agent_outputs": {},
            "files_created": {},
            "shared_state": {},
            "execution_metadata": {
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
        }
        logger.debug("ContextManager cleared")

    def summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current context state.

        Returns:
            Summary dictionary
        """
        return {
            "agent_count": len(self._context["agent_outputs"]),
            "total_files": sum(len(files) for files in self._context["files_created"].values()),
            "shared_state_keys": list(self._context["shared_state"].keys()),
            "created_at": self._context["execution_metadata"].get("created_at"),
            "updated_at": self._context["execution_metadata"].get("updated_at")
        }
