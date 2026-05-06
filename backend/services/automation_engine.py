"""
Automation Engine — orchestrator for one automation run.

Solo variant: sequential-only execution, regex-based prompt parsing
(no Claude Agent SDK), and no Celery. The engine drives the executor
step-by-step, persists step traces into ``automation_executions`` as it
goes (so the SSE stream can tail progress), and finally fans out the
configured output actions.
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from database import get_database
from models.automation_models import (
    AutomationExecutionResponse,
    ExecutionStatus,
    ExecutionStep,
)
from repositories.automation_execution_repository import (
    AutomationExecutionRepository,
)
from repositories.automation_repository import AutomationRepository
from services.automation_executor import automation_executor
from services.automation_output_service import automation_output_service
from services.automation_parser import prompt_parser

logger = logging.getLogger(__name__)


class AutomationEngine:
    """Orchestrate the full lifecycle of one automation run."""

    async def execute_automation(
        self,
        automation_id: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AutomationExecutionResponse:
        db = await get_database()
        auto_repo = AutomationRepository(db)
        exec_repo = AutomationExecutionRepository(db)

        automation = await auto_repo.get_by_id(automation_id)
        if not automation:
            raise ValueError(f"Automation '{automation_id}' not found")

        # Create the execution row up front so the SSE stream can poll it.
        exec_row = await exec_repo.create_execution(
            automation_id=automation_id, parameters=parameters or {}
        )
        execution_id = exec_row["execution_id"]
        started_at = exec_row["started_at"]
        start = time.time()

        prompt = automation["prompt_template"]
        parsed = prompt_parser.parse(prompt)
        personas = parsed["personas"]
        steps_plan = prompt_parser.split_into_steps(prompt, personas)

        if not steps_plan:
            # Fallback: treat the whole prompt as a single step on the first
            # detected persona, or fail loudly if there isn't one.
            if personas:
                steps_plan = [
                    {
                        "step_number": 1,
                        "persona": personas[0],
                        "instruction": prompt,
                    }
                ]
            else:
                await exec_repo.update_execution(
                    execution_id,
                    status=ExecutionStatus.FAILED.value,
                    error="No @agents detected in the prompt.",
                )
                return self._failed_response(
                    execution_id=execution_id,
                    automation_id=automation_id,
                    started_at=started_at,
                    duration_ms=int((time.time() - start) * 1000),
                    error="No @agents detected in the prompt.",
                )

        executed: List[Dict[str, Any]] = []
        context = ""
        for plan in steps_plan:
            step = await automation_executor.execute_step(
                step_number=plan["step_number"],
                persona=plan["persona"],
                instruction=plan["instruction"],
                context=context,
                model_id=automation.get("model_id"),
            )
            executed.append(step)
            await exec_repo.append_step(execution_id, step)

            if step["status"] == "failed":
                # Stop on first failure (sequential semantics).
                break
            context = automation_executor.build_context_from_steps(executed)

        successful = sum(1 for s in executed if s["status"] == "success")
        failed = sum(1 for s in executed if s["status"] == "failed")
        if failed == 0:
            status = ExecutionStatus.SUCCESS
        elif successful == 0:
            status = ExecutionStatus.FAILED
        else:
            status = ExecutionStatus.PARTIAL

        final_result = automation_executor.aggregate_results(executed)
        first_error = next(
            (s["error"] for s in executed if s["status"] == "failed" and s.get("error")),
            None,
        )

        execution_response = AutomationExecutionResponse(
            execution_id=execution_id,
            automation_id=automation_id,
            status=status,
            started_at=started_at,
            completed_at=datetime.utcnow().isoformat(),
            duration_ms=int((time.time() - start) * 1000),
            steps=[ExecutionStep(**s) for s in executed],
            final_result=final_result,
            error_message=first_error,
            total_steps=len(executed),
            successful_steps=successful,
            failed_steps=failed,
        )

        # Run output actions before we mark the execution as done so they are
        # persisted with the row.
        output_results: List[Dict[str, Any]] = []
        if status != ExecutionStatus.FAILED:
            for raw in automation.get("output_actions") or []:
                pass  # placeholder: dispatch happens below
            output_actions = automation.get("output_actions") or []
            if output_actions:
                try:
                    output_results = await automation_output_service.process_output_actions(
                        execution_response, output_actions, db=db
                    )
                    execution_response.output_results = output_results
                except Exception:
                    logger.exception("Output action processing failed")

        await exec_repo.update_execution(
            execution_id=execution_id,
            status=status.value,
            steps=executed,
            result=final_result,
            error=first_error,
            output_results=output_results or None,
        )
        await auto_repo.increment_run_count(
            automation_id=automation_id,
            last_run=execution_response.completed_at,
        )

        return execution_response

    @staticmethod
    def _failed_response(
        execution_id: str,
        automation_id: str,
        started_at: str,
        duration_ms: int,
        error: str,
    ) -> AutomationExecutionResponse:
        return AutomationExecutionResponse(
            execution_id=execution_id,
            automation_id=automation_id,
            status=ExecutionStatus.FAILED,
            started_at=started_at,
            completed_at=datetime.utcnow().isoformat(),
            duration_ms=duration_ms,
            steps=[],
            final_result="",
            error_message=error,
            total_steps=0,
            successful_steps=0,
            failed_steps=0,
        )


automation_engine = AutomationEngine()
