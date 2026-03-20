"""
Trigger Service — matches inbound channel messages to triggers and dispatches.

When a message arrives via a channel webhook, the TriggerService:
1. Looks up matching triggers for that channel
2. Checks cooldown
3. If a crew is assigned, runs the crew and returns its output
4. If approval_required, stores the draft instead of returning it directly
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.trigger_repository import TriggerRepository

logger = logging.getLogger(__name__)


class TriggerService:
    """Evaluate triggers against inbound messages and dispatch accordingly."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.trigger_repo = TriggerRepository(db)

    async def check_and_dispatch(
        self,
        msg: Any,  # ChannelMessage
        session: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Check if a trigger matches the inbound message.

        Returns a result dict with ``response`` and ``status`` if a
        trigger matched, or ``None`` if no trigger applies (caller
        should fall through to default AI).
        """
        trigger = await self.trigger_repo.find_for_channel(
            channel_type=msg.channel_type.value,
            channel_id=msg.channel_id,
        )
        if trigger is None:
            return None

        # Cooldown check
        if not self._check_cooldown(trigger):
            logger.debug(
                "Trigger %s in cooldown, skipping", trigger["trigger_id"]
            )
            return None

        # Record the fire
        await self.trigger_repo.record_fire(trigger["trigger_id"])

        # Dispatch to crew or direct agent
        crew_id = trigger.get("crew_id")
        agent_id = trigger.get("agent_id")

        try:
            if crew_id:
                response_text = await self._run_crew(crew_id, msg)
            elif agent_id:
                response_text = await self._run_agent(agent_id, msg)
            else:
                # No crew or agent — use default AI
                return None
        except Exception as e:
            logger.error("Trigger dispatch failed: %s", e, exc_info=True)
            return {
                "response": "Sorry, I couldn't process that right now.",
                "status": "error",
                "trigger_id": trigger["trigger_id"],
            }

        # Approval gate
        if trigger.get("approval_required"):
            try:
                from services.approval_service import ApprovalService
                approval_svc = ApprovalService(self.db)
                approval = await approval_svc.create_approval(
                    trigger_id=trigger["trigger_id"],
                    channel_type=msg.channel_type.value,
                    channel_id=msg.channel_id,
                    sender_name=msg.sender_name,
                    sender_id=msg.sender_id,
                    inbound_text=msg.text,
                    draft_response=response_text,
                    session_id=session["session_id"],
                )
                return {
                    "response": response_text,
                    "status": "pending_approval",
                    "trigger_id": trigger["trigger_id"],
                    "approval_id": approval["approval_id"],
                }
            except ImportError:
                pass  # approval_service not yet available

        return {
            "response": response_text,
            "status": "replied",
            "trigger_id": trigger["trigger_id"],
        }

    def _check_cooldown(self, trigger: Dict[str, Any]) -> bool:
        """Return True if the trigger is NOT in cooldown."""
        cooldown = trigger.get("cooldown_seconds", 0)
        if cooldown <= 0:
            return True

        last_fired = trigger.get("last_fired_at")
        if not last_fired:
            return True

        try:
            last_dt = datetime.fromisoformat(last_fired)
            return datetime.utcnow() >= last_dt + timedelta(seconds=cooldown)
        except (ValueError, TypeError):
            return True

    async def _run_crew(self, crew_id: str, msg: Any) -> str:
        """Execute a crew synchronously and return its output."""
        from services.crew_service import CrewService
        from services.crew_orchestrator import CrewOrchestrator
        from repositories.crew_repository import CrewRepository
        from repositories.crew_run_repository import CrewRunRepository
        from services.crew_memory_service import CrewMemoryService

        crew_repo = CrewRepository(self.db)
        run_repo = CrewRunRepository(self.db)
        memory_svc = CrewMemoryService(self.db)

        crew = await crew_repo.get_by_crew_id(crew_id)
        if not crew:
            return f"Crew '{crew_id}' not found."

        # Create a run
        from pydantic import BaseModel

        class FakeRunRequest:
            input = msg.text
            input_data = {
                "channel_type": msg.channel_type.value,
                "sender_name": msg.sender_name,
                "sender_id": msg.sender_id,
            }

        crew_svc = CrewService(self.db)
        run = await crew_svc.start_run(crew_id, "desktop-user", FakeRunRequest())

        # Wait for the crew to finish (poll with timeout)
        import asyncio
        run_id = run.get("run_id")
        for _ in range(120):  # 2 minutes max
            await asyncio.sleep(1)
            run_doc = await run_repo.get_by_run_id(run_id)
            if not run_doc:
                break
            status = run_doc.get("status", "")
            if status in ("completed", "failed", "cancelled"):
                output = run_doc.get("output", "")
                if status == "completed" and output:
                    return output
                elif status == "failed":
                    error = run_doc.get("error", "Crew execution failed")
                    return f"Error: {error}"
                break

        return "Crew did not complete in time."

    async def _run_agent(self, agent_id: str, msg: Any) -> str:
        """Run a single agent and return its output."""
        from services.local_model_service import local_model_service, LLAMA_CPP_AVAILABLE
        from services.default_model_service import DefaultModelService

        # Load agent
        coll = self.db["workspace_agents"]
        agent = await coll.find_one({"_id": agent_id})
        if not agent:
            agent = await coll.find_one({"agent_id": agent_id})
        if not agent:
            return f"Agent '{agent_id}' not found."

        system_prompt = agent.get("system_prompt", "You are a helpful assistant.")

        default_svc = DefaultModelService(self.db)
        ai_mode = await default_svc.get_ai_mode_preference()
        model_id = await default_svc.get_default_model_id(ai_mode)

        if not model_id or not LLAMA_CPP_AVAILABLE:
            return "No local model available."

        model_config = await default_svc.get_default_model_config(ai_mode)
        result = await local_model_service.call_model(
            prompt=msg.text,
            model_id=model_id,
            persona_context={"system_prompt": system_prompt},
            max_tokens=1024,
            temperature=0.7,
            stream=False,
            model_config=model_config or {},
        )
        return result.get("content", "I couldn't generate a response.")
