"""
Crew Orchestrator — Executes crew runs by dispatching agents sequentially or in parallel.

Integrates with:
- CrewRepository / CrewRunRepository for state persistence
- CrewMemoryService for cross-run context injection
- AgentRunner for individual agent execution via Strands/Claude SDK
- CostService for token/cost tracking

Execution flow:
1. Load crew config and run record
2. Inject memory context from previous runs
3. Execute agents in configured mode (sequential/parallel/pipeline)
4. Collect results, track costs
5. Store run summary in crew memory
6. Update crew run stats
"""

import os
import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List

from repositories.crew_repository import CrewRepository, CrewRunRepository
from repositories.crew_memory_repository import CrewMemoryRepository
from repositories.workspace_agent_repository import WorkspaceAgentRepository
from services.crew_memory_service import CrewMemoryService
from models.crew_models import CrewRunStatus, ExecutionMode

# Claude Agent SDK imports (primary — cloud-agnostic: AWS, Azure, GCP)
try:
    from claude_agent_sdk import (
        query as claude_query,
        ClaudeAgentOptions,
        AssistantMessage,
        ResultMessage,
        TextBlock,
    )
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)


class CrewOrchestrator:
    """Executes crew runs by orchestrating agent sequences."""

    def __init__(
        self,
        crew_repo: CrewRepository,
        run_repo: CrewRunRepository,
        memory_repo: CrewMemoryRepository,
        agent_repo: Optional[WorkspaceAgentRepository] = None,
    ):
        self.crew_repo = crew_repo
        self.run_repo = run_repo
        self.memory_service = CrewMemoryService(memory_repo)
        self.agent_repo = agent_repo

    async def execute_run(self, run_id: str) -> Dict[str, Any]:
        """
        Main entry point: execute a crew run end-to-end.

        Args:
            run_id: The crew run ID to execute

        Returns:
            Final run state dict
        """
        run = await self.run_repo.get_by_run_id(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        crew = await self.crew_repo.get_by_crew_id(run["crew_id"])
        if not crew:
            raise ValueError(f"Crew {run['crew_id']} not found")

        # Mark as running
        await self.run_repo.mark_running(run_id)
        logger.info(f"Starting crew run {run_id} for crew '{crew['name']}'")

        try:
            # Get memory context
            memory_context = None
            if crew.get("memory_enabled", True):
                memory_context = await self.memory_service.format_context_prompt(
                    crew["crew_id"], max_entries=30
                )

            # Get execution config
            exec_config = crew.get("execution_config", {})
            mode = exec_config.get("mode", ExecutionMode.SEQUENTIAL.value)
            timeout = exec_config.get("timeout_seconds", 600)

            # Execute with timeout
            result = await asyncio.wait_for(
                self._execute_agents(
                    run=run,
                    crew=crew,
                    memory_context=memory_context,
                    mode=mode,
                ),
                timeout=timeout,
            )

            # Mark completed
            total_tokens = result.get("total_tokens", 0)
            total_cost = result.get("total_cost_usd", 0.0)
            final_output = result.get("output", "")

            final_run = await self.run_repo.mark_completed(
                run_id, final_output, total_tokens, total_cost
            )

            # Update crew stats
            await self.crew_repo.increment_run_stats(crew["crew_id"], total_cost)

            # Store run summary in memory
            if crew.get("memory_enabled", True) and final_output:
                try:
                    await self.memory_service.add_run_summary(
                        crew["crew_id"],
                        run_id,
                        summary=self._generate_run_summary(final_output, result),
                        agent_summaries=result.get("agent_summaries", []),
                    )
                except Exception as e:
                    logger.warning(f"Failed to store run summary in memory: {e}")

            logger.info(f"Crew run {run_id} completed. tokens={total_tokens}, cost=${total_cost:.4f}")
            return final_run

        except asyncio.TimeoutError:
            error_msg = f"Crew run timed out after {exec_config.get('timeout_seconds', 600)}s"
            logger.error(f"Run {run_id}: {error_msg}")
            final_run = await self.run_repo.mark_failed(run_id, error_msg)
            await self.crew_repo.increment_run_stats(crew["crew_id"])
            return final_run

        except Exception as e:
            error_msg = f"Crew run failed: {str(e)}"
            logger.error(f"Run {run_id}: {error_msg}", exc_info=True)
            final_run = await self.run_repo.mark_failed(run_id, error_msg)
            await self.crew_repo.increment_run_stats(crew["crew_id"])
            return final_run

    async def _execute_agents(
        self,
        run: Dict[str, Any],
        crew: Dict[str, Any],
        memory_context: Optional[str],
        mode: str,
    ) -> Dict[str, Any]:
        """
        Execute agents according to the configured mode.

        Returns dict with: output, total_tokens, total_cost_usd, agent_summaries
        """
        agents = crew.get("agents", [])
        run_id = run["run_id"]
        user_input = run.get("input", "")
        input_data = run.get("input_data", {})

        if mode == ExecutionMode.AUTONOMOUS.value:
            return await self._execute_autonomous(
                run=run,
                crew=crew,
                user_input=user_input,
                input_data=input_data,
                memory_context=memory_context,
            )
        elif mode == ExecutionMode.PARALLEL.value:
            return await self._execute_parallel(
                run_id, agents, user_input, input_data, memory_context
            )
        else:
            # Sequential (default) and pipeline both use sequential execution
            return await self._execute_sequential(
                run_id, agents, user_input, input_data, memory_context
            )

    async def _execute_sequential(
        self,
        run_id: str,
        agents: List[Dict[str, Any]],
        user_input: str,
        input_data: Optional[Dict[str, Any]],
        memory_context: Optional[str],
    ) -> Dict[str, Any]:
        """Execute agents one by one, passing output from each to the next."""
        total_tokens = 0
        total_cost = 0.0
        agent_summaries = []
        accumulated_context = []

        # Sort agents by order
        sorted_agents = sorted(agents, key=lambda a: a.get("order", 0))

        for i, agent_cfg in enumerate(sorted_agents):
            agent_id = agent_cfg.get("agent_id", f"agent-{i}")
            agent_name = agent_cfg.get("name", f"Agent {i}")

            # Mark agent as running
            await self.run_repo.update_agent_state(run_id, agent_id, {
                "status": CrewRunStatus.RUNNING.value,
                "started_at": datetime.utcnow().isoformat(),
            })

            try:
                # Build prompt for this agent
                prompt = self._build_agent_prompt(
                    agent_cfg=agent_cfg,
                    user_input=user_input,
                    input_data=input_data,
                    memory_context=memory_context if i == 0 else None,
                    previous_outputs=accumulated_context,
                )

                # Execute agent
                result = await self._invoke_agent(agent_cfg, prompt)

                agent_output = result.get("output", "")
                agent_tokens = result.get("tokens_used", 0)
                agent_cost = result.get("cost", 0.0)

                total_tokens += agent_tokens
                total_cost += agent_cost

                accumulated_context.append({
                    "agent_name": agent_name,
                    "role": agent_cfg.get("role", "custom"),
                    "output": agent_output,
                })

                agent_summaries.append({
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "summary": agent_output[:500] if agent_output else "",
                })

                # Mark agent completed
                await self.run_repo.update_agent_state(run_id, agent_id, {
                    "status": CrewRunStatus.COMPLETED.value,
                    "completed_at": datetime.utcnow().isoformat(),
                    "output": agent_output,
                    "tokens_used": agent_tokens,
                    "cost_usd": agent_cost,
                })

                logger.info(f"Agent '{agent_name}' completed (tokens={agent_tokens})")

            except Exception as e:
                error_msg = str(e)
                await self.run_repo.update_agent_state(run_id, agent_id, {
                    "status": CrewRunStatus.FAILED.value,
                    "completed_at": datetime.utcnow().isoformat(),
                    "error": error_msg,
                })
                logger.error(f"Agent '{agent_name}' failed: {error_msg}")
                raise RuntimeError(f"Agent '{agent_name}' failed: {error_msg}")

        # Final output is the last agent's output
        final_output = accumulated_context[-1]["output"] if accumulated_context else ""

        return {
            "output": final_output,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "agent_summaries": agent_summaries,
        }

    async def _execute_parallel(
        self,
        run_id: str,
        agents: List[Dict[str, Any]],
        user_input: str,
        input_data: Optional[Dict[str, Any]],
        memory_context: Optional[str],
    ) -> Dict[str, Any]:
        """Execute all agents concurrently."""

        async def run_single_agent(agent_cfg: Dict[str, Any], idx: int):
            agent_id = agent_cfg.get("agent_id", f"agent-{idx}")
            agent_name = agent_cfg.get("name", f"Agent {idx}")

            await self.run_repo.update_agent_state(run_id, agent_id, {
                "status": CrewRunStatus.RUNNING.value,
                "started_at": datetime.utcnow().isoformat(),
            })

            try:
                prompt = self._build_agent_prompt(
                    agent_cfg=agent_cfg,
                    user_input=user_input,
                    input_data=input_data,
                    memory_context=memory_context,
                    previous_outputs=[],
                )
                result = await self._invoke_agent(agent_cfg, prompt)

                agent_output = result.get("output", "")
                agent_tokens = result.get("tokens_used", 0)
                agent_cost = result.get("cost", 0.0)

                await self.run_repo.update_agent_state(run_id, agent_id, {
                    "status": CrewRunStatus.COMPLETED.value,
                    "completed_at": datetime.utcnow().isoformat(),
                    "output": agent_output,
                    "tokens_used": agent_tokens,
                    "cost_usd": agent_cost,
                })

                return {
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "output": agent_output,
                    "tokens_used": agent_tokens,
                    "cost": agent_cost,
                    "success": True,
                }
            except Exception as e:
                await self.run_repo.update_agent_state(run_id, agent_id, {
                    "status": CrewRunStatus.FAILED.value,
                    "completed_at": datetime.utcnow().isoformat(),
                    "error": str(e),
                })
                return {
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "output": "",
                    "tokens_used": 0,
                    "cost": 0.0,
                    "success": False,
                    "error": str(e),
                }

        # Run all agents concurrently
        tasks = [run_single_agent(a, i) for i, a in enumerate(agents)]
        results = await asyncio.gather(*tasks)

        # Check for failures
        failures = [r for r in results if not r["success"]]
        if failures:
            failed_names = ", ".join(f["agent_name"] for f in failures)
            raise RuntimeError(f"Agents failed: {failed_names}")

        # Combine outputs
        total_tokens = sum(r["tokens_used"] for r in results)
        total_cost = sum(r["cost"] for r in results)
        combined_output = "\n\n---\n\n".join(
            f"## {r['agent_name']}\n\n{r['output']}" for r in results
        )
        agent_summaries = [
            {"agent_id": r["agent_id"], "agent_name": r["agent_name"], "summary": r["output"][:500]}
            for r in results
        ]

        return {
            "output": combined_output,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "agent_summaries": agent_summaries,
        }

    def _is_local_model(self, model_id: str) -> bool:
        """Check if a model ID refers to a local GGUF model."""
        return model_id.startswith("local-") or model_id.startswith("local:")

    async def _invoke_agent(
        self, agent_cfg: Dict[str, Any], prompt: str
    ) -> Dict[str, Any]:
        """
        Invoke a single agent using the best available SDK.

        Routing: local GGUF > Claude Agent SDK > Strands SDK (Bedrock).
        """
        # Check if we should use a local model
        model_id = agent_cfg.get("model_id", "")
        if not model_id:
            # Resolve from AI mode preference
            try:
                from database import get_database
                from services.default_model_service import DefaultModelService
                db = await get_database()
                default_svc = DefaultModelService(db)
                ai_mode = await default_svc.get_ai_mode_preference()
                model_id = await default_svc.get_default_model_id(ai_mode)
            except Exception:
                model_id = ""

        if model_id and self._is_local_model(model_id):
            # Local model selected — do NOT fall through to Bedrock on failure
            return await self._invoke_via_local(agent_cfg, prompt, model_id)

        if CLAUDE_SDK_AVAILABLE:
            try:
                return await self._invoke_via_claude_sdk(agent_cfg, prompt)
            except Exception as e:
                logger.warning(f"Claude SDK failed for crew agent, falling back to Strands: {e}")

        try:
            return await self._invoke_via_bedrock(agent_cfg, prompt)
        except ImportError:
            logger.warning("No AI SDK available, returning prompt echo for testing")
            return {
                "output": f"[Agent '{agent_cfg.get('name')}' would process: {prompt[:200]}...]",
                "tokens_used": 0,
                "cost": 0.0,
            }

    async def _invoke_via_local(
        self, agent_cfg: Dict[str, Any], prompt: str, model_id: str
    ) -> Dict[str, Any]:
        """Invoke agent via local GGUF model (text generation only)."""
        from services.local_model_service import local_model_service

        agent_name = agent_cfg.get("name", "Agent")
        logger.info(f"Running crew agent '{agent_name}' via local model: {model_id}")

        catalog_id = model_id.replace("local:", "").replace("local-", "")

        system_prompt = await self._resolve_instructions(agent_cfg)
        full_prompt = f"{system_prompt}\n\n{prompt}"

        output = await local_model_service.generate(model_id=catalog_id, prompt=full_prompt, max_tokens=4096)

        tokens_used = len(full_prompt.split()) + len(output.split())
        logger.info(f"Crew agent '{agent_name}' completed via local model (tokens~{tokens_used})")

        return {
            "output": output,
            "tokens_used": tokens_used,
            "cost": 0.0,
        }

    async def _resolve_instructions(self, agent_cfg: Dict[str, Any]) -> str:
        """Resolve agent instructions, falling back to library agent if instructions are too short."""
        instructions = agent_cfg.get("instructions", "")
        library_agent_id = agent_cfg.get("library_agent_id")

        if len(instructions) >= 50 or not library_agent_id or not self.agent_repo:
            return instructions or "You are a helpful assistant."

        # Defensive fallback: fetch system_prompt from workspace agent library
        try:
            lib_agent = await self.agent_repo.get_by_id(library_agent_id)
            if lib_agent and lib_agent.get("system_prompt"):
                logger.info(
                    f"Resolved short instructions for agent '{agent_cfg.get('name')}' "
                    f"from library agent {library_agent_id}"
                )
                return lib_agent["system_prompt"]
        except Exception as e:
            logger.warning(f"Failed to resolve library agent {library_agent_id}: {e}")

        return instructions or "You are a helpful assistant."

    async def _invoke_via_bedrock(
        self, agent_cfg: Dict[str, Any], prompt: str
    ) -> Dict[str, Any]:
        """Invoke agent via AWS Bedrock / Strands SDK."""
        from strands import Agent
        from strands.models import BedrockModel

        model_id = agent_cfg.get("model_id") or "us.anthropic.claude-sonnet-4-20250514"

        bedrock_model = BedrockModel(
            model_id=model_id,
            temperature=0.3,
            max_tokens=4096,
        )

        system_prompt = await self._resolve_instructions(agent_cfg)

        agent = Agent(
            model=bedrock_model,
            system_prompt=system_prompt,
        )

        # Run in thread pool since Strands SDK is sync
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, agent, prompt)

        # Parse result
        output_text = str(result) if result else ""

        # Extract token usage from agent metrics if available
        tokens_used = 0
        cost = 0.0
        if hasattr(result, "metrics"):
            metrics = result.metrics
            tokens_used = getattr(metrics, "total_tokens", 0)
            cost = getattr(metrics, "total_cost", 0.0)

        return {
            "output": output_text,
            "tokens_used": tokens_used,
            "cost": cost,
        }

    async def _invoke_via_claude_sdk(
        self, agent_cfg: Dict[str, Any], prompt: str
    ) -> Dict[str, Any]:
        """Invoke agent via Claude Agent SDK with native tools (cloud-agnostic)."""
        agent_name = agent_cfg.get("name", "Agent")
        system_prompt = await self._resolve_instructions(agent_cfg)

        resolved_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

        # Smart model routing: resolve "auto" to concrete model
        try:
            from services.claude_models import is_auto_model, resolve_auto_model
            if is_auto_model(resolved_model):
                resolved_model = resolve_auto_model(
                    prompt=prompt,
                    agent_category=agent_cfg.get("role"),
                )
                logger.info(f"Crew agent '{agent_name}': auto-resolved model to {resolved_model}")
        except ImportError:
            pass

        # Permission guard: block dangerous commands
        async def crew_tool_guard(tool_name, input_data, ctx):
            if tool_name == "Bash":
                command = input_data.get("command", "")
                blocked = [
                    "rm -rf /", "rm -rf ~", "git push", "shutdown",
                    "apt-get", "pip install", "npm install",
                ]
                if any(b in command for b in blocked):
                    return PermissionResultDeny(message=f"Blocked: {command}")
            return PermissionResultAllow(updated_input=input_data)

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
            permission_mode="acceptEdits",
            can_use_tool=crew_tool_guard,
            model=resolved_model,
            max_turns=20,
        )

        output_parts = []
        tokens_used = 0
        cost = 0.0

        async for message in claude_query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        output_parts.append(block.text)
            if isinstance(message, ResultMessage):
                cost = message.total_cost_usd or 0
                usage = message.usage or {}
                tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        output = "\n".join(output_parts)
        logger.info(
            f"Crew agent '{agent_name}' completed via Claude SDK: "
            f"tokens={tokens_used}, cost=${cost:.4f}"
        )

        return {
            "output": output,
            "tokens_used": tokens_used,
            "cost": cost,
        }

    async def _execute_autonomous(
        self,
        run: Dict[str, Any],
        crew: Dict[str, Any],
        user_input: str,
        input_data: Optional[Dict[str, Any]],
        memory_context: Optional[str],
    ) -> Dict[str, Any]:
        """
        Execute an autonomous crew run with a coordinator agent that dynamically
        discovers and invokes specialist agents from the workspace library.
        """
        from services.tools.agent_tools import AgentTools

        run_id = run["run_id"]
        exec_config = crew.get("execution_config", {})

        # Create AgentTools with run-specific limits
        agent_tools = AgentTools(
            max_invocations=exec_config.get("max_agent_invocations", 10),
            budget_limit_usd=exec_config.get("budget_limit_usd", 1.0),
        )

        # Mark coordinator as running
        await self.run_repo.update_agent_state(run_id, "coordinator", {
            "status": CrewRunStatus.RUNNING.value,
            "started_at": datetime.utcnow().isoformat(),
        })

        try:
            # Build coordinator system prompt
            coordinator_prompt = self._build_coordinator_system_prompt(crew, memory_context)

            # Build task prompt
            task_parts = []
            if input_data:
                import json as _json
                task_parts.append(f"## Input Data\n```json\n{_json.dumps(input_data, indent=2)}\n```")
            if user_input:
                task_parts.append(f"## Task\n{user_input}")
            task_prompt = "\n\n".join(task_parts) if task_parts else "Complete the task as described."

            # Create coordinator agent with discovery + invocation tools
            from strands import Agent
            from strands.models import BedrockModel

            model_id = exec_config.get("model_id") or "us.anthropic.claude-sonnet-4-20250514"

            bedrock_model = BedrockModel(
                model_id=model_id,
                temperature=0.3,
                max_tokens=8192,
            )

            coordinator = Agent(
                model=bedrock_model,
                system_prompt=coordinator_prompt,
                tools=agent_tools.get_tools(),
            )

            # Run coordinator in thread pool (Strands SDK is sync)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, coordinator, task_prompt)

            coordinator_output = str(result) if result else ""

            # Extract coordinator's own token usage
            coordinator_tokens = 0
            coordinator_cost = 0.0
            if hasattr(result, "metrics"):
                metrics = result.metrics
                coordinator_tokens = getattr(metrics, "total_tokens", 0)
                coordinator_cost = getattr(metrics, "total_cost", 0.0)

            # Total = coordinator + all invoked agents
            tracking = agent_tools.get_tracking_summary()
            total_tokens = coordinator_tokens + tracking["total_tokens"]
            total_cost = coordinator_cost + tracking["total_cost_usd"]

            # Mark coordinator completed
            await self.run_repo.update_agent_state(run_id, "coordinator", {
                "status": CrewRunStatus.COMPLETED.value,
                "completed_at": datetime.utcnow().isoformat(),
                "output": coordinator_output,
                "tokens_used": coordinator_tokens,
                "cost_usd": coordinator_cost,
            })

            # Add agent states for each invoked agent
            for entry in tracking["invocation_log"]:
                agent_state = {
                    "agent_id": entry["agent_id"],
                    "name": entry["agent_name"],
                    "role": "specialist",
                    "status": CrewRunStatus.COMPLETED.value if entry["status"] == "completed" else CrewRunStatus.FAILED.value,
                    "completed_at": datetime.utcnow().isoformat(),
                    "output": None,
                    "error": entry.get("error"),
                    "tokens_used": entry.get("tokens", 0),
                    "cost_usd": entry.get("cost", 0.0),
                    "iteration": 0,
                }
                try:
                    await self.run_repo.append_agent_state(run_id, agent_state)
                except Exception:
                    logger.debug(f"Could not append agent state for {entry['agent_id']}")

            # Build agent summaries for memory
            agent_summaries = [
                {
                    "agent_id": "coordinator",
                    "agent_name": "Coordinator",
                    "summary": coordinator_output[:500] if coordinator_output else "",
                }
            ]
            for entry in tracking["invocation_log"]:
                agent_summaries.append({
                    "agent_id": entry["agent_id"],
                    "agent_name": entry["agent_name"],
                    "summary": f"Task: {entry['task'][:200]}",
                })

            logger.info(
                f"Autonomous run {run_id} completed: "
                f"{tracking['invocation_count']} agents invoked, "
                f"tokens={total_tokens}, cost=${total_cost:.4f}"
            )

            return {
                "output": coordinator_output,
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost,
                "agent_summaries": agent_summaries,
                "autonomous_metadata": tracking,
            }

        except Exception as e:
            error_msg = str(e)
            await self.run_repo.update_agent_state(run_id, "coordinator", {
                "status": CrewRunStatus.FAILED.value,
                "completed_at": datetime.utcnow().isoformat(),
                "error": error_msg,
            })
            raise RuntimeError(f"Autonomous coordinator failed: {error_msg}")

    def _build_coordinator_system_prompt(
        self, crew: Dict[str, Any], memory_context: Optional[str]
    ) -> str:
        """Build the system prompt for the autonomous coordinator agent."""
        sections = [
            "You are an autonomous coordinator agent for a multi-agent crew.",
            "",
            "## Your Workflow",
            "1. Analyze the user's task carefully.",
            "2. Use `discover_agents` to search the agent library for specialists that can help.",
            "3. Use `invoke_agent` to delegate sub-tasks to discovered specialists.",
            "4. Compile all specialist outputs into a comprehensive final response.",
            "",
            "## Guidelines",
            "- Discover before invoking: always search for relevant agents first.",
            "- Be strategic with invocations — each one counts toward your limit.",
            "- Pass context between agents: include relevant prior outputs as context.",
            "- If an agent fails, work around it using outputs from other agents.",
            "- When you reach the invocation limit, compile results from what you have.",
            "- Your final message should be a complete, well-structured deliverable.",
            "",
            "## Available Agent Categories",
            "code_generation, engineering, devops, migration, code_quality, documentation,",
            "design, data_analytics, product_management, c_suite, marketing_sales, hr,",
            "finance, legal, customer_support, security, research",
        ]

        crew_desc = crew.get("description")
        if crew_desc:
            sections.append(f"\n## Crew Purpose\n{crew_desc}")

        if memory_context:
            sections.append(f"\n## Previous Run Context\n{memory_context}")

        return "\n".join(sections)

    def _build_agent_prompt(
        self,
        agent_cfg: Dict[str, Any],
        user_input: str,
        input_data: Optional[Dict[str, Any]],
        memory_context: Optional[str],
        previous_outputs: List[Dict[str, Any]],
    ) -> str:
        """Build the full prompt for an agent, including context and previous outputs."""
        sections = []

        # Memory context (from previous crew runs)
        if memory_context:
            sections.append(memory_context)

        # Previous agent outputs (sequential mode)
        if previous_outputs:
            sections.append("## Previous Agent Outputs\n")
            for prev in previous_outputs:
                sections.append(f"### {prev['agent_name']} ({prev['role']})\n{prev['output']}\n")

        # Structured input data
        if input_data:
            import json
            sections.append(f"## Input Data\n```json\n{json.dumps(input_data, indent=2)}\n```")

        # User input / task
        if user_input:
            sections.append(f"## Task\n{user_input}")

        return "\n\n".join(sections) if sections else "Please complete the task as described in your instructions."

    def _generate_run_summary(self, output: str, result: Dict[str, Any]) -> str:
        """Generate a brief summary of the run for memory storage."""
        agent_count = len(result.get("agent_summaries", []))
        tokens = result.get("total_tokens", 0)
        cost = result.get("total_cost_usd", 0.0)

        summary = f"Run completed with {agent_count} agents. "
        summary += f"Tokens: {tokens}, Cost: ${cost:.4f}. "
        summary += f"Output preview: {output[:300]}"
        return summary
