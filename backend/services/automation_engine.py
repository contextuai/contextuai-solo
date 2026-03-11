"""
Automation Engine Service
High-level orchestrator for executing complete automation workflows.
Uses Claude Agent SDK for intelligent AI-based prompt parsing (replacing regex),
and coordinates step execution with conditional logic support.
"""

import os
import uuid
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import time

from services.automation_executor import automation_executor
from services.automation_output_service import automation_output_service
from models.automation_models import (
    ExecutionStatus,
    ExecutionStep,
    AutomationExecutionResponse
)
from database import get_database
from repositories import AutomationRepository, AutomationExecutionRepository

# Claude Agent SDK imports for AI-based prompt parsing
try:
    from claude_agent_sdk import (
        query as claude_query,
        ClaudeAgentOptions,
        ResultMessage,
    )
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)

# Environment configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


class AutomationEngine:
    """
    Main orchestrator for automation execution.
    Handles prompt parsing, step coordination, and result aggregation.
    """

    def __init__(self):
        """Initialize the AutomationEngine."""
        self._automation_repo: Optional[AutomationRepository] = None
        self._execution_repo: Optional[AutomationExecutionRepository] = None

    async def _get_automation_repo(self) -> AutomationRepository:
        """Get or create the AutomationRepository instance."""
        if self._automation_repo is None:
            db = await get_database()
            self._automation_repo = AutomationRepository(db)
        return self._automation_repo

    async def _get_execution_repo(self) -> AutomationExecutionRepository:
        """Get or create the AutomationExecutionRepository instance."""
        if self._execution_repo is None:
            db = await get_database()
            self._execution_repo = AutomationExecutionRepository(db)
        return self._execution_repo

    async def execute_automation(
        self,
        automation_id: str,
        user_id: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> AutomationExecutionResponse:
        """
        Execute a complete automation workflow.

        Args:
            automation_id: ID of automation to execute
            user_id: User executing the automation
            parameters: Optional parameters for execution

        Returns:
            Complete execution response with all step results

        Raises:
            Exception: If automation not found or execution fails critically
        """
        execution_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat() + "Z"
        start_time = time.time()

        print(f"\n{'='*60}")
        print(f"🚀 AUTOMATION EXECUTION STARTED")
        print(f"{'='*60}")
        print(f"Execution ID: {execution_id}")
        print(f"Automation ID: {automation_id}")
        print(f"User ID: {user_id}")
        print(f"Started At: {started_at}")
        print(f"{'='*60}\n")

        try:
            # Step 1: Load automation from MongoDB
            automation = await self._load_automation(automation_id)
            print(f"📋 Loaded Automation: {automation['name']}")
            print(f"   Prompt: {automation['prompt_template'][:100]}...")

            # Step 2: Parse prompt into executable steps using AI
            steps_plan = await self._parse_prompt_with_ai(
                automation['prompt_template'],
                automation.get('personas_detected', [])
            )
            print(f"\n🧠 AI Parsed into {len(steps_plan)} steps:")
            for i, step in enumerate(steps_plan, 1):
                print(f"   {i}. @{step['persona']}: {step['instruction']}")

            # Step 3: Execute steps based on execution mode
            executed_steps = []
            context = ""
            failed = False

            # Detect execution mode from prompt
            from services.prompt_parser import prompt_parser
            parse_result = prompt_parser.parse(automation['prompt_template'])
            execution_mode = parse_result.get("execution_mode", "sequential")

            if execution_mode == "parallel" and len(steps_plan) > 1:
                # Parallel execution via Celery group (non-blocking)
                print(f"\n⚡ Executing {len(steps_plan)} steps in PARALLEL")
                try:
                    from celery import group
                    from tasks.automation_tasks import execute_automation_step
                    import asyncio

                    step_tasks = group(
                        execute_automation_step.s(
                            step_plan,
                            context,
                            user_id,
                            automation.get('model_id')
                        )
                        for step_plan in steps_plan
                    )

                    results = step_tasks.apply_async()
                    # Use asyncio.to_thread to avoid blocking the event loop
                    step_results = await asyncio.to_thread(results.get, timeout=300)

                    executed_steps = list(step_results) if step_results else []
                except Exception as e:
                    print(f"⚠️  Parallel execution failed, falling back to sequential: {e}")
                    # Fall back to sequential
                    execution_mode = "sequential"

            if execution_mode != "parallel" or not executed_steps:
                # Sequential execution (default)
                for step_plan in steps_plan:
                    if failed:
                        print(f"\n⏭️  Skipping remaining steps due to previous failure")
                        break

                    # Evaluate condition if present
                    condition = step_plan.get('condition')
                    if condition:
                        should_run = await self._evaluate_condition(condition, context, executed_steps)
                        if not should_run:
                            print(f"   ⏭️  Skipping step {step_plan['step_number']} (condition not met: {condition})")
                            executed_steps.append({
                                "step_number": step_plan['step_number'],
                                "persona": step_plan['persona'],
                                "instruction": step_plan['instruction'],
                                "status": "skipped",
                                "result": f"Condition not met: {condition}",
                                "error": None,
                            })
                            continue

                    step_result = await automation_executor.execute_step(
                        step_number=step_plan['step_number'],
                        persona=step_plan['persona'],
                        instruction=step_plan['instruction'],
                        context=context,
                        user_id=user_id,
                        model_id=automation.get('model_id')
                    )

                    executed_steps.append(step_result)

                    if step_result['status'] == 'failed':
                        failed = True
                    else:
                        context = automation_executor.build_context_from_steps(executed_steps)

            # Step 4: Determine overall status
            successful_steps = sum(1 for s in executed_steps if s['status'] == 'success')
            failed_steps = sum(1 for s in executed_steps if s['status'] == 'failed')

            if failed_steps == 0:
                overall_status = ExecutionStatus.SUCCESS
            elif successful_steps == 0:
                overall_status = ExecutionStatus.FAILED
            else:
                overall_status = ExecutionStatus.PARTIAL

            # Step 5: Aggregate final result
            final_result = automation_executor.aggregate_results(executed_steps)

            # Step 6: Calculate execution metrics
            completed_at = datetime.utcnow().isoformat() + "Z"
            duration_ms = int((time.time() - start_time) * 1000)

            # Step 7: Create execution response
            execution_response = AutomationExecutionResponse(
                execution_id=execution_id,
                automation_id=automation_id,
                user_id=user_id,
                status=overall_status,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                steps=[ExecutionStep(**step) for step in executed_steps],
                final_result=final_result,
                error_message=self._get_first_error(executed_steps),
                total_steps=len(executed_steps),
                successful_steps=successful_steps,
                failed_steps=failed_steps
            )

            # Step 8: Store execution history
            await self._store_execution(execution_response)

            # Step 9: Update automation's last_run
            await self._update_automation_last_run(
                automation_id,
                completed_at,
                overall_status.value
            )

            # Step 10: Process output actions
            output_actions = automation.get('output_actions', [])
            if output_actions and overall_status != ExecutionStatus.FAILED:
                print(f"\n📤 Processing {len(output_actions)} output action(s)...")
                try:
                    output_results = await automation_output_service.process_output_actions(
                        execution_response, output_actions, user_id
                    )
                    # Update execution document with output results
                    await self._update_execution_outputs(execution_id, output_results)
                    execution_response.output_results = output_results

                    succeeded = sum(1 for r in output_results if r.get('status') == 'success')
                    print(f"   ✅ {succeeded}/{len(output_results)} output actions completed")
                except Exception as e:
                    print(f"   ⚠️  Output actions processing error: {e}")

            print(f"\n{'='*60}")
            print(f"✅ AUTOMATION EXECUTION COMPLETED")
            print(f"{'='*60}")
            print(f"Status: {overall_status.value}")
            print(f"Duration: {duration_ms}ms")
            print(f"Steps: {successful_steps}/{len(executed_steps)} successful")
            print(f"{'='*60}\n")

            return execution_response

        except Exception as e:
            # Handle critical failures
            error_message = str(e)
            completed_at = datetime.utcnow().isoformat() + "Z"
            duration_ms = int((time.time() - start_time) * 1000)

            print(f"\n{'='*60}")
            print(f"❌ AUTOMATION EXECUTION FAILED")
            print(f"{'='*60}")
            print(f"Error: {error_message}")
            print(f"Duration: {duration_ms}ms")
            print(f"{'='*60}\n")

            # Create failed execution response
            execution_response = AutomationExecutionResponse(
                execution_id=execution_id,
                automation_id=automation_id,
                user_id=user_id,
                status=ExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                steps=[],
                final_result="",
                error_message=error_message,
                total_steps=0,
                successful_steps=0,
                failed_steps=0
            )

            # Store failed execution
            try:
                await self._store_execution(execution_response)
            except Exception:
                pass  # Don't fail if we can't store

            raise Exception(f"Automation execution failed: {error_message}")

    async def _load_automation(self, automation_id: str) -> Dict[str, Any]:
        """Load automation from MongoDB"""
        automation_repo = await self._get_automation_repo()
        automation = await automation_repo.get_by_id(automation_id)

        if automation is None:
            raise Exception(f"Automation '{automation_id}' not found")

        return automation

    async def _parse_prompt_with_ai(
        self,
        prompt: str,
        detected_personas: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Use AI to intelligently parse prompt into executable steps.

        Primary: Claude Agent SDK query() for true AI-based parsing that handles
        complex prompts with nested conditions, parallel/sequential detection,
        and data dependency extraction.

        Fallback: Regex keyword-based parsing when SDK is unavailable.

        Args:
            prompt: The automation prompt template
            detected_personas: List of personas detected in prompt

        Returns:
            List of step plans with step_number, persona, instruction,
            and optionally depends_on and condition fields.
        """
        if CLAUDE_SDK_AVAILABLE:
            try:
                return await self._parse_prompt_with_sdk(prompt, detected_personas)
            except Exception as e:
                logger.warning(f"SDK parsing failed, falling back to regex: {e}")
                return self._parse_prompt_with_regex(prompt, detected_personas)
        else:
            return self._parse_prompt_with_regex(prompt, detected_personas)

    async def _parse_prompt_with_sdk(
        self,
        prompt: str,
        detected_personas: List[str]
    ) -> List[Dict[str, Any]]:
        """Parse automation prompt using Claude Agent SDK for structured AI parsing."""
        parse_prompt = f"""Parse this automation prompt into structured execution steps.

Prompt: {prompt}
Available personas: {', '.join(detected_personas) if detected_personas else 'None detected'}

Return ONLY a valid JSON array of steps. Each step must have:
- "step_number" (int): Sequential step number starting from 1
- "persona" (string): Must match one of the available personas
- "instruction" (string): The specific action for this persona to perform
- "depends_on" (list of ints, optional): Step numbers this step needs completed first
- "condition" (string, optional): When this step should execute (e.g., "if previous step found errors")

Rules:
- Each @persona mention maps to exactly one step
- Detect whether steps should run sequentially or can run in parallel
- Extract data flow dependencies between steps
- If conditional logic is present (if/when/unless), include the condition
- The instruction should NOT include the @persona mention
- If only one persona is mentioned, create a single step with the full instruction

Return ONLY the JSON array, no explanation."""

        # Resolve model (Smart Model Routing)
        parse_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        from services.claude_models import is_auto_model, resolve_auto_model
        if is_auto_model(parse_model):
            parse_model = resolve_auto_model(prompt=prompt)

        options = ClaudeAgentOptions(
            system_prompt="You are a workflow parser. Output ONLY valid JSON arrays. No markdown, no explanation.",
            allowed_tools=[],
            model=parse_model,
            max_turns=1,
        )

        result_text = ""
        async for message in claude_query(prompt=parse_prompt, options=options):
            if isinstance(message, ResultMessage):
                result_text = message.result or ""

        # Parse the JSON response
        result_text = result_text.strip()
        # Strip markdown code fences if present
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        steps = json.loads(result_text)

        if not isinstance(steps, list) or not steps:
            raise ValueError("SDK returned empty or invalid steps array")

        # Validate and normalize
        for step in steps:
            if "step_number" not in step or "persona" not in step or "instruction" not in step:
                raise ValueError(f"Step missing required fields: {step}")

        logger.info(f"SDK parsed {len(steps)} steps from prompt")
        return steps

    def _parse_prompt_with_regex(
        self,
        prompt: str,
        detected_personas: List[str]
    ) -> List[Dict[str, Any]]:
        """Fallback: Parse prompt using regex keyword splitting."""
        import re

        sequential_keywords = ["then", "next", "after", "afterwards", "followed by"]
        parts = re.split(
            r'\s+(then|next|after|afterwards|followed by)\s+',
            prompt, flags=re.IGNORECASE
        )

        steps = []
        step_number = 1
        for part in parts:
            part = part.strip()
            if part.lower() in sequential_keywords or not part:
                continue

            persona_match = re.search(r'@(\w+)', part)
            if persona_match:
                persona = persona_match.group(1)
                instruction = re.sub(r'@\w+\s*', '', part).strip()
                if instruction:
                    steps.append({
                        "step_number": step_number,
                        "persona": persona,
                        "instruction": instruction,
                    })
                    step_number += 1

        if not steps and detected_personas:
            persona = detected_personas[0]
            instruction = re.sub(r'@\w+\s*', '', prompt).strip()
            steps.append({
                "step_number": 1,
                "persona": persona,
                "instruction": instruction,
            })

        return steps

    async def _evaluate_condition(
        self,
        condition: str,
        context: str,
        executed_steps: List[Dict[str, Any]],
    ) -> bool:
        """Evaluate a step condition against execution context using AI.

        Args:
            condition: The condition string (e.g., "if previous step found errors")
            context: Accumulated context from previous steps
            executed_steps: Previously executed step results

        Returns:
            True if condition is met, False otherwise.
        """
        if not CLAUDE_SDK_AVAILABLE:
            return True  # Always execute if SDK unavailable

        try:
            eval_prompt = f"""Evaluate whether this condition is TRUE or FALSE based on the context.

Condition: {condition}

Previous step results:
{context[:2000] if context else 'No previous results'}

Respond with ONLY "TRUE" or "FALSE"."""

            # Resolve model (Smart Model Routing — condition eval is simple, prefer Haiku)
            eval_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
            from services.claude_models import is_auto_model, resolve_auto_model
            if is_auto_model(eval_model):
                eval_model = resolve_auto_model(prompt=condition)

            options = ClaudeAgentOptions(
                system_prompt="You evaluate conditions. Respond ONLY with TRUE or FALSE.",
                allowed_tools=[],
                model=eval_model,
                max_turns=1,
            )

            result_text = ""
            async for message in claude_query(prompt=eval_prompt, options=options):
                if isinstance(message, ResultMessage):
                    result_text = (message.result or "").strip().upper()

            return result_text == "TRUE"

        except Exception as e:
            logger.warning(f"Condition evaluation failed, defaulting to True: {e}")
            return True

    async def _store_execution(self, execution: AutomationExecutionResponse):
        """Store execution history in MongoDB"""
        execution_repo = await self._get_execution_repo()

        # Convert Pydantic model to dict
        execution_dict = execution.dict()

        # Convert ExecutionStep objects to dicts
        execution_dict['steps'] = [step.dict() if hasattr(step, 'dict') else step for step in execution_dict['steps']]

        # Convert status enum to string value
        execution_dict['status'] = execution.status.value

        # Map field names to match repository expectations
        execution_data = {
            "execution_id": execution_dict['execution_id'],
            "automation_id": execution_dict['automation_id'],
            "user_id": execution_dict['user_id'],
            "status": execution_dict['status'],
            "started_at": execution_dict['started_at'],
            "completed_at": execution_dict['completed_at'],
            "duration_ms": execution_dict['duration_ms'],
            "parameters": {},
            "steps": execution_dict['steps'],
            "result": execution_dict['final_result'],
            "error": execution_dict['error_message'],
            "total_steps": execution_dict['total_steps'],
            "successful_steps": execution_dict['successful_steps'],
            "failed_steps": execution_dict['failed_steps']
        }

        # Use base repository's create method to store the full execution document
        await execution_repo.create(execution_data)

        print(f"💾 Execution history saved to MongoDB")

    async def _update_automation_last_run(
        self,
        automation_id: str,
        last_run: str,
        status: str
    ):
        """Update automation's last_run timestamp and increment run_count"""
        try:
            automation_repo = await self._get_automation_repo()

            # Use the increment_run_count method which handles run_count and last_run
            result = await automation_repo.increment_run_count(automation_id)

            if result:
                # Also update the last_execution_status
                await automation_repo.update(automation_id, {
                    "last_execution_status": status
                })
                print(f"📊 Automation stats updated: run_count={result.get('run_count', 'N/A')}")
            else:
                print(f"⚠️  Warning: Automation not found when updating stats")

        except Exception as e:
            print(f"⚠️  Warning: Failed to update automation stats: {e}")
            # Don't fail execution if stats update fails

    async def _update_execution_outputs(
        self,
        execution_id: str,
        output_results: List[Dict[str, Any]]
    ):
        """Update execution document with output action results."""
        try:
            execution_repo = await self._get_execution_repo()
            await execution_repo.collection.update_one(
                {"execution_id": execution_id},
                {"$set": {"output_results": output_results}}
            )
            print(f"💾 Output results saved to execution document")
        except Exception as e:
            print(f"⚠️  Warning: Failed to save output results: {e}")

    def _get_first_error(self, steps: List[Dict[str, Any]]) -> Optional[str]:
        """Extract first error message from failed steps"""
        for step in steps:
            if step.get('status') == 'failed' and step.get('error'):
                return f"Step {step['step_number']}: {step['error']}"
        return None


# Singleton instance
automation_engine = AutomationEngine()
