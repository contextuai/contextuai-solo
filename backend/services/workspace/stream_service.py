"""
Stream Service for AI Team Workspace Feature

Provides real-time event streaming for workspace executions.
Writes events to MongoDB and supports SSE-based streaming to clients.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from repositories.workspace_execution_repository import WorkspaceExecutionRepository

# Configure logging
logger = logging.getLogger(__name__)


class StreamService:
    """
    Service for streaming execution events.

    Provides methods for emitting events during execution and
    retrieving events for SSE streaming to clients.
    """

    # Event types
    EVENT_EXECUTION_STARTED = "execution_started"
    EVENT_EXECUTION_COMPLETED = "execution_completed"
    EVENT_EXECUTION_FAILED = "execution_failed"
    EVENT_EXECUTION_PAUSED = "execution_paused"
    EVENT_EXECUTION_RESUMED = "execution_resumed"
    EVENT_EXECUTION_CANCELLED = "execution_cancelled"
    EVENT_AGENT_STARTED = "agent_started"
    EVENT_AGENT_PROGRESS = "agent_progress"
    EVENT_AGENT_COMPLETED = "agent_completed"
    EVENT_AGENT_FAILED = "agent_failed"
    EVENT_CHECKPOINT_CREATED = "checkpoint_created"
    EVENT_CHECKPOINT_RESOLVED = "checkpoint_resolved"
    EVENT_FILE_CREATED = "file_created"
    EVENT_TOOL_EXECUTED = "tool_executed"
    EVENT_GIT_PHASE = "git_phase"

    async def emit_event(
        self,
        execution_id: str,
        event_type: str,
        data: Dict[str, Any],
        execution_repo: WorkspaceExecutionRepository
    ) -> Optional[Dict[str, Any]]:
        """
        Write an event to the execution's event stream.

        Args:
            execution_id: ID of the execution
            event_type: Type of event (see EVENT_* constants)
            data: Event-specific data
            execution_repo: WorkspaceExecutionRepository instance

        Returns:
            Updated execution document or None if failed
        """
        try:
            logger.debug(f"Emitting event {event_type} for execution {execution_id}")

            result = await execution_repo.add_event(
                execution_id=execution_id,
                event_type=event_type,
                event_data=data
            )

            if result:
                logger.debug(f"Event {event_type} emitted successfully")
            else:
                logger.warning(f"Failed to emit event {event_type}")

            return result

        except Exception as e:
            logger.error(f"Error emitting event: {e}")
            return None

    async def get_events(
        self,
        execution_id: str,
        after_timestamp: Optional[str],
        execution_repo: WorkspaceExecutionRepository
    ) -> List[Dict[str, Any]]:
        """
        Get events for SSE streaming.

        Args:
            execution_id: ID of the execution
            after_timestamp: Optional ISO timestamp to filter events after
            execution_repo: WorkspaceExecutionRepository instance

        Returns:
            List of events after the specified timestamp
        """
        try:
            if after_timestamp:
                events = await execution_repo.get_events_after(
                    execution_id=execution_id,
                    after_timestamp=after_timestamp
                )
            else:
                # Get all events
                execution = await execution_repo.get_by_id(execution_id)
                if execution:
                    events = execution.get("events", [])
                else:
                    events = []

            logger.debug(f"Retrieved {len(events)} events for execution {execution_id}")
            return events

        except Exception as e:
            logger.error(f"Error getting events: {e}")
            return []

    def create_execution_started_event(
        self,
        project_id: str,
        project_name: str,
        agent_count: int
    ) -> Dict[str, Any]:
        """
        Create event data for execution started.

        Args:
            project_id: ID of the project
            project_name: Name of the project
            agent_count: Number of agents in the team

        Returns:
            Event data dictionary
        """
        return {
            "project_id": project_id,
            "project_name": project_name,
            "agent_count": agent_count,
            "message": f"Starting execution of '{project_name}' with {agent_count} agents"
        }

    def create_agent_started_event(
        self,
        agent_id: str,
        agent_name: str,
        step_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create event data for agent started.

        Args:
            agent_id: ID of the agent
            agent_name: Name of the agent
            step_index: Optional step index in the execution

        Returns:
            Event data dictionary
        """
        return {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "step_index": step_index,
            "message": f"Agent '{agent_name}' started execution"
        }

    def create_progress_event(
        self,
        agent_id: str,
        percent: int,
        message: str
    ) -> Dict[str, Any]:
        """
        Create event data for progress update.

        Args:
            agent_id: ID of the agent
            percent: Progress percentage (0-100)
            message: Progress message

        Returns:
            Event data dictionary
        """
        return {
            "agent_id": agent_id,
            "percent": min(100, max(0, percent)),
            "message": message
        }

    def create_agent_completed_event(
        self,
        agent_id: str,
        agent_name: str,
        files_created: Optional[List[str]] = None,
        tokens_used: int = 0,
        cost: float = 0.0
    ) -> Dict[str, Any]:
        """
        Create event data for agent completed.

        Args:
            agent_id: ID of the agent
            agent_name: Name of the agent
            files_created: Optional list of file names created
            tokens_used: Number of tokens used
            cost: Cost incurred

        Returns:
            Event data dictionary
        """
        return {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "files_created": files_created or [],
            "files_count": len(files_created) if files_created else 0,
            "tokens_used": tokens_used,
            "cost": cost,
            "message": f"Agent '{agent_name}' completed successfully"
        }

    def create_agent_failed_event(
        self,
        agent_id: str,
        agent_name: str,
        error: str
    ) -> Dict[str, Any]:
        """
        Create event data for agent failed.

        Args:
            agent_id: ID of the agent
            agent_name: Name of the agent
            error: Error message

        Returns:
            Event data dictionary
        """
        return {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "error": error,
            "message": f"Agent '{agent_name}' failed: {error}"
        }

    def create_checkpoint_event(
        self,
        checkpoint_id: str,
        checkpoint_type: str,
        agent_id: str,
        title: str
    ) -> Dict[str, Any]:
        """
        Create event data for checkpoint created.

        Args:
            checkpoint_id: ID of the checkpoint
            checkpoint_type: Type of checkpoint
            agent_id: ID of the agent that triggered it
            title: Checkpoint title

        Returns:
            Event data dictionary
        """
        return {
            "checkpoint_id": checkpoint_id,
            "checkpoint_type": checkpoint_type,
            "agent_id": agent_id,
            "title": title,
            "message": f"Checkpoint created: {title}"
        }

    def create_file_created_event(
        self,
        agent_id: str,
        filename: str,
        size: int
    ) -> Dict[str, Any]:
        """
        Create event data for file created.

        Args:
            agent_id: ID of the agent that created the file
            filename: Name of the file
            size: Size in bytes

        Returns:
            Event data dictionary
        """
        return {
            "agent_id": agent_id,
            "filename": filename,
            "size": size,
            "message": f"File created: {filename}"
        }

    def create_tool_executed_event(
        self,
        agent_id: str,
        tool_name: str,
        success: bool,
        result_summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create event data for tool execution.

        Args:
            agent_id: ID of the agent
            tool_name: Name of the tool executed
            success: Whether the tool execution was successful
            result_summary: Optional summary of the result

        Returns:
            Event data dictionary
        """
        status = "succeeded" if success else "failed"
        return {
            "agent_id": agent_id,
            "tool_name": tool_name,
            "success": success,
            "result_summary": result_summary,
            "message": f"Tool '{tool_name}' {status}"
        }

    def create_completed_event(
        self,
        total_cost: float,
        artifacts_url: Optional[str] = None,
        total_tokens: int = 0,
        duration_ms: int = 0,
        files_created: int = 0
    ) -> Dict[str, Any]:
        """
        Create event data for execution completed.

        Args:
            total_cost: Total cost of the execution
            artifacts_url: Optional URL to download artifacts
            total_tokens: Total tokens used
            duration_ms: Total duration in milliseconds
            files_created: Number of files created

        Returns:
            Event data dictionary
        """
        return {
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "duration_ms": duration_ms,
            "files_created": files_created,
            "artifacts_url": artifacts_url,
            "message": f"Execution completed. Cost: ${total_cost:.4f}, Files: {files_created}"
        }

    def create_failed_event(
        self,
        error: str,
        total_cost: float = 0.0,
        last_agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create event data for execution failed.

        Args:
            error: Error message
            total_cost: Cost incurred before failure
            last_agent_id: ID of the last agent that was running

        Returns:
            Event data dictionary
        """
        return {
            "error": error,
            "total_cost": total_cost,
            "last_agent_id": last_agent_id,
            "message": f"Execution failed: {error}"
        }

    def create_git_phase_event(
        self,
        phase: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create event data for git integration phases.

        Args:
            phase: Git phase name (clone, commit, push, pr_create)
            message: Human-readable status message
            details: Optional extra details (repo_url, branch, pr_url, etc.)

        Returns:
            Event data dictionary
        """
        event = {
            "phase": phase,
            "message": message,
        }
        if details:
            event["details"] = details
        return event

    def format_sse_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        event_id: Optional[str] = None
    ) -> str:
        """
        Format an event for Server-Sent Events.

        Args:
            event_type: Type of event
            data: Event data
            event_id: Optional event ID for resumption

        Returns:
            SSE-formatted string
        """
        import json

        lines = []

        if event_id:
            lines.append(f"id: {event_id}")

        lines.append(f"event: {event_type}")
        lines.append(f"data: {json.dumps(data)}")
        lines.append("")  # Empty line to end the event

        return "\n".join(lines) + "\n"


# Create singleton instance
stream_service = StreamService()
