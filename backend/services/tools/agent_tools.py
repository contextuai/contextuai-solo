"""
Agent Tools — Enables autonomous crew coordinators to discover and invoke
specialist agents from the workspace agent library at runtime.

Used exclusively by the Autonomous Crew execution mode. The coordinator agent
gets these tools; invoked agents get read-only tools (Read, Glob, Grep) via
Claude Agent SDK, preventing recursion while allowing file inspection.

Primary SDK: Claude Agent SDK (cloud-agnostic: AWS, Azure, GCP)
Fallback SDK: Strands Agents SDK (AWS Bedrock only, no tools for invoked agents)

Uses sync PyMongo (not async Motor) because Strands @tool functions execute
inside run_in_executor threads with no asyncio event loop.
"""

import json
import logging
import time
from typing import Optional, List, Dict, Any

import asyncio
import os

from strands import tool

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


async def _invoke_agent_via_claude_sdk(
    system_prompt: str, prompt: str, model: str
) -> Dict[str, Any]:
    """
    Invoke a specialist agent via Claude Agent SDK with read-only tools.

    Read-only tools (Read, Glob, Grep) allow the agent to inspect files
    without modification. No Write/Edit/Bash — prevents recursive side effects.
    """

    async def read_only_guard(tool_name, input_data, ctx):
        """Only allow read-only tools for invoked specialist agents."""
        if tool_name in ("Read", "Glob", "Grep"):
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(
            message=f"Tool '{tool_name}' not allowed for invoked agents (read-only only)"
        )

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        allowed_tools=["Read", "Glob", "Grep"],
        permission_mode="default",
        can_use_tool=read_only_guard,
        model=model,
        max_turns=10,
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

    return {
        "output": "\n".join(output_parts),
        "tokens_used": tokens_used,
        "cost": cost,
    }


class AgentTools:
    """
    Provides discover_agents and invoke_agent tools for autonomous crew coordinators.

    Safety guardrails:
    - Max invocations per run (default 10, configurable 1-50)
    - Budget limit per run (default $1.00, configurable $0.01-$100)
    - Per-agent timeout (120s)
    - Invoked agents get NO tools (no recursion)
    - Failed invocations count toward limit
    """

    def __init__(
        self,
        max_invocations: int = 10,
        budget_limit_usd: float = 1.0,
        default_model_id: str = "us.anthropic.claude-sonnet-4-20250514",
    ):
        self.max_invocations = max(1, min(50, max_invocations))
        self.budget_limit_usd = max(0.01, min(100.0, budget_limit_usd))
        self.default_model_id = default_model_id

        # Runtime tracking
        self.invocation_count = 0
        self.total_cost_usd = 0.0
        self.total_tokens = 0
        self.invocation_log: List[Dict[str, Any]] = []

        # Sync MongoDB access
        self._db = None

    def _get_db(self):
        """Lazy-load sync MongoDB connection."""
        if self._db is None:
            from database import get_sync_database
            self._db = get_sync_database()
        return self._db

    def get_tools(self) -> list:
        """Return the list of Strands tool functions for the coordinator agent."""
        return [self._discover_agents_tool(), self._invoke_agent_tool()]

    def _discover_agents_tool(self):
        """Create the discover_agents tool with closure over self."""
        agent_tools_ref = self

        @tool
        def discover_agents(
            query: str = "",
            category: str = "",
            max_results: int = 10,
        ) -> str:
            """Search the workspace agent library for specialist agents.

            Use this tool to find agents that can help with specific tasks.
            You can search by keyword (matches name, description, capabilities)
            and optionally filter by category.

            Args:
                query: Search text to match against agent name, description, and capabilities.
                category: Optional category filter (e.g., 'marketing_sales', 'code_generation', 'data_analytics', 'engineering', 'design', 'documentation', 'product_management', 'hr', 'finance', 'legal', 'customer_support', 'devops', 'security', 'research', 'code_quality', 'c_suite').
                max_results: Maximum number of agents to return (1-20, default 10).

            Returns:
                JSON array of matching agents with id, name, description, category, and capabilities.
            """
            try:
                db = agent_tools_ref._get_db()
                collection = db["workspace_agents"]

                max_results = max(1, min(20, max_results))

                # Build MongoDB query
                mongo_filter: Dict[str, Any] = {"status": "active"}

                if category:
                    mongo_filter["category"] = category

                if query:
                    # Text search across name, description, capabilities
                    mongo_filter["$or"] = [
                        {"name": {"$regex": query, "$options": "i"}},
                        {"description": {"$regex": query, "$options": "i"}},
                        {"capabilities": {"$regex": query, "$options": "i"}},
                    ]

                cursor = collection.find(
                    mongo_filter,
                    {
                        "agent_id": 1,
                        "name": 1,
                        "description": 1,
                        "category": 1,
                        "capabilities": 1,
                        "estimated_cost_per_run": 1,
                        "_id": 0,
                    },
                ).limit(max_results)

                agents = []
                for doc in cursor:
                    agents.append({
                        "agent_id": doc.get("agent_id", ""),
                        "name": doc.get("name", ""),
                        "description": doc.get("description", "")[:200],
                        "category": doc.get("category", ""),
                        "capabilities": doc.get("capabilities", []),
                    })

                if not agents:
                    return json.dumps({
                        "agents": [],
                        "message": f"No agents found matching query='{query}' category='{category}'. Try broader search terms.",
                    })

                return json.dumps({
                    "agents": agents,
                    "total_found": len(agents),
                })

            except Exception as e:
                logger.error(f"discover_agents failed: {e}")
                return json.dumps({"error": str(e), "agents": []})

        return discover_agents

    def _invoke_agent_tool(self):
        """Create the invoke_agent tool with closure over self."""
        agent_tools_ref = self

        @tool
        def invoke_agent(
            agent_id: str,
            task: str,
            context: str = "",
        ) -> str:
            """Invoke a specialist agent from the library to perform a specific task.

            The invoked agent will execute the task using its specialized knowledge
            (system prompt) and return the result. Invoked agents have read-only tools
            (Read, Glob, Grep) when Claude SDK is available, otherwise text-only.

            IMPORTANT: Each invocation counts toward the run's invocation limit and budget.
            Plan your invocations carefully — discover first, then invoke strategically.

            Args:
                agent_id: The agent_id from discover_agents results.
                task: Clear description of what you want this agent to do.
                context: Optional context from previous agent outputs to pass along.

            Returns:
                The agent's text output, or an error message if invocation fails.
            """
            start_time = time.time()

            # Check invocation limit
            if agent_tools_ref.invocation_count >= agent_tools_ref.max_invocations:
                return (
                    f"INVOCATION LIMIT REACHED ({agent_tools_ref.max_invocations}). "
                    "You cannot invoke more agents. Please compile your final output "
                    "from the results already gathered."
                )

            # Check budget limit
            if agent_tools_ref.total_cost_usd >= agent_tools_ref.budget_limit_usd:
                return (
                    f"BUDGET LIMIT REACHED (${agent_tools_ref.budget_limit_usd:.2f}). "
                    "You cannot invoke more agents. Please compile your final output "
                    "from the results already gathered."
                )

            # Count this invocation (even if it fails)
            agent_tools_ref.invocation_count += 1

            try:
                # Load agent from library
                db = agent_tools_ref._get_db()
                collection = db["workspace_agents"]
                agent_doc = collection.find_one({"agent_id": agent_id})

                if not agent_doc:
                    log_entry = {
                        "agent_id": agent_id,
                        "agent_name": "unknown",
                        "task": task[:200],
                        "tokens": 0,
                        "cost": 0.0,
                        "elapsed_seconds": time.time() - start_time,
                        "status": "error",
                        "error": "Agent not found",
                    }
                    agent_tools_ref.invocation_log.append(log_entry)
                    return f"Error: Agent '{agent_id}' not found in the library."

                agent_name = agent_doc.get("name", agent_id)
                system_prompt = agent_doc.get("system_prompt", "You are a helpful specialist assistant.")

                logger.info(
                    f"Invoking agent '{agent_name}' ({agent_id}) — "
                    f"invocation {agent_tools_ref.invocation_count}/{agent_tools_ref.max_invocations}"
                )

                # Build the full prompt for the invoked agent
                full_prompt_parts = []
                if context:
                    full_prompt_parts.append(f"## Context from Previous Agents\n{context}")
                full_prompt_parts.append(f"## Task\n{task}")
                full_prompt = "\n\n".join(full_prompt_parts)

                # ---- Primary: Claude Agent SDK (read-only tools) ----
                if CLAUDE_SDK_AVAILABLE:
                    logger.info(f"Invoking agent '{agent_name}' via Claude Agent SDK (read-only tools)")

                    resolved_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

                    # Smart model routing: resolve "auto" to concrete model
                    try:
                        from services.claude_models import is_auto_model, resolve_auto_model
                        if is_auto_model(resolved_model):
                            resolved_model = resolve_auto_model(
                                prompt=full_prompt,
                                agent_category=agent_doc.get("category"),
                            )
                            logger.info(f"Agent '{agent_name}': auto-resolved model to {resolved_model}")
                    except ImportError:
                        pass

                    # asyncio.run() is safe here — we're in a thread pool worker with no event loop
                    sdk_result = asyncio.run(_invoke_agent_via_claude_sdk(
                        system_prompt=system_prompt,
                        prompt=full_prompt,
                        model=resolved_model,
                    ))
                    output_text = sdk_result["output"]
                    tokens_used = sdk_result["tokens_used"]
                    cost = sdk_result["cost"]

                # ---- Fallback: Strands SDK (no tools) ----
                else:
                    logger.info(f"Invoking agent '{agent_name}' via Strands SDK (no tools)")
                    from strands import Agent
                    from strands.models import BedrockModel

                    model = BedrockModel(
                        model_id=agent_tools_ref.default_model_id,
                        temperature=0.3,
                        max_tokens=4096,
                    )

                    invoked_agent = Agent(
                        model=model,
                        system_prompt=system_prompt,
                        # NO tools — Strands fallback has no tool access
                    )

                    result = invoked_agent(full_prompt)
                    output_text = str(result) if result else ""

                    tokens_used = 0
                    cost = 0.0
                    if hasattr(result, "metrics"):
                        metrics = result.metrics
                        tokens_used = getattr(metrics, "total_tokens", 0)
                        cost = getattr(metrics, "total_cost", 0.0)

                elapsed = time.time() - start_time

                # Update tracking
                agent_tools_ref.total_tokens += tokens_used
                agent_tools_ref.total_cost_usd += cost

                log_entry = {
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "task": task[:200],
                    "tokens": tokens_used,
                    "cost": cost,
                    "elapsed_seconds": round(elapsed, 2),
                    "status": "completed",
                }
                agent_tools_ref.invocation_log.append(log_entry)

                logger.info(
                    f"Agent '{agent_name}' completed in {elapsed:.1f}s "
                    f"(tokens={tokens_used}, cost=${cost:.4f})"
                )

                return output_text

            except Exception as e:
                elapsed = time.time() - start_time
                error_msg = str(e)

                log_entry = {
                    "agent_id": agent_id,
                    "agent_name": agent_doc.get("name", agent_id) if 'agent_doc' in dir() else agent_id,
                    "task": task[:200],
                    "tokens": 0,
                    "cost": 0.0,
                    "elapsed_seconds": round(elapsed, 2),
                    "status": "error",
                    "error": error_msg[:500],
                }
                agent_tools_ref.invocation_log.append(log_entry)

                logger.error(f"invoke_agent failed for {agent_id}: {error_msg}")
                return f"Error invoking agent '{agent_id}': {error_msg}"

        return invoke_agent

    def get_tracking_summary(self) -> Dict[str, Any]:
        """Return runtime tracking data for the orchestrator to record."""
        return {
            "invocation_count": self.invocation_count,
            "max_invocations": self.max_invocations,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "budget_limit_usd": self.budget_limit_usd,
            "invocation_log": self.invocation_log,
        }
