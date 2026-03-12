"""
Automation Executor Service
Handles low-level execution of automation steps by calling ai-chat endpoint
"""

import httpx
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import time


class AutomationExecutor:
    """
    Executes individual automation steps by calling the ai-chat endpoint.
    Handles context passing, error handling, and result aggregation.
    """

    def __init__(self):
        # Get the base URL for ai-chat endpoint
        # In production, this would be the internal service URL
        self.ai_chat_base_url = os.getenv(
            "AI_CHAT_URL",
            "http://localhost:18741"  # Default for desktop sidecar
        )
        self.ai_chat_endpoint = f"{self.ai_chat_base_url}/api/v1/ai-chat"

    async def execute_step(
        self,
        step_number: int,
        persona: str,
        instruction: str,
        context: str,
        user_id: str,
        model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a single automation step by calling ai-chat endpoint.

        Args:
            step_number: Sequential step number
            persona: Persona name to use (without @ symbol)
            instruction: The instruction for this step
            context: Accumulated context from previous steps
            user_id: User ID for the request
            model_id: Optional model ID to use

        Returns:
            Dictionary containing:
            - step_number: int
            - persona: str
            - instruction: str
            - full_prompt: str
            - result: str
            - status: str (success/failed)
            - error: Optional[str]
            - duration_ms: int
        """
        start_time = time.time()

        try:
            # Build full prompt with context
            full_prompt = self._build_prompt_with_context(instruction, context)

            print(f"\n🔄 Executing Step {step_number}:")
            print(f"   Persona: @{persona}")
            print(f"   Instruction: {instruction}")
            print(f"   Prompt length: {len(full_prompt)} chars")

            # Call ai-chat endpoint
            result = await self._call_ai_chat(
                persona_id=persona,
                prompt=full_prompt,
                user_id=user_id,
                model_id=model_id
            )

            duration_ms = int((time.time() - start_time) * 1000)

            print(f"   ✅ Step completed in {duration_ms}ms")
            print(f"   Result preview: {result[:100]}...")

            return {
                "step_number": step_number,
                "persona": persona,
                "instruction": instruction,
                "full_prompt": full_prompt,
                "result": result,
                "status": "success",
                "error": None,
                "duration_ms": duration_ms
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_message = str(e)

            print(f"   ❌ Step failed in {duration_ms}ms")
            print(f"   Error: {error_message}")

            return {
                "step_number": step_number,
                "persona": persona,
                "instruction": instruction,
                "full_prompt": full_prompt if 'full_prompt' in locals() else instruction,
                "result": "",
                "status": "failed",
                "error": error_message,
                "duration_ms": duration_ms
            }

    async def _call_ai_chat(
        self,
        persona_id: str,
        prompt: str,
        user_id: str,
        model_id: Optional[str] = None
    ) -> str:
        """
        Call the ai-chat endpoint with the given parameters.

        Args:
            persona_id: Persona to use
            prompt: Full prompt text
            user_id: User ID
            model_id: Optional model ID

        Returns:
            Response text from AI

        Raises:
            Exception: If API call fails
        """
        # Build request payload
        payload = {
            "prompt": prompt,
            "userId": user_id,
            "persona_id": persona_id,
            "stream": False,  # Synchronous execution
            "max_tokens": 4096,
            "temperature": 0.7
        }

        if model_id:
            payload["model_id"] = model_id

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.ai_chat_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                response.raise_for_status()
                data = response.json()

                # Extract response from ai-chat endpoint response
                if "response" in data:
                    return data["response"]
                elif "result" in data:
                    return data["result"]
                else:
                    raise Exception(f"Unexpected response format: {data}")

        except httpx.HTTPStatusError as e:
            raise Exception(f"AI chat API error ({e.response.status_code}): {e.response.text}")
        except httpx.TimeoutException:
            raise Exception("AI chat request timed out after 60 seconds")
        except Exception as e:
            raise Exception(f"Failed to call AI chat endpoint: {str(e)}")

    def _build_prompt_with_context(self, instruction: str, context: str) -> str:
        """
        Build a complete prompt including accumulated context from previous steps.

        Args:
            instruction: The instruction for this step
            context: Context from previous steps

        Returns:
            Complete prompt string
        """
        if not context or context.strip() == "":
            # First step - no context
            return instruction

        # Subsequent steps - include context
        return f"""{instruction}

Previous Steps Context:
{context}

Please use the information from previous steps to complete this task."""

    def aggregate_results(self, steps: List[Dict[str, Any]]) -> str:
        """
        Aggregate results from all steps into a final summary.

        Args:
            steps: List of step execution results

        Returns:
            Human-readable summary of all results
        """
        if not steps:
            return "No steps executed"

        # Build summary
        summary_parts = []

        for step in steps:
            step_num = step.get("step_number", 0)
            persona = step.get("persona", "unknown")
            status = step.get("status", "unknown")
            result = step.get("result", "")

            if status == "success":
                summary_parts.append(f"Step {step_num} (@{persona}): {result}")
            else:
                error = step.get("error", "Unknown error")
                summary_parts.append(f"Step {step_num} (@{persona}): Failed - {error}")

        return "\n\n".join(summary_parts)

    def build_context_from_steps(self, steps: List[Dict[str, Any]]) -> str:
        """
        Build context string from completed steps to pass to next step.

        Args:
            steps: List of completed step results

        Returns:
            Formatted context string
        """
        if not steps:
            return ""

        context_parts = []

        for step in steps:
            step_num = step.get("step_number", 0)
            persona = step.get("persona", "unknown")
            result = step.get("result", "")

            if result:  # Only include successful results
                context_parts.append(f"Step {step_num} (@{persona}): {result}")

        return "\n".join(context_parts)


# Singleton instance
automation_executor = AutomationExecutor()
