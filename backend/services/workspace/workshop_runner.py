"""
Workshop Runner for AI Team Workspace Feature

Main workshop execution engine that coordinates multi-round collaborative sessions
between agents. Uses Claude Agent SDK with parallel agent execution — all agents
within a round run concurrently via asyncio.gather (like Claude Code's parallel
sub-agent pattern), then results are aggregated before the next round.

Falls back to Strands SDK if Claude Agent SDK is unavailable.
"""

import asyncio
import os
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from services.workspace.workshop_prompt_builder import WorkshopPromptBuilder
from services.workspace.workshop_compiler import WorkshopCompiler
from services.workspace.context_manager import ContextManager
from services.workspace.stream_service import StreamService
from services.workspace.artifact_service import ArtifactService

from repositories.workspace_execution_repository import WorkspaceExecutionRepository

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        query as claude_query,
        ClaudeAgentOptions,
        AssistantMessage,
        ResultMessage,
        TextBlock,
    )
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

# Strands SDK imports (fallback)
try:
    from strands import Agent
    from strands.models import BedrockModel
    STRANDS_AVAILABLE = True
except ImportError:
    STRANDS_AVAILABLE = False

logger = logging.getLogger(__name__)


class WorkshopRunner:
    """
    Runner for multi-round workshop executions with parallel agent execution.

    Primary: Claude Agent SDK with asyncio.gather for parallel agent execution
    within each round. All agents in a round run concurrently, then their
    contributions are aggregated before the next round begins.
    Fallback: Strands SDK with sequential per-round Agent() instantiation.
    """

    DEFAULT_MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    DEFAULT_TEMPERATURE = 0.5
    DEFAULT_MAX_TOKENS = 8192

    def __init__(
        self,
        model_id: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        # Store explicit user override for Claude SDK path (None means use env/default)
        self._user_model_id = model_id
        self.temperature = temperature if temperature is not None else self.DEFAULT_TEMPERATURE
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS

        self.prompt_builder = WorkshopPromptBuilder()
        self.compiler = WorkshopCompiler()

        mode = "Claude Agent SDK (parallel)" if CLAUDE_SDK_AVAILABLE else "Strands fallback"
        logger.info(f"WorkshopRunner initialized ({mode}, model={model_id or 'default'})")

    async def run_workshop(
        self,
        project: Dict[str, Any],
        agents: List[Dict[str, Any]],
        workshop_config: Dict[str, Any],
        context_manager: ContextManager,
        stream_service: StreamService,
        execution_id: str,
        execution_repo: WorkspaceExecutionRepository,
        artifact_service: ArtifactService,
    ) -> Dict[str, Any]:
        """Execute a complete multi-round workshop session."""
        if not CLAUDE_SDK_AVAILABLE and not STRANDS_AVAILABLE:
            return self._build_result(
                success=False, contributions=[], compiled_output="",
                artifact_filename="", total_tokens=0, total_cost=0.0,
                rounds_completed=0, agents_count=len(agents),
                error="No AI SDK available (install claude-agent-sdk or strands-agents)",
                duration_ms=0,
            )

        if CLAUDE_SDK_AVAILABLE:
            return await self._run_workshop_sdk(
                project, agents, workshop_config, context_manager,
                stream_service, execution_id, execution_repo, artifact_service,
            )
        else:
            return await self._run_workshop_strands(
                project, agents, workshop_config, context_manager,
                stream_service, execution_id, execution_repo, artifact_service,
            )

    async def _run_single_agent_sdk(
        self,
        agent: Dict[str, Any],
        agent_index: int,
        round_number: int,
        previous_contributions: List[Dict[str, Any]],
        workshop_config: Dict[str, Any],
        project_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a single agent via Claude SDK. Designed to run concurrently
        with other agents in the same round via asyncio.gather.

        Returns a contribution dict with content, tokens, cost, and any error.
        """
        agent_id = agent.get("agent_id", f"agent_{agent_index}")
        agent_name = agent.get("name", f"Agent {agent_index + 1}")

        try:
            system_prompt, user_prompt = self.prompt_builder.build_workshop_prompt(
                agent_blueprint=agent,
                workshop_config=workshop_config,
                round_number=round_number,
                previous_contributions=previous_contributions,
                project_context=project_context,
            )

            # Resolve model per-agent (Smart Model Routing)
            agent_model = self._user_model_id or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
            from services.claude_models import is_auto_model, resolve_auto_model
            if is_auto_model(agent_model):
                agent_model = resolve_auto_model(
                    prompt=user_prompt,
                    agent_count=1,
                    agent_category=agent.get("category"),
                )
                logger.info(f"Workshop agent {agent_name}: auto-resolved model to {agent_model}")

            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                allowed_tools=["Read", "Glob", "Grep"],
                permission_mode="default",
                model=agent_model,
                max_turns=5,
            )

            content_parts = []
            turn_tokens = 0
            turn_cost = 0.0

            async for message in claude_query(prompt=user_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            content_parts.append(block.text)
                if isinstance(message, ResultMessage):
                    turn_cost = message.total_cost_usd or 0
                    usage = message.usage or {}
                    turn_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            content = "\n".join(content_parts)

            return {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "content": content,
                "round_number": round_number,
                "tokens_used": turn_tokens,
                "cost": turn_cost,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as agent_error:
            error_msg = str(agent_error)
            logger.error(f"Error running agent {agent_name} in parallel: {error_msg}")
            return {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "content": f"[Agent failed: {error_msg}]",
                "round_number": round_number,
                "tokens_used": 0,
                "cost": 0.0,
                "timestamp": datetime.utcnow().isoformat(),
                "error": error_msg,
            }

    async def _run_workshop_sdk(
        self,
        project: Dict[str, Any],
        agents: List[Dict[str, Any]],
        workshop_config: Dict[str, Any],
        context_manager: ContextManager,
        stream_service: StreamService,
        execution_id: str,
        execution_repo: WorkspaceExecutionRepository,
        artifact_service: ArtifactService,
    ) -> Dict[str, Any]:
        """
        Execute workshop using Claude SDK with parallel agent execution.

        Within each round, all agents run concurrently via asyncio.gather.
        After all agents complete, their contributions are collected and used
        as context for the next round. This mirrors the Claude Code parallel
        sub-agent pattern for maximum throughput.
        """
        start_time = time.time()
        project_id = project.get("project_id") or project.get("id", "")
        project_name = project.get("name", "Unknown Project")
        topic = workshop_config.get("topic", "General Discussion")
        num_rounds = workshop_config.get("num_rounds", 1)
        output_format = workshop_config.get("output_format", "report")

        logger.info(
            f"Starting parallel SDK workshop '{topic}' with {len(agents)} agents, "
            f"{num_rounds} round(s)"
        )

        all_contributions: List[Dict[str, Any]] = []
        total_tokens = 0
        total_cost = 0.0
        rounds_completed = 0

        project_context = {
            "name": project.get("name", ""),
            "description": project.get("description", ""),
            "tech_stack": project.get("tech_stack", []),
        }

        await stream_service.emit_event(
            execution_id=execution_id,
            event_type=stream_service.EVENT_EXECUTION_STARTED,
            data=stream_service.create_execution_started_event(
                project_id=project_id,
                project_name=project_name,
                agent_count=len(agents),
            ),
            execution_repo=execution_repo,
        )

        try:
            for round_number in range(1, num_rounds + 1):
                logger.info(
                    f"Starting workshop round {round_number}/{num_rounds} "
                    f"({len(agents)} agents in parallel)"
                )

                # Check for cancellation before each round
                current_execution = await execution_repo.get_by_id(execution_id)
                if current_execution and current_execution.get("status") == "cancelled":
                    return self._build_result(
                        success=False, contributions=all_contributions,
                        compiled_output="", artifact_filename="",
                        total_tokens=total_tokens, total_cost=total_cost,
                        rounds_completed=rounds_completed,
                        agents_count=len(agents), error="Execution cancelled",
                        duration_ms=self._elapsed_ms(start_time),
                    )

                # Emit started events for all agents in this round
                for agent_index, agent in enumerate(agents):
                    agent_id = agent.get("agent_id", f"agent_{agent_index}")
                    agent_name = agent.get("name", f"Agent {agent_index + 1}")
                    step_index = (round_number - 1) * len(agents) + agent_index
                    total_steps = num_rounds * len(agents)
                    progress_percent = int((step_index / total_steps) * 100)

                    await stream_service.emit_event(
                        execution_id=execution_id,
                        event_type=stream_service.EVENT_AGENT_STARTED,
                        data=stream_service.create_agent_started_event(
                            agent_id=agent_id, agent_name=agent_name,
                            step_index=step_index,
                        ),
                        execution_repo=execution_repo,
                    )

                    await stream_service.emit_event(
                        execution_id=execution_id,
                        event_type=stream_service.EVENT_AGENT_PROGRESS,
                        data=stream_service.create_progress_event(
                            agent_id=agent_id, percent=progress_percent,
                            message=(
                                f"Round {round_number}/{num_rounds}: "
                                f"{agent_name} contributing (parallel)..."
                            ),
                        ),
                        execution_repo=execution_repo,
                    )

                # Run all agents in parallel via asyncio.gather
                # Each agent gets an independent claude_query() call
                agent_tasks = [
                    self._run_single_agent_sdk(
                        agent=agent,
                        agent_index=agent_index,
                        round_number=round_number,
                        previous_contributions=all_contributions,
                        workshop_config=workshop_config,
                        project_context=project_context,
                    )
                    for agent_index, agent in enumerate(agents)
                ]

                round_results = await asyncio.gather(*agent_tasks)

                # Collect results from parallel execution
                for contribution in round_results:
                    agent_id = contribution["agent_id"]
                    agent_name = contribution["agent_name"]
                    turn_tokens = contribution["tokens_used"]
                    turn_cost = contribution["cost"]

                    all_contributions.append(contribution)
                    total_tokens += turn_tokens
                    total_cost += turn_cost

                    context_manager.add_agent_output(
                        agent_id=f"{agent_id}_round_{round_number}",
                        output=contribution["content"],
                    )

                    await execution_repo.update_metrics(
                        execution_id=execution_id,
                        tokens=turn_tokens,
                        cost=turn_cost,
                    )

                    # Emit completed or failed event per agent
                    if contribution.get("error"):
                        await stream_service.emit_event(
                            execution_id=execution_id,
                            event_type=stream_service.EVENT_AGENT_FAILED,
                            data=stream_service.create_agent_failed_event(
                                agent_id=agent_id, agent_name=agent_name,
                                error=contribution["error"],
                            ),
                            execution_repo=execution_repo,
                        )
                    else:
                        await stream_service.emit_event(
                            execution_id=execution_id,
                            event_type=stream_service.EVENT_AGENT_COMPLETED,
                            data=stream_service.create_agent_completed_event(
                                agent_id=agent_id, agent_name=agent_name,
                                files_created=[], tokens_used=turn_tokens,
                                cost=turn_cost,
                            ),
                            execution_repo=execution_repo,
                        )

                rounds_completed = round_number
                logger.info(
                    f"Round {round_number} complete: {len(round_results)} agents, "
                    f"{sum(c['tokens_used'] for c in round_results)} tokens"
                )

            # Compile output from all rounds
            compiled_output = self.compiler.compile(all_contributions, workshop_config)
            artifact_filename = self._generate_artifact_filename(topic, output_format)

            save_result = await artifact_service.save_file(
                project_id=project_id,
                filename=artifact_filename,
                content=compiled_output,
            )

            if save_result.get("success"):
                await stream_service.emit_event(
                    execution_id=execution_id,
                    event_type=stream_service.EVENT_FILE_CREATED,
                    data=stream_service.create_file_created_event(
                        agent_id="workshop_compiler",
                        filename=artifact_filename,
                        size=save_result.get("size", len(compiled_output)),
                    ),
                    execution_repo=execution_repo,
                )

            duration_ms = self._elapsed_ms(start_time)

            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_EXECUTION_COMPLETED,
                data=stream_service.create_completed_event(
                    total_cost=total_cost,
                    artifacts_url=save_result.get("path"),
                    total_tokens=total_tokens,
                    duration_ms=duration_ms,
                    files_created=1,
                ),
                execution_repo=execution_repo,
            )

            return self._build_result(
                success=True, contributions=all_contributions,
                compiled_output=compiled_output,
                artifact_filename=artifact_filename,
                total_tokens=total_tokens, total_cost=total_cost,
                rounds_completed=rounds_completed, agents_count=len(agents),
                error=None, duration_ms=duration_ms,
            )

        except Exception as e:
            error_msg = str(e)
            duration_ms = self._elapsed_ms(start_time)
            logger.error(f"Workshop execution failed: {error_msg}")

            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_EXECUTION_FAILED,
                data=stream_service.create_failed_event(
                    error=error_msg, total_cost=total_cost,
                ),
                execution_repo=execution_repo,
            )

            return self._build_result(
                success=False, contributions=all_contributions,
                compiled_output="", artifact_filename="",
                total_tokens=total_tokens, total_cost=total_cost,
                rounds_completed=rounds_completed, agents_count=len(agents),
                error=error_msg, duration_ms=duration_ms,
            )

    async def _run_workshop_strands(
        self,
        project: Dict[str, Any],
        agents: List[Dict[str, Any]],
        workshop_config: Dict[str, Any],
        context_manager: ContextManager,
        stream_service: StreamService,
        execution_id: str,
        execution_repo: WorkspaceExecutionRepository,
        artifact_service: ArtifactService,
    ) -> Dict[str, Any]:
        """Fallback: Execute workshop using Strands SDK."""
        start_time = time.time()
        project_id = project.get("project_id") or project.get("id", "")
        project_name = project.get("name", "Unknown Project")
        topic = workshop_config.get("topic", "General Discussion")
        num_rounds = workshop_config.get("num_rounds", 1)
        output_format = workshop_config.get("output_format", "report")

        all_contributions: List[Dict[str, Any]] = []
        total_tokens = 0
        total_cost = 0.0
        rounds_completed = 0

        project_context = {
            "name": project.get("name", ""),
            "description": project.get("description", ""),
            "tech_stack": project.get("tech_stack", []),
        }

        await stream_service.emit_event(
            execution_id=execution_id,
            event_type=stream_service.EVENT_EXECUTION_STARTED,
            data=stream_service.create_execution_started_event(
                project_id=project_id, project_name=project_name,
                agent_count=len(agents),
            ),
            execution_repo=execution_repo,
        )

        try:
            model = BedrockModel(
                model_id=self.model_id,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                streaming=False,
            )

            for round_number in range(1, num_rounds + 1):
                current_execution = await execution_repo.get_by_id(execution_id)
                if current_execution and current_execution.get("status") == "cancelled":
                    return self._build_result(
                        success=False, contributions=all_contributions,
                        compiled_output="", artifact_filename="",
                        total_tokens=total_tokens, total_cost=total_cost,
                        rounds_completed=rounds_completed,
                        agents_count=len(agents), error="Execution cancelled",
                        duration_ms=self._elapsed_ms(start_time),
                    )

                for agent_index, agent in enumerate(agents):
                    agent_id = agent.get("agent_id", f"agent_{agent_index}")
                    agent_name = agent.get("name", f"Agent {agent_index + 1}")

                    step_index = (round_number - 1) * len(agents) + agent_index

                    await stream_service.emit_event(
                        execution_id=execution_id,
                        event_type=stream_service.EVENT_AGENT_STARTED,
                        data=stream_service.create_agent_started_event(
                            agent_id=agent_id, agent_name=agent_name,
                            step_index=step_index,
                        ),
                        execution_repo=execution_repo,
                    )

                    try:
                        system_prompt, user_prompt = self.prompt_builder.build_workshop_prompt(
                            agent_blueprint=agent,
                            workshop_config=workshop_config,
                            round_number=round_number,
                            previous_contributions=all_contributions,
                            project_context=project_context,
                        )

                        strands_agent = Agent(model=model, system_prompt=system_prompt)
                        response = strands_agent(user_prompt)

                        if hasattr(response, "content"):
                            content = response.content
                        elif isinstance(response, str):
                            content = response
                        else:
                            content = str(response)

                        tokens_used = (len(system_prompt + user_prompt) + len(content)) // 4
                        cost = (int(tokens_used * 0.7) / 1000 * 0.003) + (int(tokens_used * 0.3) / 1000 * 0.015)
                        total_tokens += tokens_used
                        total_cost += cost

                        all_contributions.append({
                            "agent_id": agent_id,
                            "agent_name": agent_name,
                            "content": content,
                            "round_number": round_number,
                            "tokens_used": tokens_used,
                            "cost": cost,
                            "timestamp": datetime.utcnow().isoformat(),
                        })

                        context_manager.add_agent_output(
                            agent_id=f"{agent_id}_round_{round_number}",
                            output=content,
                        )

                        await execution_repo.update_metrics(
                            execution_id=execution_id, tokens=tokens_used, cost=cost,
                        )

                        await stream_service.emit_event(
                            execution_id=execution_id,
                            event_type=stream_service.EVENT_AGENT_COMPLETED,
                            data=stream_service.create_agent_completed_event(
                                agent_id=agent_id, agent_name=agent_name,
                                files_created=[], tokens_used=tokens_used, cost=cost,
                            ),
                            execution_repo=execution_repo,
                        )

                    except Exception as agent_error:
                        error_msg = str(agent_error)
                        logger.error(f"Error running agent {agent_name}: {error_msg}")

                        await stream_service.emit_event(
                            execution_id=execution_id,
                            event_type=stream_service.EVENT_AGENT_FAILED,
                            data=stream_service.create_agent_failed_event(
                                agent_id=agent_id, agent_name=agent_name, error=error_msg,
                            ),
                            execution_repo=execution_repo,
                        )

                        all_contributions.append({
                            "agent_id": agent_id,
                            "agent_name": agent_name,
                            "content": f"[Agent failed: {error_msg}]",
                            "round_number": round_number,
                            "tokens_used": 0, "cost": 0.0,
                            "timestamp": datetime.utcnow().isoformat(),
                            "error": error_msg,
                        })
                        continue

                rounds_completed = round_number

            compiled_output = self.compiler.compile(all_contributions, workshop_config)
            artifact_filename = self._generate_artifact_filename(topic, output_format)

            save_result = await artifact_service.save_file(
                project_id=project_id, filename=artifact_filename, content=compiled_output,
            )

            duration_ms = self._elapsed_ms(start_time)

            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_EXECUTION_COMPLETED,
                data=stream_service.create_completed_event(
                    total_cost=total_cost, artifacts_url=save_result.get("path"),
                    total_tokens=total_tokens, duration_ms=duration_ms, files_created=1,
                ),
                execution_repo=execution_repo,
            )

            return self._build_result(
                success=True, contributions=all_contributions,
                compiled_output=compiled_output, artifact_filename=artifact_filename,
                total_tokens=total_tokens, total_cost=total_cost,
                rounds_completed=rounds_completed, agents_count=len(agents),
                error=None, duration_ms=duration_ms,
            )

        except Exception as e:
            error_msg = str(e)
            duration_ms = self._elapsed_ms(start_time)
            logger.error(f"Workshop execution failed: {error_msg}")

            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_EXECUTION_FAILED,
                data=stream_service.create_failed_event(
                    error=error_msg, total_cost=total_cost,
                ),
                execution_repo=execution_repo,
            )

            return self._build_result(
                success=False, contributions=all_contributions,
                compiled_output="", artifact_filename="",
                total_tokens=total_tokens, total_cost=total_cost,
                rounds_completed=rounds_completed, agents_count=len(agents),
                error=error_msg, duration_ms=duration_ms,
            )

    def _generate_artifact_filename(self, topic: str, output_format: str) -> str:
        safe_topic = topic.lower()
        safe_topic = "".join(c if c.isalnum() or c == "_" else "_" for c in safe_topic)
        while "__" in safe_topic:
            safe_topic = safe_topic.replace("__", "_")
        safe_topic = safe_topic[:50].strip("_")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"workshop_{output_format}_{safe_topic}_{timestamp}.md"

    def _elapsed_ms(self, start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    def _build_result(
        self, success: bool, contributions: List[Dict[str, Any]],
        compiled_output: str, artifact_filename: str,
        total_tokens: int, total_cost: float,
        rounds_completed: int, agents_count: int,
        error: Optional[str], duration_ms: int = 0,
    ) -> Dict[str, Any]:
        return {
            "success": success,
            "contributions": contributions,
            "compiled_output": compiled_output,
            "artifact_filename": artifact_filename,
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "rounds_completed": rounds_completed,
            "agents_count": agents_count,
            "total_contributions": len(contributions),
            "duration_ms": duration_ms,
            "error": error,
        }


def create_workshop_runner(
    model_id: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> WorkshopRunner:
    """Factory function for creating a WorkshopRunner instance."""
    return WorkshopRunner(model_id=model_id, temperature=temperature, max_tokens=max_tokens)
