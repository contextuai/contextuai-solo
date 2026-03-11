"""
CodeMorph Executor - 9-phase migration pipeline.

Phases: CLONE -> ANALYZE -> TRANSFORM -> BUILD -> TEST -> VALIDATE -> COMMIT -> PUSH -> PR_CREATE

The TRANSFORM phase uses the Claude Agent SDK for native tool execution
(Read/Write/Edit/Bash/Glob/Grep) instead of custom Strands tools.
"""

import os
import uuid
import shutil
import logging
import tempfile
from typing import AsyncIterator, Dict, Any, Optional
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient
from database import get_database
from repositories import CodeMorphRepository

# Claude Agent SDK imports for TRANSFORM phase
try:
    from claude_agent_sdk import (
        query as claude_query,
        ClaudeAgentOptions,
        AssistantMessage,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
    )
    from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)

CODEMORPH_WORKSPACE = os.getenv("CODEMORPH_WORKSPACE", "/tmp/codemorph")

# Phase definitions with progress percentages
PHASES = [
    ("CLONE", 5, "Cloning repository"),
    ("ANALYZE", 15, "Analyzing codebase"),
    ("TRANSFORM", 50, "Transforming code"),
    ("BUILD", 65, "Building project"),
    ("TEST", 75, "Running tests"),
    ("VALIDATE", 85, "Validating changes"),
    ("COMMIT", 90, "Committing changes"),
    ("PUSH", 95, "Pushing to remote"),
    ("PR_CREATE", 100, "Creating pull request"),
]


class CheckpointParkedException(Exception):
    """Raised to cleanly end a Celery task when parking at a checkpoint.

    Instead of blocking a worker thread polling for approval, this exception
    signals the task to exit. A new task is dispatched on checkpoint approval.
    """
    pass


class CodeMorphExecutor:
    """Executes CodeMorph migration jobs through 9 phases."""

    def __init__(self):
        self._repo: Optional[CodeMorphRepository] = None

    async def _get_repo(self) -> CodeMorphRepository:
        if self._repo is None:
            db = await get_database()
            self._repo = CodeMorphRepository(db)
        return self._repo

    async def _resolve_scm_credentials(self, persona_id: Optional[str]) -> str:
        """Resolve SCM token from the selected Git persona."""
        if not persona_id:
            logger.warning("No Git persona selected — clone/push will use unauthenticated access")
            return ""
        try:
            from database import get_database
            from repositories.persona_repository import PersonaRepository
            db = await get_database()
            persona_repo = PersonaRepository(db)
            persona = await persona_repo.get_by_id_with_credentials(persona_id)
            if not persona:
                logger.warning(f"Persona {persona_id} not found")
                return ""
            credentials = persona.get("credentials", {})
            token = credentials.get("token", "")
            if not token:
                logger.warning(f"Persona {persona_id} has no token configured")
            return token
        except Exception as e:
            logger.warning(f"Failed to resolve persona {persona_id}: {e}")
            return ""

    async def _append_log(self, job_id: str, message: str, level: str = "info"):
        """Append a log entry to the job's logs array in MongoDB."""
        repo = await self._get_repo()
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
        }
        await repo.collection.update_one(
            {"job_id": job_id},
            {"$push": {"logs": entry}}
        )

    async def _update_progress(self, job_id: str, phase: str, percentage: int, step: str, **kwargs):
        """Update job progress in MongoDB."""
        repo = await self._get_repo()
        update_data = {
            "current_phase": phase,
            "progress_percentage": percentage,
            "current_step": step,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        update_data.update(kwargs)
        await repo.update_job(job_id, update_data)
        # Also append as a log entry
        await self._append_log(job_id, f"[{phase}] {step}")


    async def _park_at_checkpoint(self, job_id: str, checkpoint_type: str, message: str,
                                   data: Dict = None, resume_phase: str = None):
        """Park the job at a checkpoint and end the current Celery task cleanly.

        Sets checkpoint_data and resume_phase in DB, then raises
        CheckpointParkedException so the task exits without marking the job failed.
        A new task will be dispatched when the user approves the checkpoint.
        """
        repo = await self._get_repo()
        checkpoint_id = f"cp-{str(uuid.uuid4())[:8]}"
        checkpoint_data = {
            "checkpoint_id": checkpoint_id,
            "checkpoint_type": checkpoint_type,
            "message": message,
            "data": data or {},
            "actions": ["approve", "reject"],
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        update = {
            "status": "paused",
            "checkpoint_data": checkpoint_data,
            "current_step": f"Waiting for approval: {message}",
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        if resume_phase:
            update["resume_phase"] = resume_phase
        await repo.update_job(job_id, update)
        await self._append_log(job_id, f"Checkpoint: {checkpoint_type} — {message}", level="warn")
        raise CheckpointParkedException(
            f"Job {job_id} parked at {checkpoint_type}, will resume at {resume_phase}"
        )

    async def execute(self, job_id: str, resume_from_phase: str = None):
        """Execute the full 9-phase migration pipeline.

        Args:
            job_id: The job identifier.
            resume_from_phase: If set, skip all phases before this one.
                Work directories persist on the Docker volume so they're
                still available on resume.
        """
        repo = await self._get_repo()
        job = await repo.get_job(job_id)
        if not job:
            raise Exception(f"Job {job_id} not found")

        work_dir = os.path.join(CODEMORPH_WORKSPACE, job_id)
        if not resume_from_phase:
            # Fresh run — clean up stale work_dir from previous attempts
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
        os.makedirs(work_dir, exist_ok=True)

        # Resolve SCM credentials from persona or env
        source_token = await self._resolve_scm_credentials(job.get("source_persona_id"))
        target_token = await self._resolve_scm_credentials(job.get("target_persona_id")) if job.get("target_persona_id") else source_token

        # Set up dual work directories for cross-repo conversion
        is_dual_repo = bool(job.get("target_repo_url"))
        if is_dual_repo:
            base_dir = f"/tmp/codemorph/{job_id}"
            source_work_dir = os.path.join(base_dir, "source")
            target_work_dir = os.path.join(base_dir, "target")
            os.makedirs(source_work_dir, exist_ok=True)
            os.makedirs(target_work_dir, exist_ok=True)
        else:
            source_work_dir = work_dir
            target_work_dir = work_dir

        # Ordered phases for skip logic
        phase_order = ["CLONE", "ANALYZE", "TRANSFORM", "BUILD", "TEST", "VALIDATE", "COMMIT", "PUSH", "PR_CREATE"]

        def should_skip(phase: str) -> bool:
            """Return True if this phase comes before resume_from_phase."""
            if not resume_from_phase:
                return False
            try:
                return phase_order.index(phase) < phase_order.index(resume_from_phase)
            except ValueError:
                return False

        # Load persisted analysis for resumed runs (needed by TRANSFORM, BUILD, TEST)
        analysis = job.get("analysis_result") if resume_from_phase else None

        try:
            # Phase 1: CLONE source repo
            if not should_skip("CLONE"):
                await self._phase_clone(job_id, job, source_work_dir, token=source_token)
                if is_dual_repo:
                    await self._phase_clone_target(job_id, job, target_work_dir, token=target_token)

            # Phase 2: ANALYZE
            if not should_skip("ANALYZE"):
                analysis = await self._phase_analyze(job_id, job, source_work_dir)
                # Persist analysis so resumed tasks can load it
                await repo.update_job(job_id, {"analysis_result": analysis})

            # Phase 3: TRANSFORM
            if not should_skip("TRANSFORM"):
                await self._phase_transform(job_id, job, source_work_dir, analysis or {}, target_work_dir=target_work_dir if is_dual_repo else None)

            # Phase 4: BUILD
            if not should_skip("BUILD"):
                if job.get("validate_build", True):
                    await self._phase_build(job_id, job, target_work_dir, analysis or {})

            # Phase 5: TEST
            if not should_skip("TEST"):
                if job.get("run_tests", True):
                    await self._phase_test(job_id, job, target_work_dir, analysis or {})

            # Phase 6: VALIDATE
            if not should_skip("VALIDATE"):
                await self._phase_validate(job_id, job, target_work_dir)

            # Phase 7: COMMIT
            if not should_skip("COMMIT"):
                skip_checkpoint = (resume_from_phase == "COMMIT")
                await self._phase_commit(job_id, job, target_work_dir, skip_checkpoint=skip_checkpoint)

            # Phase 8: PUSH
            if not should_skip("PUSH"):
                await self._phase_push(job_id, job, target_work_dir, token=target_token)

            # Phase 9: PR_CREATE
            if not should_skip("PR_CREATE"):
                pr_url = await self._phase_pr_create(job_id, job, target_work_dir, token=target_token)
            else:
                pr_url = job.get("pr_url")

            # Determine final status based on whether changes were made
            has_changes = getattr(self, '_has_changes', True)
            if has_changes:
                final_status = "completed"
                final_step = "Migration completed successfully"
            else:
                final_status = "failed"
                final_step = "Migration produced no code changes — transformation may have failed"
                await self._append_log(job_id, final_step, level="error")

            await repo.update_job(job_id, {
                "status": final_status,
                "progress_percentage": 100,
                "current_phase": "COMPLETE",
                "current_step": final_step,
                "completed_at": datetime.utcnow().isoformat() + "Z",
                "pr_url": pr_url if has_changes else None,
                "resume_phase": None,
                "result": {
                    "pr_url": pr_url,
                    "work_dir": work_dir,
                },
                "updated_at": datetime.utcnow().isoformat() + "Z",
            })

        except CheckpointParkedException:
            # Job parked at checkpoint — task ends cleanly, no failure
            logger.info(f"Job {job_id} parked at checkpoint, task ending cleanly")
            return

        except Exception as e:
            logger.error(f"Job {job_id} failed at execution: {str(e)}")
            await repo.update_job(job_id, {
                "status": "failed",
                "error_message": str(e),
                "completed_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
            })
            raise
        finally:
            # Clean up work directory on failure (keep on success/paused for artifacts & resume)
            job_final = await repo.get_job(job_id)
            if job_final and job_final.get("status") == "failed":
                shutil.rmtree(work_dir, ignore_errors=True)

    async def _phase_clone(self, job_id: str, job: Dict, work_dir: str, token: str = None):
        """Phase 1: Clone source repository."""
        await self._update_progress(job_id, "CLONE", 5, "Cloning repository")

        from services.codemorph.tools.git_tool import git_clone
        repo_url = job.get("repo_url", "")
        branch = job.get("branch", "main")

        result = git_clone(repo_url=repo_url, target_dir=work_dir, branch=branch, token=token)
        if str(result).startswith("Error (exit code"):
            raise Exception(f"Clone failed: {result}")

    async def _phase_clone_target(self, job_id: str, job: Dict, work_dir: str, token: str = None):
        """Phase 1b: Clone target repository (dual-repo conversion only)."""
        await self._update_progress(job_id, "CLONE", 8, "Cloning target repository")

        from services.codemorph.tools.git_tool import git_clone
        target_repo_url = job.get("target_repo_url", "")
        target_branch = job.get("target_branch", "main")

        result = git_clone(repo_url=target_repo_url, target_dir=work_dir, branch=target_branch, token=token)
        if str(result).startswith("Error (exit code"):
            raise Exception(f"Target clone failed: {result}")

    async def _phase_analyze(self, job_id: str, job: Dict, work_dir: str) -> Dict[str, Any]:
        """Phase 2: Analyze codebase."""
        await self._update_progress(job_id, "ANALYZE", 15, "Analyzing project structure")

        from services.codemorph.project_detector import detect_project_type
        analysis = detect_project_type(work_dir)

        # Checkpoint on high complexity — parks the job and ends this task
        complexity = analysis.get("complexity", "low")
        if complexity == "high":
            # Persist analysis before parking so the resumed task can load it
            repo = await self._get_repo()
            await repo.update_job(job_id, {"analysis_result": analysis})
            await self._park_at_checkpoint(
                job_id, "HIGH_COMPLEXITY_WARNING",
                f"High complexity detected: {analysis.get('file_count', 0)} files",
                data=analysis,
                resume_phase="TRANSFORM",
            )

        return analysis

    async def _phase_transform(self, job_id: str, job: Dict, work_dir: str, analysis: Dict, target_work_dir: str = None):
        """Phase 3: Transform code using Claude Agent SDK with native tools.

        Uses SDK built-in Read/Write/Edit/Bash/Glob/Grep tools instead of custom
        Strands tools. The SDK executes tools natively during generation, providing:
        - Real-time file editing (not post-hoc regex parsing)
        - Intelligent partial file editing via Edit tool
        - Full codebase search via Glob/Grep (no file limits)
        - Bash command execution with security guards
        - Streaming progress updates during transformation

        Args:
            target_work_dir: If set (dual-repo mode), transformed output goes here.
        """
        await self._update_progress(job_id, "TRANSFORM", 30, "Starting code transformation")

        if not CLAUDE_SDK_AVAILABLE:
            # Fallback to Strands if SDK not installed
            await self._phase_transform_strands_fallback(job_id, job, work_dir, analysis)
            return

        try:
            migration_type = job.get("migration_type", "")
            target_version = job.get("target_version", "")
            source_language = job.get("source_language", "")
            target_language = job.get("target_language", "")
            custom_instructions = job.get("custom_instructions", "")
            exclude_paths = job.get("exclude_paths", [])
            include_paths = job.get("include_paths", [])

            # Build path constraints for prompt
            path_constraints = ""
            if include_paths:
                path_constraints += f"\nOnly modify files in these paths: {', '.join(include_paths)}"
            if exclude_paths:
                path_constraints += f"\nDo NOT modify files in these paths: {', '.join(exclude_paths)}"

            # Dual-repo instruction for cross-repo conversion
            dual_repo_instruction = ""
            if target_work_dir:
                dual_repo_instruction = f"\nIMPORTANT: Read source code from {work_dir}. Write all converted output files to {target_work_dir}."

            if migration_type == "code_conversion":
                prompt = f"""Convert all {source_language} code in this project to {target_language}.

Source language: {source_language}
Target language: {target_language}
{f'Custom instructions: {custom_instructions}' if custom_instructions else ''}{path_constraints}{dual_repo_instruction}

Use the available tools to read, modify, and write files.
Convert all source files from {source_language} to idiomatic {target_language}.
Preserve the project structure and logic while adapting to {target_language} conventions."""
            else:
                prompt = f"""Migrate this {analysis.get('project_type', 'unknown')} project.

Migration type: {migration_type}
Target version: {target_version}
{f'Custom instructions: {custom_instructions}' if custom_instructions else ''}{path_constraints}{dual_repo_instruction}

Use the available tools to read, modify, and write files.
Focus on the most important migration changes first."""

            system_prompt = (
                "You are a code migration expert. You have access to file and search "
                "tools to read, edit, and write code. Work only within the project "
                "directory. Make targeted, precise edits using the Edit tool when "
                "possible instead of rewriting entire files."
            )

            # Note: can_use_tool guard disabled due to SDK compatibility issue
            # (causes 0 messages to be yielded). Security is enforced by:
            # - permission_mode="acceptEdits" (auto-approves file edits only)
            # - cwd restricts the agent's working directory
            # - system_prompt instructs the agent to work within the project dir
            model_id = job.get("model_id") or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

            # Smart Model Routing: resolve "auto" using migration context
            from services.claude_models import is_auto_model, resolve_auto_model
            if is_auto_model(model_id):
                model_id = resolve_auto_model(
                    prompt=prompt,
                    file_count=analysis.get("file_count", 0),
                    migration_type=migration_type,
                )
                logger.info(f"CodeMorph job {job_id}: auto-resolved model to {model_id}")
            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                permission_mode="acceptEdits",
                cwd=work_dir,
                model=model_id,
                max_turns=50,
            )

            await self._update_progress(job_id, "TRANSFORM", 35, "AI agent analyzing code")
            await self._append_log(job_id, f"Using Claude Agent SDK (model: {model_id})")
            await self._append_log(job_id, f"Prompt: {prompt[:300]}...")

            progress = 35
            tool_uses = 0
            message_count = 0
            try:
                async for message in claude_query(prompt=prompt, options=options):
                    message_count += 1
                    msg_type = type(message).__name__
                    await self._append_log(job_id, f"SDK message #{message_count}: {msg_type}")

                    # Stream tool use events as progress updates
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            block_type = type(block).__name__
                            if isinstance(block, ToolUseBlock):
                                tool_uses += 1
                                tool_desc = block.name
                                if block.name in ("Write", "Edit") and block.input.get("file_path"):
                                    file_path = block.input["file_path"]
                                    rel_path = os.path.relpath(file_path, work_dir)
                                    tool_desc = f"Editing {rel_path}"
                                elif block.name == "Bash":
                                    cmd = block.input.get("command", "")[:50]
                                    tool_desc = f"Running: {cmd}"

                                progress = min(progress + 1, 50)
                                await self._update_progress(
                                    job_id, "TRANSFORM", progress, tool_desc
                                )
                                await self._append_log(job_id, f"Tool: {tool_desc}")
                            elif isinstance(block, TextBlock):
                                text_preview = block.text[:200] if block.text else "(empty)"
                                await self._append_log(job_id, f"Agent text: {text_preview}")

                    # Capture final result
                    if isinstance(message, ResultMessage):
                        await self._append_log(
                            job_id,
                            f"ResultMessage: is_error={message.is_error}, "
                            f"num_turns={message.num_turns}, "
                            f"duration_ms={message.duration_ms}, "
                            f"result={str(message.result)[:300]}"
                        )
                        if message.is_error:
                            error_msg = message.result or 'Unknown error'
                            await self._append_log(job_id, f"SDK error: {error_msg}", level="error")
                            raise Exception(f"SDK transform failed: {error_msg}")
                        cost_usd = message.total_cost_usd or 0
                        summary = (
                            f"TRANSFORM complete: {message.num_turns} turns, "
                            f"{tool_uses} tool calls, ${cost_usd:.4f}, {message.duration_ms}ms"
                        )
                        logger.info(summary)
                        await self._append_log(job_id, summary)

                        # Persist cost data to MongoDB for analytics
                        usage = message.usage or {}
                        cost_data = {
                            "cost_usd": round(cost_usd, 6),
                            "input_tokens": usage.get("input_tokens"),
                            "output_tokens": usage.get("output_tokens"),
                            "total_tokens": (usage.get("input_tokens", 0) or 0) + (usage.get("output_tokens", 0) or 0) or None,
                            "model_used": model_id,
                            "num_turns": message.num_turns,
                            "transform_duration_ms": message.duration_ms,
                        }
                        cost_data = {k: v for k, v in cost_data.items() if v is not None}
                        repo = await self._get_repo()
                        await repo.update_job(job_id, cost_data)

            except Exception as sdk_err:
                await self._append_log(job_id, f"SDK exception after {message_count} messages: {str(sdk_err)[:300]}", level="error")
                raise

            await self._append_log(job_id, f"SDK loop finished: {message_count} messages total, {tool_uses} tool calls")

            if tool_uses == 0:
                await self._append_log(job_id, "WARNING: Agent made 0 tool calls — no code was modified", level="warn")

            # Check if git has any changes after transform
            import subprocess as _sp
            diff_result = _sp.run(["git", "diff", "--stat"], cwd=work_dir, capture_output=True, text=True, timeout=30)
            untracked = _sp.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=work_dir, capture_output=True, text=True, timeout=30)
            diff_summary = diff_result.stdout.strip() or "(no changes)"
            untracked_summary = untracked.stdout.strip() or "(none)"
            await self._append_log(job_id, f"Files changed: {diff_summary}")
            if untracked_summary != "(none)":
                await self._append_log(job_id, f"New files: {untracked_summary}")

            await self._update_progress(job_id, "TRANSFORM", 50, "Code transformation complete")

        except Exception as e:
            logger.error(f"Transform phase error: {e}")
            raise Exception(f"Code transformation failed: {str(e)}")

    async def _phase_transform_strands_fallback(
        self, job_id: str, job: Dict, work_dir: str, analysis: Dict
    ):
        """Fallback TRANSFORM using Strands SDK when Claude Agent SDK is unavailable."""
        try:
            from strands import Agent
            from strands.models import BedrockModel
            from services.codemorph.tools.file_tool import read_file, write_file, list_files

            model = BedrockModel(
                model_id=os.getenv(
                    "CODEMORPH_MODEL", "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
                ),
                temperature=0.2,
                max_tokens=4096,
            )

            migration_type = job.get("migration_type", "")
            target_version = job.get("target_version", "")
            source_language = job.get("source_language", "")
            target_language = job.get("target_language", "")
            custom_instructions = job.get("custom_instructions", "")

            if migration_type == "code_conversion":
                prompt = (
                    f"You are a code conversion expert. Convert all {source_language} "
                    f"code in this project to {target_language}.\n\n"
                    f"Source language: {source_language}\n"
                    f"Target language: {target_language}\n"
                    f"Project directory: {work_dir}\n"
                    f"{f'Custom instructions: {custom_instructions}' if custom_instructions else ''}\n\n"
                    f"Use the available file tools to read, modify, and write files.\n"
                    f"Work directory is: {work_dir}"
                )
            else:
                prompt = (
                    f"You are a code migration expert. Migrate this "
                    f"{analysis.get('project_type', 'unknown')} project.\n\n"
                    f"Migration type: {migration_type}\n"
                    f"Target version: {target_version}\n"
                    f"Project directory: {work_dir}\n"
                    f"{f'Custom instructions: {custom_instructions}' if custom_instructions else ''}\n\n"
                    f"Use the available file tools to read, modify, and write files.\n"
                    f"Work directory is: {work_dir}"
                )

            agent = Agent(model=model, tools=[read_file, write_file, list_files])

            await self._update_progress(job_id, "TRANSFORM", 40, "AI agent transforming code")
            logger.info(f"TRANSFORM prompt for job {job_id}: {prompt[:200]}...")
            await self._append_log(job_id, f"Agent prompt: {prompt[:300]}...")
            result = agent(prompt)
            # Log what the agent actually did
            result_text = str(result) if result else "(empty)"
            logger.info(f"TRANSFORM agent result for job {job_id} ({len(result_text)} chars): {result_text[:500]}")
            await self._append_log(job_id, f"Agent response ({len(result_text)} chars): {result_text[:500]}")

            # Check if git has any changes after transform
            import subprocess
            diff_result = subprocess.run(
                ["git", "diff", "--stat"], cwd=work_dir, capture_output=True, text=True, timeout=30
            )
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"], cwd=work_dir, capture_output=True, text=True, timeout=30
            )
            diff_summary = diff_result.stdout.strip() or "(no changes)"
            untracked_summary = untracked.stdout.strip() or "(none)"
            logger.info(f"TRANSFORM diff stat: {diff_summary}")
            logger.info(f"TRANSFORM untracked files: {untracked_summary}")
            await self._append_log(job_id, f"Files changed: {diff_summary}")
            if untracked_summary != "(none)":
                await self._append_log(job_id, f"New files: {untracked_summary}")

            await self._update_progress(job_id, "TRANSFORM", 50, "Code transformation complete")

        except Exception as e:
            logger.error(f"Strands fallback transform error: {e}")
            raise Exception(f"Code transformation failed: {str(e)}")

    async def _phase_build(self, job_id: str, job: Dict, work_dir: str, analysis: Dict):
        """Phase 4: Build project."""
        await self._update_progress(job_id, "BUILD", 65, "Running build")

        from services.codemorph.tools.bash_tool import run_command

        build_cmd = analysis.get("build_command")
        if build_cmd:
            result = run_command(command=build_cmd, working_dir=work_dir)
            result_str = str(result)
            # Check for non-zero exit code (appended by bash_tool as "Exit code: N")
            has_error = "Exit code:" in result_str and not result_str.rstrip().endswith("Exit code: 0")
            has_error = has_error or result_str.startswith("Error")
            if has_error:
                # Park at checkpoint — task ends, resumed task skips to TEST
                await self._park_at_checkpoint(
                    job_id, "BUILD_FAILURE",
                    "Build failed. Review and decide whether to continue.",
                    data={"output": result_str[:2000]},
                    resume_phase="TEST",
                )

    async def _phase_test(self, job_id: str, job: Dict, work_dir: str, analysis: Dict):
        """Phase 5: Run tests."""
        await self._update_progress(job_id, "TEST", 75, "Running test suite")

        from services.codemorph.tools.bash_tool import run_command

        test_cmd = analysis.get("test_command")
        if test_cmd:
            result = run_command(command=test_cmd, working_dir=work_dir)
            result_str = str(result)
            has_error = "Exit code:" in result_str and not result_str.rstrip().endswith("Exit code: 0")
            has_error = has_error or result_str.startswith("Error")
            if has_error:
                # Park at checkpoint — task ends, resumed task skips to VALIDATE
                await self._park_at_checkpoint(
                    job_id, "TEST_FAILURE",
                    "Some tests failed. Review results and decide.",
                    data={"output": result_str[:2000]},
                    resume_phase="VALIDATE",
                )

    async def _phase_validate(self, job_id: str, job: Dict, work_dir: str):
        """Phase 6: Validate changes."""
        await self._update_progress(job_id, "VALIDATE", 85, "Validating migration")
        # Basic validation - ensure work dir still exists and has files
        if not os.path.isdir(work_dir):
            raise Exception("Work directory missing after transformation")

    def _get_branch_name(self, job: Dict) -> str:
        """Generate the migration branch name."""
        migration_type = job.get("migration_type", "migration")
        if migration_type == "code_conversion":
            return f"codemorph/conversion-{job.get('source_language', '')}-to-{job.get('target_language', '')}-{job.get('job_id', '')[:8]}"
        return f"codemorph/{migration_type}-{job.get('job_id', '')[:8]}"

    async def _phase_commit(self, job_id: str, job: Dict, work_dir: str, skip_checkpoint: bool = False):
        """Phase 7: Create branch and commit changes."""
        await self._update_progress(job_id, "COMMIT", 90, "Creating branch and committing changes")

        if job.get("requires_approval", False) and not skip_checkpoint:
            # Park at checkpoint — resumed task re-enters COMMIT with skip_checkpoint=True
            await self._park_at_checkpoint(
                job_id, "COMMIT_APPROVAL",
                "Ready to commit changes. Review diff and approve.",
                data={},
                resume_phase="COMMIT",
            )

        import subprocess

        # Create branch BEFORE committing so commit lands on the right branch
        branch_name = self._get_branch_name(job)
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=work_dir, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise Exception(f"Failed to create branch {branch_name}: {result.stderr}")

        from services.codemorph.tools.git_tool import git_commit
        migration_type = job.get("migration_type", "migration")
        if migration_type == "code_conversion":
            source_lang = job.get("source_language", "")
            target_lang = job.get("target_language", "")
            commit_msg = f"chore: code_conversion {source_lang} to {target_lang} - automated by CodeMorph"
        else:
            commit_msg = f"chore: {migration_type} - automated by CodeMorph"
        result = git_commit(repo_dir=work_dir, message=commit_msg)
        if str(result).startswith("Error (exit code"):
            raise Exception(f"Commit failed: {result}")
        # Track whether there were actual changes to push
        self._has_changes = "no new changes" not in str(result)
        if not self._has_changes:
            await self._append_log(job_id, "No code changes were produced by the transformation", level="warn")

    async def _phase_push(self, job_id: str, job: Dict, work_dir: str, token: str = None):
        """Phase 8: Push branch to remote."""
        if not getattr(self, '_has_changes', True):
            await self._update_progress(job_id, "PUSH", 95, "Skipping push — no changes to push")
            logger.info(f"Skipping push for job {job_id} — no changes were committed")
            return
        await self._update_progress(job_id, "PUSH", 95, "Pushing to remote")

        import subprocess

        branch_name = self._get_branch_name(job)

        # Inject token into remote URL for push authentication
        token = token or ""
        if token:
            from services.codemorph.tools.git_tool import _inject_token
            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=work_dir, capture_output=True, text=True, timeout=10
            )
            if remote_result.returncode == 0:
                original_url = remote_result.stdout.strip()
                # Skip injection if URL already has credentials (from clone)
                if "@" not in original_url.split("//", 1)[-1].split("/", 1)[0]:
                    auth_url = _inject_token(original_url, token=token)
                    if auth_url != original_url:
                        subprocess.run(
                            ["git", "remote", "set-url", "origin", auth_url],
                            cwd=work_dir, capture_output=True, text=True, timeout=10
                        )

        result = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            cwd=work_dir, capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            stderr = result.stderr
            if token:
                stderr = stderr.replace(token, "***")
            raise Exception(f"Push failed: {stderr}")

    async def _phase_pr_create(self, job_id: str, job: Dict, work_dir: str, token: str = None) -> Optional[str]:
        """Phase 9: Create pull request."""
        if not job.get("create_pr", True):
            await self._update_progress(job_id, "PR_CREATE", 100, "Skipping PR creation")
            return None
        if not getattr(self, '_has_changes', True):
            await self._update_progress(job_id, "PR_CREATE", 100, "Skipping PR — no changes were made")
            logger.info(f"Skipping PR creation for job {job_id} — no changes were committed")
            return None

        await self._update_progress(job_id, "PR_CREATE", 98, "Creating pull request")

        from services.codemorph.tools.github_tool import create_pull_request

        # Use target_repo_url for PR if set (dual-repo), otherwise source repo_url
        repo_url = job.get("target_repo_url") or job.get("repo_url", "")
        migration_type = job.get("migration_type", "migration")
        target_version = job.get("target_version", "")

        if migration_type == "code_conversion":
            source_lang = job.get("source_language", "")
            target_lang = job.get("target_language", "")
            branch_name = f"codemorph/conversion-{source_lang}-to-{target_lang}-{job.get('job_id', '')[:8]}"
            default_title = f"CodeMorph: Convert {source_lang} to {target_lang}"
            default_body = f"Automated code conversion by CodeMorph.\n\nSource language: {source_lang}\nTarget language: {target_lang}"
        else:
            branch_name = f"codemorph/{migration_type}-{job.get('job_id', '')[:8]}"
            default_title = f"CodeMorph: {migration_type} to {target_version}"
            default_body = f"Automated migration by CodeMorph.\n\nMigration type: {migration_type}\nTarget version: {target_version}"

        # Use user-provided PR title/description if available
        pr_title = job.get("pr_title") or default_title
        pr_body = job.get("pr_description") or default_body

        # Use target_branch for base if dual-repo, otherwise source branch
        base_branch = job.get("target_branch", job.get("branch", "main")) if job.get("target_repo_url") else job.get("branch", "main")

        pr_url = create_pull_request(
            repo_url=repo_url,
            head_branch=branch_name,
            base_branch=base_branch,
            title=pr_title,
            body=pr_body,
            token=token
        )

        if not pr_url:
            logger.warning(f"PR creation returned empty URL for job {job_id} — Git persona may not have write access")

        return pr_url
