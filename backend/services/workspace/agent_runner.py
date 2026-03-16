"""
Agent Runner for AI Team Workspace Feature

Executes individual agents using the Claude Agent SDK with native tool execution.
Tools (Read/Write/Edit/Bash/Glob/Grep) execute natively during generation instead
of post-hoc regex parsing.

Falls back to Strands SDK if Claude Agent SDK is unavailable.
"""

import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from services.workspace.artifact_service import ArtifactService

# Claude Agent SDK imports
try:
    from claude_agent_sdk import (
        query as claude_query,
        ClaudeAgentOptions,
        AssistantMessage,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
        ToolResultBlock,
    )
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny
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


class AgentRunner:
    """
    Runner for executing individual workspace agents.

    Primary: Claude Agent SDK with native Read/Write/Edit/Bash/Glob/Grep tools.
    Fallback: Strands SDK with regex-based tool extraction.
    """

    DEFAULT_MODEL_ID = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    DEFAULT_TEMPERATURE = 0.3
    DEFAULT_MAX_TOKENS = 8192

    def __init__(
        self,
        model_id: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        work_dir: Optional[str] = None,
    ):
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        # Store explicit user override for Claude SDK path (None means use env/default)
        self._user_model_id = model_id
        self.temperature = temperature if temperature is not None else self.DEFAULT_TEMPERATURE
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        self.work_dir = work_dir or os.getenv("WORKSPACE_DIR", "/tmp/workspace")

        if CLAUDE_SDK_AVAILABLE:
            logger.info(f"AgentRunner initialized with Claude Agent SDK (model: {os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-6')})")
        elif STRANDS_AVAILABLE:
            self.model = BedrockModel(
                model_id=self.model_id,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                streaming=False,
            )
            self.agent = Agent(model=self.model)
            logger.info(f"AgentRunner initialized with Strands fallback (model: {self.model_id})")
        else:
            raise RuntimeError("Neither Claude Agent SDK nor Strands SDK available")

    def _is_local_model(self) -> bool:
        """Check if the configured model is a local GGUF model."""
        return (
            self.model_id.startswith("local-")
            or self.model_id.startswith("local:")
        )

    async def run_agent(
        self,
        agent_blueprint: Dict[str, Any],
        context: Dict[str, Any],
        artifact_service: ArtifactService,
        project_id: str,
    ) -> Dict[str, Any]:
        """Execute a single agent with native tool execution."""
        # Route to local model path if configured
        if self._is_local_model():
            return await self._run_agent_local(agent_blueprint, context, artifact_service, project_id)
        if CLAUDE_SDK_AVAILABLE:
            return await self._run_agent_sdk(agent_blueprint, context, artifact_service, project_id)
        else:
            return await self._run_agent_strands(agent_blueprint, context, artifact_service, project_id)

    async def _run_agent_local(
        self,
        agent_blueprint: Dict[str, Any],
        context: Dict[str, Any],
        artifact_service: ArtifactService,
        project_id: str,
    ) -> Dict[str, Any]:
        """Execute agent using local GGUF model (text generation only, no tool calling)."""
        try:
            from services.local_model_service import LocalModelService

            agent_name = agent_blueprint.get("name", "Agent")
            logger.info(f"Running agent '{agent_name}' via local model: {self.model_id}")

            prompt = self.build_prompt(agent_blueprint, context)
            # Prepend a note about local model limitations
            prompt = (
                "[Local AI mode: text generation only — no tool use available]\n\n"
                + prompt
            )

            local_svc = LocalModelService()
            # Strip "local-" prefix to get the model catalog ID
            catalog_id = self.model_id.replace("local-", "")
            output = await local_svc.generate(model_id=catalog_id, prompt=prompt, max_tokens=self.max_tokens)

            # Parse any file blocks from the output (```file:path\ncontent```)
            import re
            files_created = []
            file_matches = re.findall(r'```file:([^\n]+)\n(.*?)```', output, re.DOTALL)
            for filename, content in file_matches:
                filename = filename.strip()
                content = content.strip()
                result = await artifact_service.save_file(
                    project_id=project_id, filename=filename, content=content
                )
                if result.get("success"):
                    files_created.append({
                        "filename": filename,
                        "content": content,
                        "size": result.get("size", len(content)),
                    })

            logger.info(f"Agent '{agent_name}' completed via local model: {len(files_created)} files")

            return {
                "success": True,
                "output": output,
                "files_created": files_created,
                "tool_calls": [],
                "tokens_used": len(prompt.split()) + len(output.split()),
                "cost": 0.0,
                "error": None,
            }
        except Exception as e:
            logger.error(f"Error running agent via local model: {e}")
            return {
                "success": False,
                "output": "",
                "files_created": [],
                "tool_calls": [],
                "tokens_used": 0,
                "cost": 0.0,
                "error": str(e),
            }

    async def _run_agent_sdk(
        self,
        agent_blueprint: Dict[str, Any],
        context: Dict[str, Any],
        artifact_service: ArtifactService,
        project_id: str,
    ) -> Dict[str, Any]:
        """Execute agent using Claude Agent SDK with native tools."""
        try:
            agent_id = agent_blueprint.get("agent_id")
            agent_name = agent_blueprint.get("name", agent_id)
            logger.info(f"Running agent via SDK: {agent_name} ({agent_id})")

            prompt = self.build_prompt(agent_blueprint, context)
            system_prompt = agent_blueprint.get("system_prompt", "")

            project_dir = os.path.join(self.work_dir, project_id)
            os.makedirs(project_dir, exist_ok=True)

            # Tool guard: restrict operations to project directory
            async def workspace_tool_guard(tool_name, input_data, ctx):
                BLOCKED_COMMANDS = [
                    "rm -rf /", "rm -rf ~", "git push", "curl", "wget",
                    "pip install", "npm install", "apt-get", "shutdown",
                ]

                if tool_name == "Bash":
                    command = input_data.get("command", "")
                    if any(blocked in command for blocked in BLOCKED_COMMANDS):
                        return PermissionResultDeny(message=f"Blocked: {command}")

                if tool_name in ("Write", "Edit"):
                    file_path = input_data.get("file_path", "")
                    if file_path and not file_path.startswith(project_dir):
                        return PermissionResultDeny(
                            message=f"Write outside project directory blocked: {file_path}"
                        )

                return PermissionResultAllow(updated_input=input_data)

            # Resolve model: user-selected model_id > env CLAUDE_MODEL > default
            resolved_model = self._user_model_id or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

            # Smart Model Routing: resolve "auto" to concrete model
            from services.claude_models import is_auto_model, resolve_auto_model
            if is_auto_model(resolved_model):
                resolved_model = resolve_auto_model(
                    prompt=prompt,
                    agent_category=agent_blueprint.get("category"),
                )
                logger.info(f"Agent {agent_name}: auto-resolved model to {resolved_model}")

            options = ClaudeAgentOptions(
                system_prompt=system_prompt or (
                    f"You are {agent_name}, a workspace agent. You have access to file "
                    f"and code tools. Work within the project directory."
                ),
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                permission_mode="acceptEdits",
                can_use_tool=workspace_tool_guard,
                cwd=project_dir,
                model=resolved_model,
                max_turns=30,
            )

            output_parts = []
            files_created = []
            tool_calls = []
            tokens_used = 0
            cost = 0.0

            async for message in claude_query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            output_parts.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            tool_call = {
                                "tool": block.name,
                                "input": block.input,
                                "success": True,
                                "executed": True,
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                            tool_calls.append(tool_call)

                            # Track file creation
                            if block.name in ("Write", "Edit"):
                                file_path = block.input.get("file_path", "")
                                if file_path:
                                    rel_path = os.path.relpath(file_path, project_dir)
                                    files_created.append({
                                        "filename": rel_path,
                                        "content": block.input.get("content", ""),
                                        "size": len(block.input.get("content", "")),
                                    })

                if isinstance(message, ResultMessage):
                    cost = message.total_cost_usd or 0
                    usage = message.usage or {}
                    tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

                    if message.is_error:
                        return {
                            "success": False,
                            "output": message.result or "",
                            "files_created": files_created,
                            "tool_calls": tool_calls,
                            "tokens_used": tokens_used,
                            "cost": cost,
                            "error": message.result or "SDK execution error",
                        }

            output = "\n".join(output_parts)
            logger.info(
                f"Agent {agent_name} completed via SDK: "
                f"{len(files_created)} files, {tokens_used} tokens, ${cost:.4f}"
            )

            return {
                "success": True,
                "output": output,
                "files_created": files_created,
                "tool_calls": tool_calls,
                "tokens_used": tokens_used,
                "cost": cost,
                "error": None,
            }

        except Exception as e:
            logger.error(f"Error running agent via SDK: {e}")
            return {
                "success": False,
                "output": "",
                "files_created": [],
                "tool_calls": [],
                "tokens_used": 0,
                "cost": 0.0,
                "error": str(e),
            }

    async def _run_agent_strands(
        self,
        agent_blueprint: Dict[str, Any],
        context: Dict[str, Any],
        artifact_service: ArtifactService,
        project_id: str,
    ) -> Dict[str, Any]:
        """Fallback: Execute agent using Strands SDK with regex tool parsing."""
        import re

        FILE_WRITE_PATTERN = r'```file:([^\n]+)\n(.*?)```'
        BASH_PATTERN = r'```bash\n(.*?)```'

        try:
            agent_id = agent_blueprint.get("agent_id")
            agent_name = agent_blueprint.get("name", agent_id)
            logger.info(f"Running agent via Strands: {agent_name} ({agent_id})")

            prompt = self.build_prompt(agent_blueprint, context)
            response = self.agent(prompt)

            if hasattr(response, 'content'):
                output = response.content
            elif isinstance(response, str):
                output = response
            else:
                output = str(response)

            # Execute embedded tools (file writes via regex)
            files_created = []
            tool_calls = []

            file_matches = re.findall(FILE_WRITE_PATTERN, output, re.DOTALL)
            for filename, content in file_matches:
                filename = filename.strip()
                content = content.strip()
                result = await artifact_service.save_file(
                    project_id=project_id, filename=filename, content=content
                )
                tool_calls.append({
                    "tool": "file_write",
                    "filename": filename,
                    "success": result.get("success", False),
                    "executed": True,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                if result.get("success"):
                    files_created.append({
                        "filename": filename,
                        "content": content,
                        "size": result.get("size", len(content)),
                    })

            # Log bash commands (not executed for safety in Strands mode)
            bash_matches = re.findall(BASH_PATTERN, output, re.DOTALL)
            for command in bash_matches:
                tool_calls.append({
                    "tool": "bash",
                    "command": command.strip(),
                    "success": True,
                    "executed": False,
                    "note": "Bash commands logged but not executed (Strands fallback)",
                    "timestamp": datetime.utcnow().isoformat(),
                })

            tokens_used = (len(prompt) + len(output)) // 4
            cost = (int(tokens_used * 0.7) / 1000 * 0.003) + (int(tokens_used * 0.3) / 1000 * 0.015)

            return {
                "success": True,
                "output": output,
                "files_created": files_created,
                "tool_calls": tool_calls,
                "tokens_used": tokens_used,
                "cost": cost,
                "error": None,
            }

        except Exception as e:
            logger.error(f"Error running agent via Strands: {e}")
            return {
                "success": False,
                "output": "",
                "files_created": [],
                "tool_calls": [],
                "tokens_used": 0,
                "cost": 0.0,
                "error": str(e),
            }

    def build_prompt(
        self,
        agent_blueprint: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        """Build the complete prompt for an agent."""
        parts = []

        name = agent_blueprint.get("name", "Agent")
        category = agent_blueprint.get("category", "developer")
        capabilities = agent_blueprint.get("capabilities", [])

        parts.append(f"You are {name}, a {category} agent.")

        if capabilities:
            parts.append(f"Your capabilities: {', '.join(capabilities)}")

        project_config = context.get("project_config", {})
        if project_config:
            parts.append(
                f"Project: {project_config.get('name', 'Unknown')} - "
                f"{project_config.get('description', '')}"
            )
            tech_stack = project_config.get("tech_stack", [])
            if tech_stack:
                parts.append(f"Tech Stack: {', '.join(tech_stack)}")

        previous_outputs = context.get("previous_outputs", {})
        if previous_outputs:
            parts.append("\nPrevious work from other agents:")
            for prev_agent_id, output_data in previous_outputs.items():
                output_text = output_data.get("output", "")
                if output_text:
                    if len(output_text) > 4000:
                        output_text = output_text[:4000] + "\n...[truncated]..."
                    parts.append(f"\n--- {prev_agent_id} ---\n{output_text}")

        available_files = context.get("available_files", [])
        if available_files:
            file_list = ", ".join(f.get("filename", "unknown") for f in available_files)
            parts.append(f"\nAvailable files: {file_list}")

        config = agent_blueprint.get("config", {})
        task = config.get("task", "")
        if task:
            parts.append(f"\nYour task:\n{task}")

        return "\n\n".join(parts)


def create_agent_runner(
    model_id: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    work_dir: Optional[str] = None,
) -> AgentRunner:
    """Create a new AgentRunner instance."""
    return AgentRunner(
        model_id=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        work_dir=work_dir,
    )
