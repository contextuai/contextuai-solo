"""
Workspace Orchestrator for AI Team Workspace Feature

Main orchestration engine that coordinates agent execution, manages job processing,
and handles the execution lifecycle for workspace projects.
"""

import logging
import asyncio
import os
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.workspace_project_repository import WorkspaceProjectRepository
from repositories.workspace_execution_repository import WorkspaceExecutionRepository
from repositories.workspace_job_repository import WorkspaceJobRepository
from repositories.workspace_agent_repository import WorkspaceAgentRepository
from repositories.workspace_checkpoint_repository import WorkspaceCheckpointRepository

from services.workspace.agent_runner import AgentRunner, create_agent_runner
from services.workspace.context_manager import ContextManager
from services.workspace.stream_service import StreamService, stream_service
from services.workspace.artifact_service import ArtifactService, artifact_service
from services.workspace.checkpoint_service import CheckpointService, checkpoint_service
from services.workspace.agent_registry import AgentRegistry, agent_registry

# Configure logging
logger = logging.getLogger(__name__)


class WorkspaceOrchestrator:
    """
    Orchestrator for workspace project executions.

    Coordinates the execution of multiple agents, manages job processing,
    handles checkpoints, and maintains execution state.
    """

    # Worker identification
    WORKER_ID_PREFIX = "workspace-worker"

    # Job types to process
    JOB_TYPES = ["execute_workspace_project"]

    # Poll interval for job queue (seconds)
    POLL_INTERVAL = 2.0

    # Lock duration for jobs (seconds)
    LOCK_DURATION = 600  # 10 minutes

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize the orchestrator.

        Args:
            db: AsyncIOMotorDatabase instance
        """
        self.db = db
        self.worker_id = f"{self.WORKER_ID_PREFIX}-{uuid.uuid4().hex[:8]}"

        # Initialize repositories
        self.project_repo = WorkspaceProjectRepository(db)
        self.execution_repo = WorkspaceExecutionRepository(db)
        self.job_repo = WorkspaceJobRepository(db)
        self.agent_repo = WorkspaceAgentRepository(db)
        self.checkpoint_repo = WorkspaceCheckpointRepository(db)

        # Running state
        self._running = False
        self._current_job = None

        logger.info(f"WorkspaceOrchestrator initialized with worker ID: {self.worker_id}")

    async def run(self) -> None:
        """
        Main worker loop.

        Continuously polls for jobs, processes them, and updates status.
        Runs until stopped via stop() method.
        """
        self._running = True
        logger.info(f"Worker {self.worker_id} starting main loop")

        while self._running:
            try:
                # Release any stale jobs from crashed workers
                released = await self.job_repo.release_stale_jobs(
                    stale_threshold_seconds=self.LOCK_DURATION
                )
                if released > 0:
                    logger.info(f"Released {released} stale jobs")

                # Get next pending job
                pending_job = await self.job_repo.get_pending_job(
                    job_types=self.JOB_TYPES
                )

                if pending_job:
                    # Claim the job atomically
                    job = await self.job_repo.claim_job(
                        job_id=pending_job.get("job_id"),
                        worker_id=self.worker_id,
                        lock_duration_seconds=self.LOCK_DURATION
                    )

                    if job:
                        self._current_job = job
                        await self.process_job(job)
                        self._current_job = None
                    else:
                        logger.debug("Job was claimed by another worker")
                else:
                    logger.debug("No pending jobs, waiting...")

                # Wait before next poll
                await asyncio.sleep(self.POLL_INTERVAL)

            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                await asyncio.sleep(self.POLL_INTERVAL * 2)  # Back off on error

        logger.info(f"Worker {self.worker_id} stopped")

    def stop(self) -> None:
        """Stop the worker loop."""
        self._running = False
        logger.info(f"Worker {self.worker_id} stopping...")

    async def execute_project(
        self, project_id: str, execution_id: str, user_id: str = None
    ) -> None:
        """
        Execute a workspace project directly (called from Celery task).

        Bridges the Celery dispatch to the process_job() pipeline by
        constructing a synthetic job payload.

        Args:
            project_id: Project to execute
            execution_id: Execution tracking ID
            user_id: User who initiated
        """
        logger.info(f"Direct execution: project={project_id}, execution={execution_id}")

        # Load execution to get team agent IDs
        execution = await self.execution_repo.get_by_id(execution_id)
        if not execution:
            raise Exception(f"Execution {execution_id} not found")

        team_agent_ids = execution.get("team_agent_ids", [])

        # Fall back to project's team_agent_ids if execution doesn't have them
        if not team_agent_ids:
            project = await self.project_repo.get_by_id(project_id)
            if project:
                team_agent_ids = project.get("team_agent_ids", [])
                logger.info(f"Loaded {len(team_agent_ids)} agents from project config")

        # Build synthetic job payload matching what process_job expects
        job = {
            "job_id": f"celery-{execution_id}",
            "payload": {
                "execution_id": execution_id,
                "project_id": project_id,
                "user_id": user_id,
                "team_agent_ids": team_agent_ids,
                "resume": False,
            }
        }

        await self.process_job(job)

    async def resume_project(
        self, project_id: str, execution_id: str
    ) -> None:
        """
        Resume a paused workspace project (called from Celery task).

        Args:
            project_id: Project to resume
            execution_id: Execution to resume (if None, finds latest)
        """
        logger.info(f"Resume execution: project={project_id}, execution={execution_id}")

        # Find the execution to resume
        if not execution_id:
            # Find the latest paused execution for this project
            executions = await self.execution_repo.get_by_project(project_id)
            paused = [e for e in executions if e.get("status") == "paused"]
            if not paused:
                raise Exception(f"No paused execution found for project {project_id}")
            execution = paused[0]
            execution_id = execution.get("execution_id")
        else:
            execution = await self.execution_repo.get_by_id(execution_id)
            if not execution:
                raise Exception(f"Execution {execution_id} not found")

        team_agent_ids = execution.get("team_agent_ids", [])

        # Fall back to project's team_agent_ids if execution doesn't have them
        if not team_agent_ids:
            project = await self.project_repo.get_by_id(project_id)
            if project:
                team_agent_ids = project.get("team_agent_ids", [])

        # Get last completed step
        steps = execution.get("steps", [])
        last_completed = {}
        for step in steps:
            if step.get("status") == "completed":
                last_completed = step

        # Update status back to running
        await self.execution_repo.update_status(execution_id, "running")

        # Build synthetic job payload for resume
        job = {
            "job_id": f"celery-resume-{execution_id}",
            "payload": {
                "execution_id": execution_id,
                "project_id": project_id,
                "team_agent_ids": team_agent_ids,
                "resume": True,
                "last_completed_step": last_completed,
            }
        }

        await self.process_job(job)

    async def process_job(self, job: Dict[str, Any]) -> None:
        """
        Process a single job.

        Handles the complete execution lifecycle for a workspace project.

        Args:
            job: Job document with payload containing execution details
        """
        job_id = job.get("job_id")
        payload = job.get("payload", {})
        execution_id = payload.get("execution_id")

        logger.info(f"Processing job {job_id} for execution {execution_id}")

        try:
            # Get execution record
            execution = await self.execution_repo.get_by_id(execution_id)
            if not execution:
                logger.error(f"Execution not found: {execution_id}")
                await self.job_repo.fail_job(job_id, "Execution not found", retry=False)
                return

            # Check if execution is cancelled
            if execution.get("status") == "cancelled":
                logger.info(f"Execution {execution_id} was cancelled")
                await self.job_repo.complete_job(job_id, {"status": "cancelled"})
                return

            # Get project
            project_id = payload.get("project_id")
            project = await self.project_repo.get_by_id(project_id)
            if not project:
                logger.error(f"Project not found: {project_id}")
                await self.finalize_execution(execution, False, "Project not found")
                await self.job_repo.fail_job(job_id, "Project not found", retry=False)
                return

            # Get agents
            agent_ids = payload.get("team_agent_ids", [])
            agents = await agent_registry.get_agents_by_ids(agent_ids, self.agent_repo)

            if not agents:
                logger.error(f"No agents found for project {project_id}")
                await self.finalize_execution(execution, False, "No agents found")
                await self.job_repo.fail_job(job_id, "No agents found", retry=False)
                return

            # Get recommended execution order
            order_result = await agent_registry.get_recommended_order(agent_ids, self.agent_repo)
            ordered_agents = order_result.get("agents", agents)

            # Update execution status to running
            await self.execution_repo.update_status(execution_id, "running")

            # Emit execution started event
            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_EXECUTION_STARTED,
                data=stream_service.create_execution_started_event(
                    project_id=project_id,
                    project_name=project.get("name", "Unknown"),
                    agent_count=len(ordered_agents)
                ),
                execution_repo=self.execution_repo
            )

            # Initialize or restore context
            is_resume = payload.get("resume", False)
            if is_resume:
                last_step = payload.get("last_completed_step", {})
                context = await self._restore_context(execution, last_step)
            else:
                context = ContextManager()

            # Add project config to context
            context.set_shared_state("project_config", {
                "name": project.get("name"),
                "description": project.get("description"),
                "tech_stack": project.get("tech_stack", []),
                "complexity": project.get("complexity")
            })

            # Resolve model_id from project (user-selected Claude model)
            project_model_id = project.get("model_id")

            # Dispatch based on project type
            project_type = project.get("project_type", "build")

            if project_type == "workshop":
                # Workshop mode: use WorkshopRunner for brainstorming/strategy sessions
                from services.workspace.workshop_runner import WorkshopRunner
                workshop_runner = WorkshopRunner(model_id=project_model_id)
                workshop_config = project.get("workshop_config", {})
                result = await workshop_runner.run_workshop(
                    project=project,
                    agents=ordered_agents,
                    workshop_config=workshop_config,
                    context_manager=context,
                    stream_service=stream_service,
                    execution_id=execution_id,
                    execution_repo=self.execution_repo,
                    artifact_service=artifact_service,
                )
                # Store workshop result in execution for frontend retrieval
                if result.get("success"):
                    workshop_result_data = {
                        "contributions": result.get("contributions", []),
                        "compiled_output": result.get("compiled_output", ""),
                        "output_format": workshop_config.get("output_format", "report"),
                        "artifact_filename": result.get("artifact_filename", ""),
                    }
                    await self.execution_repo.update_by_execution_id(execution_id, {
                        "context.workshop_result": workshop_result_data
                    })
                success = result.get("success", False)
                error = result.get("error") if not success else None
            else:
                # Build mode: sequential agent execution with optional git integration
                config = project.get("config", {})
                git_repo_url = config.get("github_repo_url", "")
                git_persona_id = project.get("git_persona_id", "")
                auto_create_pr = config.get("auto_create_pr", False)
                git_work_dir = None
                git_token = ""

                # --- Git clone phase (if repo URL configured) ---
                if git_repo_url:
                    git_token = await self._resolve_git_credentials(git_persona_id)
                    import tempfile
                    git_work_dir = os.path.join(
                        tempfile.gettempdir(),
                        "workspace-builds",
                        f"{project_id}-{uuid.uuid4().hex[:8]}"
                    )
                    os.makedirs(git_work_dir, exist_ok=True)

                    clone_ok = await self._git_clone_repo(
                        execution_id=execution_id,
                        repo_url=git_repo_url,
                        work_dir=git_work_dir,
                        token=git_token,
                    )
                    if not clone_ok:
                        error = "Failed to clone git repository"
                        await self.finalize_execution(execution, False, error)
                        await self.job_repo.fail_job(job_id, error, retry=False)
                        return

                    # Initialise artifact service to write into the cloned repo
                    await artifact_service.initialize_directory(
                        project_id, base_path=git_work_dir
                    )

                    # Let agents know the working directory
                    context.set_shared_state("git_work_dir", git_work_dir)
                    context.set_shared_state("git_repo_url", git_repo_url)

                # --- Execute agents ---
                success, error = await self.execute_agents(
                    execution=execution,
                    agents=ordered_agents,
                    context=context,
                    model_id=project_model_id
                )

                # --- Git commit/push/PR phase (if repo URL configured and agents succeeded) ---
                pr_url = None
                if git_repo_url and success:
                    pr_url = await self._git_commit_and_push(
                        execution_id=execution_id,
                        work_dir=git_work_dir or "",
                        project_name=project.get("name", "workspace-project"),
                        repo_url=git_repo_url,
                        token=git_token,
                        create_pr=auto_create_pr,
                    )
                    if pr_url:
                        # Store PR URL in execution result
                        await self.execution_repo.update_by_execution_id(
                            execution_id, {"context.pr_url": pr_url}
                        )

            # Finalize execution
            await self.finalize_execution(execution, success, error)

            # Complete job
            await self.job_repo.complete_job(job_id, {
                "success": success,
                "error": error,
                **({"pr_url": pr_url} if project_type == "build" and git_repo_url else {}),
            })

        except Exception as e:
            logger.error(f"Error processing job {job_id}: {e}")
            if execution_id:
                await self.finalize_execution(
                    {"execution_id": execution_id},
                    False,
                    str(e)
                )
            await self.job_repo.fail_job(job_id, str(e), retry=True)

    async def execute_agents(
        self,
        execution: Dict[str, Any],
        agents: List[Dict[str, Any]],
        context: ContextManager,
        model_id: str = None
    ) -> tuple:
        """
        Execute agents sequentially.

        Args:
            execution: Execution document
            agents: Ordered list of agent blueprints
            context: ContextManager with shared state
            model_id: Optional Claude model ID for agent execution

        Returns:
            Tuple of (success: bool, error: Optional[str])
        """
        execution_id = execution.get("execution_id")
        project_id = execution.get("project_id")

        # Create agent runner with optional model_id override
        runner = create_agent_runner(model_id=model_id)

        total_tokens = 0
        total_cost = 0.0

        for step_index, agent in enumerate(agents):
            agent_id = agent.get("agent_id")
            agent_name = agent.get("name", agent_id)

            try:
                # Check if execution is still active
                current_execution = await self.execution_repo.get_by_id(execution_id)
                status = current_execution.get("status") if current_execution else "unknown"

                if status == "cancelled":
                    logger.info(f"Execution {execution_id} cancelled, stopping")
                    return False, "Execution cancelled"

                if status == "paused":
                    logger.info(f"Execution {execution_id} paused, stopping")
                    return False, "Execution paused"

                # Add step to execution
                await self.execution_repo.add_step(
                    execution_id=execution_id,
                    step_data={
                        "agent_id": agent_id,
                        "agent_name": agent_name,
                        "step_index": step_index
                    }
                )

                # Emit agent started event
                await stream_service.emit_event(
                    execution_id=execution_id,
                    event_type=stream_service.EVENT_AGENT_STARTED,
                    data=stream_service.create_agent_started_event(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        step_index=step_index
                    ),
                    execution_repo=self.execution_repo
                )

                logger.info(f"Executing agent {step_index + 1}/{len(agents)}: {agent_name}")

                # Build context for this agent
                agent_context = context.get_context_for_agent(agent_id, agent)
                agent_context["project_config"] = context.get_shared_state("project_config")

                # Run the agent
                result = await runner.run_agent(
                    agent_blueprint=agent,
                    context=agent_context,
                    artifact_service=artifact_service,
                    project_id=project_id
                )

                if not result.get("success"):
                    error = result.get("error", "Unknown error")
                    logger.error(f"Agent {agent_name} failed: {error}")

                    # Update step as failed
                    await self.execution_repo.update_step(
                        execution_id=execution_id,
                        step_id=agent_id,
                        update_data={"status": "failed", "error": error}
                    )

                    # Emit agent failed event
                    await stream_service.emit_event(
                        execution_id=execution_id,
                        event_type=stream_service.EVENT_AGENT_FAILED,
                        data=stream_service.create_agent_failed_event(
                            agent_id=agent_id,
                            agent_name=agent_name,
                            error=error
                        ),
                        execution_repo=self.execution_repo
                    )

                    return False, f"Agent '{agent_name}' failed: {error}"

                # Add agent output to context
                context.add_agent_output(
                    agent_id=agent_id,
                    output=result.get("output", ""),
                    files_created=result.get("files_created", [])
                )

                # Update metrics
                tokens = result.get("tokens_used", 0)
                cost = result.get("cost", 0.0)
                total_tokens += tokens
                total_cost += cost

                await self.execution_repo.update_metrics(
                    execution_id=execution_id,
                    tokens=tokens,
                    cost=cost
                )

                # Emit file creation events
                for file_info in result.get("files_created", []):
                    await stream_service.emit_event(
                        execution_id=execution_id,
                        event_type=stream_service.EVENT_FILE_CREATED,
                        data=stream_service.create_file_created_event(
                            agent_id=agent_id,
                            filename=file_info.get("filename", "unknown"),
                            size=file_info.get("size", 0)
                        ),
                        execution_repo=self.execution_repo
                    )

                # Update step as completed
                await self.execution_repo.update_step(
                    execution_id=execution_id,
                    step_id=agent_id,
                    update_data={
                        "status": "completed",
                        "tokens_used": tokens,
                        "cost": cost,
                        "files_created": len(result.get("files_created", []))
                    }
                )

                # Emit agent completed event
                file_names = [f.get("filename") for f in result.get("files_created", [])]
                await stream_service.emit_event(
                    execution_id=execution_id,
                    event_type=stream_service.EVENT_AGENT_COMPLETED,
                    data=stream_service.create_agent_completed_event(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        files_created=file_names,
                        tokens_used=tokens,
                        cost=cost
                    ),
                    execution_repo=self.execution_repo
                )

                # Check for checkpoint request
                checkpoint_request = self._check_for_checkpoint(agent, result)
                if checkpoint_request:
                    await self.handle_checkpoint(execution, agent, checkpoint_request)
                    # After checkpoint, execution is paused
                    return False, "Execution paused for checkpoint"

            except Exception as e:
                logger.error(f"Error executing agent {agent_name}: {e}")
                return False, f"Error executing agent '{agent_name}': {str(e)}"

        logger.info(
            f"All {len(agents)} agents completed. "
            f"Total tokens: {total_tokens}, Total cost: ${total_cost:.4f}"
        )

        return True, None

    async def handle_checkpoint(
        self,
        execution: Dict[str, Any],
        agent: Dict[str, Any],
        checkpoint_data: Dict[str, Any]
    ) -> None:
        """
        Create a checkpoint and pause execution.

        Args:
            execution: Execution document
            agent: Agent that triggered the checkpoint
            checkpoint_data: Checkpoint configuration
        """
        execution_id = execution.get("execution_id")
        project_id = execution.get("project_id")
        agent_id = agent.get("agent_id")

        logger.info(f"Creating checkpoint for execution {execution_id}")

        # Create checkpoint
        checkpoint = await checkpoint_service.create_checkpoint(
            execution_id=execution_id,
            project_id=project_id,
            step_id=agent_id,
            agent_id=agent_id,
            checkpoint_type=checkpoint_data.get("type", "approval"),
            title=checkpoint_data.get("title", "Review Required"),
            description=checkpoint_data.get("description", "Please review before continuing"),
            options=checkpoint_data.get("options", checkpoint_service.build_approval_options()),
            checkpoint_repo=self.checkpoint_repo,
            context=checkpoint_data.get("context")
        )

        if checkpoint:
            # Emit checkpoint event
            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_CHECKPOINT_CREATED,
                data=stream_service.create_checkpoint_event(
                    checkpoint_id=checkpoint.get("checkpoint_id", ""),
                    checkpoint_type=checkpoint_data.get("type", "approval"),
                    agent_id=agent_id,
                    title=checkpoint_data.get("title", "Review Required")
                ),
                execution_repo=self.execution_repo
            )

            # Pause execution
            await self.execution_repo.update_status(execution_id, "paused")

    async def finalize_execution(
        self,
        execution: Dict[str, Any],
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """
        Complete an execution with final status.

        Args:
            execution: Execution document
            success: Whether execution completed successfully
            error: Optional error message
        """
        execution_id = execution.get("execution_id")
        project_id = execution.get("project_id", "")

        logger.info(f"Finalizing execution {execution_id}: success={success}")

        # Get final metrics
        final_execution = await self.execution_repo.get_by_id(execution_id)
        metrics = final_execution.get("metrics", {}) if final_execution else {}

        if success:
            # Update status to completed
            await self.execution_repo.update_status(execution_id, "completed")

            # Create ZIP archive of artifacts
            zip_result = await artifact_service.create_zip(project_id)
            artifacts_url = zip_result.get("path") if zip_result.get("success") else None

            # Get file count
            files = await artifact_service.list_files(project_id)

            # Emit completion event
            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_EXECUTION_COMPLETED,
                data=stream_service.create_completed_event(
                    total_cost=metrics.get("total_cost", 0.0),
                    artifacts_url=artifacts_url,
                    total_tokens=metrics.get("total_tokens", 0),
                    duration_ms=metrics.get("duration_ms", 0),
                    files_created=len(files)
                ),
                execution_repo=self.execution_repo
            )

            # Set execution result
            await self.execution_repo.set_result(
                execution_id=execution_id,
                result={
                    "success": True,
                    "artifacts_url": artifacts_url,
                    "files_created": len(files),
                    "total_cost": metrics.get("total_cost", 0.0),
                    "total_tokens": metrics.get("total_tokens", 0)
                }
            )

        else:
            # Update status to failed
            await self.execution_repo.update_status(execution_id, "failed", error)

            # Emit failure event
            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_EXECUTION_FAILED,
                data=stream_service.create_failed_event(
                    error=error or "Unknown error",
                    total_cost=metrics.get("total_cost", 0.0)
                ),
                execution_repo=self.execution_repo
            )

    def _check_for_checkpoint(
        self,
        agent: Dict[str, Any],
        result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Check if agent requires a checkpoint.

        Args:
            agent: Agent blueprint
            result: Agent execution result

        Returns:
            Checkpoint data if required, None otherwise
        """
        config = agent.get("config", {})

        # Check if agent always requires approval
        if config.get("requires_approval"):
            return {
                "type": "approval",
                "title": f"Review output from {agent.get('name', 'Agent')}",
                "description": "Please review the agent's work before continuing.",
                "options": checkpoint_service.build_approval_options()
            }

        # Check for specific checkpoint triggers in output
        output = result.get("output", "")
        if "CHECKPOINT:" in output or "[CHECKPOINT]" in output:
            return {
                "type": "review",
                "title": f"Agent {agent.get('name', 'Agent')} requests review",
                "description": "The agent has requested human review.",
                "options": checkpoint_service.build_approval_options()
            }

        return None

    async def _restore_context(
        self,
        execution: Dict[str, Any],
        last_step: Dict[str, Any]
    ) -> ContextManager:
        """
        Restore context from a previous execution state.

        Args:
            execution: Execution document
            last_step: Last completed step info

        Returns:
            Restored ContextManager
        """
        # For now, create a fresh context
        # In production, this would restore from stored state
        context = ContextManager()

        # Restore outputs from completed steps
        steps = execution.get("steps", [])
        for step in steps:
            if step.get("status") == "completed":
                agent_id = step.get("agent_id")
                # Note: Would need to store outputs to fully restore
                context.add_agent_output(agent_id, "[Restored from previous run]", [])

        return context


    # =========================================================================
    # Git Integration for Build Projects
    # =========================================================================

    async def _resolve_git_credentials(self, persona_id: Optional[str]) -> str:
        """Resolve Git token from a persona ID.

        Reuses the same credential resolution pattern as CodeMorph.
        """
        if not persona_id:
            return ""
        try:
            from repositories.persona_repository import PersonaRepository
            from database import get_async_db
            db = get_async_db()
            persona_repo = PersonaRepository(db)
            persona = await persona_repo.get_by_id_with_credentials(persona_id)
            if not persona:
                logger.warning(f"Git persona {persona_id} not found")
                return ""
            credentials = persona.get("credentials", {})
            token = credentials.get("token", "")
            return token
        except Exception as e:
            logger.error(f"Failed to resolve git credentials: {e}")
            return ""

    async def _git_clone_repo(
        self,
        execution_id: str,
        repo_url: str,
        work_dir: str,
        branch: str = "main",
        token: str = ""
    ) -> bool:
        """Clone a git repository for a build project.

        Uses CodeMorph's git_tool for the actual clone operation.
        """
        try:
            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_GIT_PHASE,
                data=stream_service.create_git_phase_event(
                    "clone", f"Cloning repository: {repo_url}",
                    {"repo_url": repo_url, "branch": branch}
                ),
                execution_repo=self.execution_repo,
            )

            from services.codemorph.tools.git_tool import git_clone
            result = git_clone(
                repo_url=repo_url, target_dir=work_dir,
                branch=branch, token=token
            )
            if str(result).startswith("Error (exit code"):
                logger.error(f"Git clone failed: {result}")
                await stream_service.emit_event(
                    execution_id=execution_id,
                    event_type=stream_service.EVENT_GIT_PHASE,
                    data=stream_service.create_git_phase_event(
                        "clone", f"Clone failed: {result}"
                    ),
                    execution_repo=self.execution_repo,
                )
                return False

            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_GIT_PHASE,
                data=stream_service.create_git_phase_event(
                    "clone", "Repository cloned successfully"
                ),
                execution_repo=self.execution_repo,
            )
            return True
        except Exception as e:
            logger.error(f"Git clone error: {e}")
            return False

    async def _git_commit_and_push(
        self,
        execution_id: str,
        work_dir: str,
        project_name: str,
        repo_url: str,
        token: str = "",
        create_pr: bool = True,
        base_branch: str = "main"
    ) -> Optional[str]:
        """Commit changes, push to a new branch, and optionally create a PR.

        Returns the PR URL if created, or None.
        """
        import subprocess as _sp

        try:
            # Check if there are changes
            diff = _sp.run(
                ["git", "diff", "--stat"], cwd=work_dir,
                capture_output=True, text=True, timeout=30
            )
            untracked = _sp.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=work_dir, capture_output=True, text=True, timeout=30
            )
            has_changes = bool(diff.stdout.strip() or untracked.stdout.strip())

            if not has_changes:
                logger.info("No changes to commit")
                await stream_service.emit_event(
                    execution_id=execution_id,
                    event_type=stream_service.EVENT_GIT_PHASE,
                    data=stream_service.create_git_phase_event(
                        "commit", "No changes to commit"
                    ),
                    execution_repo=self.execution_repo,
                )
                return None

            # Determine branch name
            safe_name = project_name.lower().replace(" ", "-")[:30]
            branch_name = f"workspace/{safe_name}-{uuid.uuid4().hex[:8]}"

            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_GIT_PHASE,
                data=stream_service.create_git_phase_event(
                    "commit", f"Staging and committing on branch: {branch_name}"
                ),
                execution_repo=self.execution_repo,
            )

            # Stage all changes on current branch first, then git_push
            # creates the new branch AND pushes.
            _sp.run(["git", "add", "-A"], cwd=work_dir,
                    capture_output=True, text=True, timeout=60)
            commit_res = _sp.run(
                ["git", "commit", "-m",
                 f"feat: {project_name} - generated by ContextuAI Workspace"],
                cwd=work_dir, capture_output=True, text=True, timeout=60
            )
            logger.info(f"Commit result: {commit_res.stdout.strip()}")

            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_GIT_PHASE,
                data=stream_service.create_git_phase_event(
                    "commit", "Changes committed successfully",
                    {"branch": branch_name}
                ),
                execution_repo=self.execution_repo,
            )

            # Push (git_push creates the branch and pushes in one step)
            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_GIT_PHASE,
                data=stream_service.create_git_phase_event(
                    "push", f"Pushing branch {branch_name}..."
                ),
                execution_repo=self.execution_repo,
            )

            from services.codemorph.tools.git_tool import git_push
            push_result = git_push(
                repo_dir=work_dir, branch=branch_name, token=token
            )
            if str(push_result).startswith("Error"):
                logger.error(f"Push failed: {push_result}")
                await stream_service.emit_event(
                    execution_id=execution_id,
                    event_type=stream_service.EVENT_GIT_PHASE,
                    data=stream_service.create_git_phase_event(
                        "push", f"Push failed: {push_result}"
                    ),
                    execution_repo=self.execution_repo,
                )
                return None

            await stream_service.emit_event(
                execution_id=execution_id,
                event_type=stream_service.EVENT_GIT_PHASE,
                data=stream_service.create_git_phase_event(
                    "push", "Branch pushed successfully"
                ),
                execution_repo=self.execution_repo,
            )

            # Create PR
            pr_url = None
            if create_pr and token:
                await stream_service.emit_event(
                    execution_id=execution_id,
                    event_type=stream_service.EVENT_GIT_PHASE,
                    data=stream_service.create_git_phase_event(
                        "pr_create", "Creating pull request..."
                    ),
                    execution_repo=self.execution_repo,
                )

                from services.codemorph.tools.github_tool import create_pull_request
                pr_url = create_pull_request(
                    repo_url=repo_url,
                    head_branch=branch_name,
                    base_branch=base_branch,
                    title=f"feat: {project_name}",
                    body=(
                        f"## AI Workspace: {project_name}\n\n"
                        f"This PR was generated by ContextuAI AI Team Workspace.\n\n"
                        f"---\n*Generated automatically by ContextuAI*"
                    ),
                    token=token,
                )

                if pr_url and not pr_url.startswith("Error"):
                    await stream_service.emit_event(
                        execution_id=execution_id,
                        event_type=stream_service.EVENT_GIT_PHASE,
                        data=stream_service.create_git_phase_event(
                            "pr_create", "Pull request created!",
                            {"pr_url": pr_url}
                        ),
                        execution_repo=self.execution_repo,
                    )
                else:
                    logger.warning(f"PR creation returned: {pr_url}")
                    pr_url = None

            return pr_url

        except Exception as e:
            logger.error(f"Git commit/push error: {e}")
            return None


def create_orchestrator(db: AsyncIOMotorDatabase) -> WorkspaceOrchestrator:
    """
    Factory function to create an orchestrator.

    Args:
        db: AsyncIOMotorDatabase instance

    Returns:
        Configured WorkspaceOrchestrator
    """
    return WorkspaceOrchestrator(db)
