"""
Prompt Parser Service
Analyzes natural language automation prompts to detect:
- @persona mentions
- Execution flow (sequential vs parallel)
- Data dependencies between steps
"""

import re
from typing import List, Dict, Any, Tuple
from models.automation_models import ExecutionMode


class PromptParser:
    """
    Parser for natural language automation prompts.
    Detects personas, execution modes, and workflow structure.
    """

    # Keywords indicating sequential execution
    SEQUENTIAL_KEYWORDS = [
        "then", "after", "afterwards", "next", "followed by",
        "subsequently", "once", "when", "first", "second", "finally"
    ]

    # Keywords indicating parallel execution
    PARALLEL_KEYWORDS = [
        "and", "also", "simultaneously", "at the same time",
        "concurrently", "together", "along with", "in parallel"
    ]

    # Keywords indicating conditional logic
    CONDITIONAL_KEYWORDS = [
        "if", "when", "unless", "in case", "provided that",
        "depending on", "based on", "should"
    ]

    def parse(self, prompt: str) -> Dict[str, Any]:
        """
        Parse automation prompt and extract structure.

        Args:
            prompt: Natural language automation prompt

        Returns:
            Dictionary containing:
            - personas: List of detected persona names
            - execution_mode: sequential, parallel, or smart
            - is_valid: Whether prompt has required elements
            - warnings: List of potential issues
            - suggestions: List of improvement suggestions
            - data_flow: Detected data dependencies
        """
        # Detect personas
        personas = self._detect_personas(prompt)

        # Detect execution mode
        execution_mode = self._detect_execution_mode(prompt)

        # Detect data flow and dependencies
        data_flow = self._detect_data_flow(prompt, personas)

        # Validate prompt
        is_valid = len(personas) > 0
        warnings = self._generate_warnings(prompt, personas, execution_mode)
        suggestions = self._generate_suggestions(prompt, personas, execution_mode)

        return {
            "personas": personas,
            "execution_mode": execution_mode,
            "is_valid": is_valid,
            "warnings": warnings,
            "suggestions": suggestions,
            "data_flow": data_flow,
            "has_conditionals": self._has_conditionals(prompt)
        }

    def _detect_personas(self, prompt: str) -> List[str]:
        """
        Detect all @persona mentions in the prompt.

        Args:
            prompt: Automation prompt text

        Returns:
            List of persona names (without @ symbol)
        """
        # Find all @word patterns (negative lookbehind excludes emails like user@domain)
        persona_pattern = r'(?<![a-zA-Z0-9.])@(\w+)'
        matches = re.findall(persona_pattern, prompt)

        # Remove duplicates while preserving order
        seen = set()
        personas = []
        for persona in matches:
            if persona not in seen:
                seen.add(persona)
                personas.append(persona)

        return personas

    def _detect_execution_mode(self, prompt: str) -> str:
        """
        Determine if execution should be sequential or parallel.

        Args:
            prompt: Automation prompt text

        Returns:
            ExecutionMode enum value
        """
        prompt_lower = prompt.lower()

        # Check for sequential keywords
        has_sequential = any(
            keyword in prompt_lower
            for keyword in self.SEQUENTIAL_KEYWORDS
        )

        # Check for parallel keywords
        has_parallel = any(
            keyword in prompt_lower
            for keyword in self.PARALLEL_KEYWORDS
        )

        # Decision logic
        if has_sequential and not has_parallel:
            return ExecutionMode.SEQUENTIAL.value
        elif has_parallel and not has_sequential:
            return ExecutionMode.PARALLEL.value
        elif has_sequential and has_parallel:
            # Mixed: default to sequential (safer)
            return ExecutionMode.SEQUENTIAL.value
        else:
            # No clear indicators: let AI decide
            return ExecutionMode.SMART.value

    def _detect_data_flow(self, prompt: str, personas: List[str]) -> List[Dict[str, Any]]:
        """
        Detect data dependencies between personas.

        Args:
            prompt: Automation prompt text
            personas: List of detected personas

        Returns:
            List of data flow connections
        """
        data_flow = []

        # Pattern: "use X from @persona" or "pass Y to @persona"
        flow_patterns = [
            r'use\s+(?:the\s+)?(\w+)\s+from\s+@(\w+)',
            r'pass\s+(?:the\s+)?(\w+)\s+to\s+@(\w+)',
            r'send\s+(?:the\s+)?(\w+)\s+to\s+@(\w+)',
            r'@(\w+).*?results?\s+to\s+@(\w+)',
        ]

        for pattern in flow_patterns:
            matches = re.finditer(pattern, prompt, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) >= 2:
                    data_flow.append({
                        "from": match.group(2) if len(match.groups()) > 1 else None,
                        "to": match.group(1) if len(match.groups()) > 1 else match.group(2),
                        "data": match.group(1) if len(match.groups()) > 1 else "result"
                    })

        return data_flow

    def _has_conditionals(self, prompt: str) -> bool:
        """Check if prompt contains conditional logic."""
        prompt_lower = prompt.lower()
        return any(
            keyword in prompt_lower
            for keyword in self.CONDITIONAL_KEYWORDS
        )

    def _generate_warnings(
        self,
        prompt: str,
        personas: List[str],
        execution_mode: str
    ) -> List[str]:
        """
        Generate warnings about potential issues.

        Args:
            prompt: Automation prompt text
            personas: Detected personas
            execution_mode: Detected execution mode

        Returns:
            List of warning messages
        """
        warnings = []

        # No personas detected
        if len(personas) == 0:
            warnings.append(
                "No @personas detected. Use @ symbol to reference connectors "
                "(e.g., @salesforce_db, @slack_notifier)"
            )

        # Only one persona (might be better as direct chat)
        if len(personas) == 1:
            warnings.append(
                "Only one persona detected. Consider using direct chat instead of automation."
            )

        # Conditional logic detected (not yet supported)
        if self._has_conditionals(prompt):
            warnings.append(
                "Conditional logic detected but not yet fully supported. "
                "Automation will execute all steps regardless of conditions."
            )

        # Very long prompt
        if len(prompt) > 1000:
            warnings.append(
                "Prompt is quite long. Consider breaking into multiple simpler automations."
            )

        return warnings

    def _generate_suggestions(
        self,
        prompt: str,
        personas: List[str],
        execution_mode: str
    ) -> List[str]:
        """
        Generate suggestions for improvement.

        Args:
            prompt: Automation prompt text
            personas: Detected personas
            execution_mode: Detected execution mode

        Returns:
            List of suggestion messages
        """
        suggestions = []

        # Suggest making execution order explicit
        if execution_mode == ExecutionMode.SMART.value and len(personas) > 1:
            suggestions.append(
                "Consider making execution order explicit using 'then' for sequential "
                "or 'and' for parallel execution."
            )

        # Suggest error handling
        if len(personas) > 2:
            suggestions.append(
                "For multi-step automations, consider what should happen if a step fails."
            )

        # Suggest data passing syntax
        if execution_mode == ExecutionMode.SEQUENTIAL.value and len(personas) > 1:
            has_data_passing = any([
                "use" in prompt.lower(),
                "pass" in prompt.lower(),
                "send" in prompt.lower()
            ])
            if not has_data_passing:
                suggestions.append(
                    "Consider explicitly stating how data flows between steps "
                    "(e.g., 'use the results from @db in @email')"
                )

        return suggestions

    def validate_persona_exists(
        self,
        persona_name: str,
        available_personas: List[str]
    ) -> Tuple[bool, str]:
        """
        Validate if a persona exists in the system.

        Args:
            persona_name: Name of persona to validate
            available_personas: List of available persona names

        Returns:
            Tuple of (exists: bool, message: str)
        """
        if persona_name in available_personas:
            return True, f"Persona '@{persona_name}' found"
        else:
            similar = self._find_similar_personas(persona_name, available_personas)
            if similar:
                return False, f"Persona '@{persona_name}' not found. Did you mean: {', '.join(['@' + p for p in similar])}?"
            else:
                return False, f"Persona '@{persona_name}' not found"

    def _find_similar_personas(
        self,
        persona_name: str,
        available_personas: List[str],
        threshold: int = 3
    ) -> List[str]:
        """
        Find similar persona names using simple string distance.

        Args:
            persona_name: Target persona name
            available_personas: Available persona names
            threshold: Maximum edit distance

        Returns:
            List of similar persona names
        """
        similar = []
        for available in available_personas:
            distance = self._levenshtein_distance(
                persona_name.lower(),
                available.lower()
            )
            if distance <= threshold:
                similar.append(available)

        return similar[:3]  # Return top 3 matches

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost of insertions, deletions, or substitutions
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]


# Singleton instance
prompt_parser = PromptParser()
