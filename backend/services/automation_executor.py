"""
Automation Executor Service

Runs a single automation step. Solo variant:
- Resolves the @persona to an agent in ``workspace_agents``.
- Picks up that agent's ``system_prompt`` and ``model_id`` (with a global
  fallback resolved from the ``models`` collection).
- For ``local-*`` / ``local:*`` model IDs, calls ``LocalModelService.generate``
  directly — same path used by ``services/workspace/agent_runner.py``.
- For other model IDs, defers to ``UniversalModelAdapter.invoke_model``.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)


class AutomationExecutor:
    """Run a single automation step and return its trace."""

    async def execute_step(
        self,
        step_number: int,
        persona: str,
        instruction: str,
        context: str,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        start = time.time()
        full_prompt = ""

        try:
            agent = await self._resolve_agent(persona)
            resolved_model = (
                model_id
                or (agent.get("model_id") if agent else None)
                or await self._default_model_id()
            )
            if not resolved_model:
                raise RuntimeError(
                    "No AI model is configured. Download a local model from the Model Hub or pick one in Settings."
                )

            full_prompt = self._build_prompt(
                instruction=instruction,
                context=context,
                system_prompt=(agent or {}).get("system_prompt") or "",
            )
            content = await self._call_model(resolved_model, full_prompt)

            duration_ms = int((time.time() - start) * 1000)
            return {
                "step_number": step_number,
                "persona": persona,
                "instruction": instruction,
                "full_prompt": full_prompt,
                "result": content or "",
                "status": "success",
                "error": None,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            logger.exception("Step %d (@%s) failed", step_number, persona)
            duration_ms = int((time.time() - start) * 1000)
            return {
                "step_number": step_number,
                "persona": persona,
                "instruction": instruction,
                "full_prompt": full_prompt or instruction,
                "result": "",
                "status": "failed",
                "error": str(e),
                "duration_ms": duration_ms,
            }

    @staticmethod
    def _build_prompt(instruction: str, context: str, system_prompt: str) -> str:
        sections: List[str] = []
        if system_prompt:
            sections.append(f"# Role\n{system_prompt.strip()}")
        sections.append(f"# Task\n{instruction.strip()}")
        if context.strip():
            sections.append(f"# Previous step results\n{context.strip()}")
            sections.append("Use the prior results to complete this task.")
        return "\n\n".join(sections)

    async def _resolve_agent(self, persona: str) -> Optional[Dict[str, Any]]:
        """Find an agent in ``workspace_agents`` by slug or name."""
        db = await get_database()
        coll = db["workspace_agents"]
        row = await coll.find_one({"slug": persona})
        if not row:
            row = await coll.find_one(
                {"name": {"$regex": f"^{persona}$", "$options": "i"}}
            )
        if not row:
            row = await coll.find_one({"_id": {"$regex": f"-{persona}$"}})
        if not row:
            return None
        if "_id" in row and "id" not in row:
            row["id"] = str(row["_id"])
            row.pop("_id", None)
        return row

    async def _default_model_id(self) -> Optional[str]:
        """Pick a model when neither the automation nor the agent set one."""
        db = await get_database()
        coll = db["models"]
        local = await coll.find_one({"provider": "local"})
        if local:
            return local.get("id") or str(local.get("_id"))
        any_model = await coll.find_one({})
        if any_model:
            return any_model.get("id") or str(any_model.get("_id"))
        return None

    async def _call_model(self, model_id: str, prompt: str) -> str:
        """Route the prompt through Solo's model layer."""
        if model_id.startswith("local-") or model_id.startswith("local:"):
            from services.local_model_service import LocalModelService
            catalog_id = model_id.replace("local-", "").replace("local:", "")
            return await LocalModelService().generate(
                model_id=catalog_id, prompt=prompt, max_tokens=2048
            )

        # Cloud / Bedrock path — defer to the universal adapter.
        try:
            from services.universal_model_adapter import UniversalModelAdapter
            adapter = UniversalModelAdapter()
            result = await adapter.invoke_model(
                model_id=model_id,
                prompt=prompt,
                max_tokens=2048,
                temperature=0.7,
                stream=False,
            )
            if isinstance(result, dict):
                return result.get("content") or result.get("response") or ""
            return str(result or "")
        except Exception as cloud_err:
            logger.warning(
                "Cloud model adapter failed for %s (%s) — falling back to local",
                model_id,
                cloud_err,
            )
            from services.local_model_service import LocalModelService
            catalog_id = model_id.replace("local-", "").replace("local:", "")
            return await LocalModelService().generate(
                model_id=catalog_id, prompt=prompt, max_tokens=2048
            )

    @staticmethod
    def aggregate_results(steps: List[Dict[str, Any]]) -> str:
        if not steps:
            return ""
        parts: List[str] = []
        for step in steps:
            persona = step.get("persona", "?")
            num = step.get("step_number", 0)
            if step.get("status") == "success":
                parts.append(f"Step {num} (@{persona}): {step.get('result', '')}")
            elif step.get("status") == "skipped":
                parts.append(f"Step {num} (@{persona}): skipped — {step.get('result', '')}")
            else:
                parts.append(
                    f"Step {num} (@{persona}): failed — {step.get('error') or 'unknown error'}"
                )
        return "\n\n".join(parts)

    @staticmethod
    def build_context_from_steps(steps: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for step in steps:
            if step.get("status") != "success":
                continue
            result = step.get("result") or ""
            if not result:
                continue
            persona = step.get("persona", "?")
            num = step.get("step_number", 0)
            parts.append(f"Step {num} (@{persona}): {result}")
        return "\n".join(parts)


automation_executor = AutomationExecutor()
