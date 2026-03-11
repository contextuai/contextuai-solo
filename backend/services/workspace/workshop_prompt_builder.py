"""
Workshop Prompt Builder for AI Team Workspace Feature

Builds structured prompts for workshop agents, incorporating workshop configuration,
round context, and previous agent contributions for multi-round collaborative sessions.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional

# Configure logging
logger = logging.getLogger(__name__)


class WorkshopPromptBuilder:
    """
    Builder for workshop agent prompts.

    Constructs system and user prompts tailored to workshop sessions,
    incorporating agent blueprints, workshop configuration, round context,
    and contributions from previous agents and rounds.
    """

    # Facilitation style instructions
    FACILITATION_STYLES = {
        "structured": (
            "Follow a structured approach: clearly state your position, "
            "provide supporting evidence, and conclude with actionable recommendations. "
            "Use numbered points and clear headings."
        ),
        "brainstorm": (
            "Think creatively and expansively. Generate as many ideas as possible "
            "without self-censoring. Build on others' ideas where applicable. "
            "Prioritize volume and novelty of ideas over polish."
        ),
        "debate": (
            "Take a clear stance and defend it with evidence and reasoning. "
            "Respectfully challenge assumptions and counter-arguments from other contributors. "
            "Identify strengths and weaknesses in different positions."
        ),
        "consensus": (
            "Seek common ground with other contributors. Identify shared themes "
            "and areas of agreement. Where disagreements exist, propose compromises "
            "or synthesis positions that incorporate multiple viewpoints."
        ),
        "advisory": (
            "Provide expert advisory input from your specialized perspective. "
            "Focus on practical, actionable guidance. Highlight risks and opportunities "
            "that others may have overlooked."
        ),
    }

    # Output format instructions
    OUTPUT_FORMAT_INSTRUCTIONS = {
        "report": (
            "Structure your contribution as a section of a formal report. "
            "Use clear headings, professional language, and support your points "
            "with reasoning. Include specific recommendations where applicable."
        ),
        "slides": (
            "Structure your contribution as presentation-ready content. "
            "Use concise bullet points, one key idea per section. "
            "Focus on clarity and impact. Include speaker notes where helpful."
        ),
        "canvas": (
            "Structure your contribution to fit a business canvas format. "
            "Organize your input into clear categories relevant to the canvas model. "
            "Be concise and use short, impactful phrases."
        ),
        "brief": (
            "Keep your contribution concise and executive-friendly. "
            "Lead with the most important insight or recommendation. "
            "Limit supporting detail to what is essential for decision-making."
        ),
    }

    def build_workshop_prompt(
        self,
        agent_blueprint: Dict[str, Any],
        workshop_config: Dict[str, Any],
        round_number: int,
        previous_contributions: List[Dict[str, Any]],
        project_context: Dict[str, Any],
    ) -> Tuple[str, str]:
        """
        Build system and user prompts for a workshop agent.

        Args:
            agent_blueprint: The agent's configuration/blueprint, including
                system_prompt (from .md content), name, description, category,
                and capabilities.
            workshop_config: Workshop configuration dict with keys:
                - topic (str): The workshop topic or question
                - workshop_type (str): Type of workshop (e.g. "brainstorm", "analysis")
                - num_rounds (int): Total number of discussion rounds
                - output_format (str): Desired output format ("report", "slides", "canvas", "brief")
                - facilitation_style (str): Style of facilitation
            round_number: Current round number (1-indexed)
            previous_contributions: List of contribution dicts, each with:
                - agent_id (str): ID of the contributing agent
                - agent_name (str): Display name of the contributing agent
                - content (str): The contribution text
                - round_number (int): Which round the contribution was made in
            project_context: Project-level context dict with name, description,
                tech_stack, etc.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_prompt = self._build_system_prompt(agent_blueprint)
        user_prompt = self._build_user_prompt(
            agent_blueprint=agent_blueprint,
            workshop_config=workshop_config,
            round_number=round_number,
            previous_contributions=previous_contributions,
            project_context=project_context,
        )

        logger.debug(
            f"Built workshop prompt for agent '{agent_blueprint.get('name', 'Unknown')}' "
            f"(round {round_number}, system_prompt length: {len(system_prompt)}, "
            f"user_prompt length: {len(user_prompt)})"
        )

        return system_prompt, user_prompt

    def _build_system_prompt(self, agent_blueprint: Dict[str, Any]) -> str:
        """
        Build the system prompt from the agent blueprint.

        Uses the agent's system_prompt field (typically loaded from .md content).
        Falls back to the agent's description if no system_prompt is defined.

        Args:
            agent_blueprint: The agent's configuration/blueprint

        Returns:
            System prompt string
        """
        # Primary: use the agent's system_prompt field (from .md content)
        system_prompt = agent_blueprint.get("system_prompt", "").strip()

        if system_prompt:
            return system_prompt

        # Fallback: construct from description and role information
        name = agent_blueprint.get("name", "Workshop Agent")
        description = agent_blueprint.get("description", "").strip()
        category = agent_blueprint.get("category", "specialized")
        capabilities = agent_blueprint.get("capabilities", [])

        parts = []

        if description:
            parts.append(description)
        else:
            parts.append(
                f"You are {name}, a {category} agent participating in a collaborative workshop."
            )

        if capabilities:
            parts.append(
                f"Your areas of expertise include: {', '.join(capabilities)}."
            )

        parts.append(
            "Provide thoughtful, well-reasoned contributions that draw on your "
            "specialized knowledge and perspective."
        )

        fallback_prompt = " ".join(parts)

        logger.debug(
            f"No system_prompt found for agent '{name}', using description fallback"
        )

        return fallback_prompt

    def _build_user_prompt(
        self,
        agent_blueprint: Dict[str, Any],
        workshop_config: Dict[str, Any],
        round_number: int,
        previous_contributions: List[Dict[str, Any]],
        project_context: Dict[str, Any],
    ) -> str:
        """
        Build the user prompt with full workshop context.

        Args:
            agent_blueprint: The agent's configuration/blueprint
            workshop_config: Workshop configuration
            round_number: Current round number (1-indexed)
            previous_contributions: Previous contributions from agents
            project_context: Project-level context

        Returns:
            User prompt string
        """
        parts = []

        # 1. Workshop topic and type
        parts.append(self._build_workshop_header(workshop_config, round_number))

        # 2. Project context (if available)
        project_section = self._build_project_context(project_context)
        if project_section:
            parts.append(project_section)

        # 3. Output format instructions
        parts.append(self._build_output_instructions(workshop_config))

        # 4. Round number context
        parts.append(self._build_round_context(workshop_config, round_number))

        # 5. Facilitation style instructions
        parts.append(self._build_facilitation_instructions(workshop_config))

        # 6. Previous contributions (for rounds > 1 or when other agents
        #    have already contributed in the current round)
        if previous_contributions:
            parts.append(
                self._build_previous_contributions(
                    previous_contributions, round_number
                )
            )

        # 7. Structured output instructions
        parts.append(self._build_structured_output_instructions(
            agent_blueprint, workshop_config, round_number
        ))

        return "\n\n".join(parts)

    def _build_workshop_header(
        self, workshop_config: Dict[str, Any], round_number: int
    ) -> str:
        """
        Build the workshop header section with topic and type.

        Args:
            workshop_config: Workshop configuration
            round_number: Current round number

        Returns:
            Workshop header string
        """
        topic = workshop_config.get("topic", "General Discussion")
        workshop_type = workshop_config.get("workshop_type", "discussion")
        num_rounds = workshop_config.get("num_rounds", 1)

        lines = [
            "<workshop>",
            f"Topic: {topic}",
            f"Workshop Type: {workshop_type}",
            f"Round: {round_number} of {num_rounds}",
            "</workshop>",
        ]

        return "\n".join(lines)

    def _build_project_context(self, project_context: Dict[str, Any]) -> Optional[str]:
        """
        Build the project context section.

        Args:
            project_context: Project-level context

        Returns:
            Project context string, or None if no context available
        """
        if not project_context:
            return None

        name = project_context.get("name", "")
        description = project_context.get("description", "")
        tech_stack = project_context.get("tech_stack", [])

        if not name and not description:
            return None

        lines = ["<project_context>"]

        if name:
            lines.append(f"Project: {name}")
        if description:
            lines.append(f"Description: {description}")
        if tech_stack:
            lines.append(f"Tech Stack: {', '.join(tech_stack)}")

        lines.append("</project_context>")

        return "\n".join(lines)

    def _build_output_instructions(self, workshop_config: Dict[str, Any]) -> str:
        """
        Build output format instructions.

        Args:
            workshop_config: Workshop configuration

        Returns:
            Output format instructions string
        """
        output_format = workshop_config.get("output_format", "report")
        instruction = self.OUTPUT_FORMAT_INSTRUCTIONS.get(
            output_format,
            self.OUTPUT_FORMAT_INSTRUCTIONS["report"],
        )

        return f"<output_format>\nTarget format: {output_format}\n{instruction}\n</output_format>"

    def _build_round_context(
        self, workshop_config: Dict[str, Any], round_number: int
    ) -> str:
        """
        Build round-specific context and instructions.

        Provides different guidance depending on whether this is the first round,
        a middle round, or the final round.

        Args:
            workshop_config: Workshop configuration
            round_number: Current round number

        Returns:
            Round context string
        """
        num_rounds = workshop_config.get("num_rounds", 1)
        topic = workshop_config.get("topic", "the topic")

        if num_rounds == 1:
            return (
                "<round_instructions>\n"
                "This is a single-round workshop. Provide your complete analysis "
                f"and recommendations on: {topic}\n"
                "</round_instructions>"
            )

        if round_number == 1:
            return (
                "<round_instructions>\n"
                f"This is Round 1 of {num_rounds}. Provide your initial analysis, "
                "key observations, and preliminary recommendations. "
                "Focus on establishing your core perspective and identifying the "
                "most important aspects of the topic. Other agents will also contribute "
                "their perspectives, and you will have the opportunity to build on "
                "the discussion in subsequent rounds.\n"
                "</round_instructions>"
            )

        if round_number == num_rounds:
            return (
                "<round_instructions>\n"
                f"This is the FINAL round (Round {round_number} of {num_rounds}). "
                "Review the contributions from previous rounds and provide your "
                "final, refined perspective. Synthesize key insights, resolve any "
                "outstanding disagreements, and provide concrete, actionable "
                "conclusions and next steps.\n"
                "</round_instructions>"
            )

        return (
            "<round_instructions>\n"
            f"This is Round {round_number} of {num_rounds}. "
            "Review the contributions from previous rounds. Build on what others "
            "have said, address any gaps or counterarguments, refine your position, "
            "and add new insights that advance the discussion.\n"
            "</round_instructions>"
        )

    def _build_facilitation_instructions(
        self, workshop_config: Dict[str, Any]
    ) -> str:
        """
        Build facilitation style instructions.

        Args:
            workshop_config: Workshop configuration

        Returns:
            Facilitation style instructions string
        """
        style = workshop_config.get("facilitation_style", "structured")
        instruction = self.FACILITATION_STYLES.get(
            style,
            self.FACILITATION_STYLES["structured"],
        )

        return f"<facilitation_style>\nStyle: {style}\n{instruction}\n</facilitation_style>"

    def _build_previous_contributions(
        self,
        previous_contributions: List[Dict[str, Any]],
        current_round: int,
    ) -> str:
        """
        Build the previous contributions section.

        Organizes contributions by round for clarity.

        Args:
            previous_contributions: List of contribution dicts
            current_round: Current round number

        Returns:
            Previous contributions string
        """
        if not previous_contributions:
            return ""

        # Group contributions by round
        rounds: Dict[int, List[Dict[str, Any]]] = {}
        for contribution in previous_contributions:
            rnd = contribution.get("round_number", 1)
            if rnd not in rounds:
                rounds[rnd] = []
            rounds[rnd].append(contribution)

        lines = ["<previous_contributions>"]

        for rnd in sorted(rounds.keys()):
            contributions_in_round = rounds[rnd]

            if len(rounds) > 1:
                lines.append(f"\n--- Round {rnd} ---")

            for contrib in contributions_in_round:
                agent_name = contrib.get("agent_name", "Unknown Agent")
                content = contrib.get("content", "")

                # Truncate very long contributions to keep prompt manageable
                if len(content) > 4000:
                    content = content[:4000] + "\n...[truncated]..."

                lines.append(
                    f"\n<contribution agent=\"{agent_name}\" round=\"{rnd}\">"
                )
                lines.append(content)
                lines.append("</contribution>")

        lines.append("\n</previous_contributions>")

        return "\n".join(lines)

    def _build_structured_output_instructions(
        self,
        agent_blueprint: Dict[str, Any],
        workshop_config: Dict[str, Any],
        round_number: int,
    ) -> str:
        """
        Build structured output instructions for the agent's contribution.

        Args:
            agent_blueprint: The agent's configuration/blueprint
            workshop_config: Workshop configuration
            round_number: Current round number

        Returns:
            Structured output instructions string
        """
        agent_name = agent_blueprint.get("name", "Agent")
        output_format = workshop_config.get("output_format", "report")
        num_rounds = workshop_config.get("num_rounds", 1)

        lines = [
            "<instructions>",
            f"You are contributing to this workshop as '{agent_name}'.",
            "",
            "Please provide your contribution following this structure:",
            "",
            f"## {agent_name}'s Analysis",
            "",
            "### Key Observations",
            "- List your main observations and insights",
            "",
            "### Detailed Analysis",
            "- Provide your in-depth analysis from your specialized perspective",
            "",
            "### Recommendations",
            "- Provide specific, actionable recommendations",
            "",
        ]

        if round_number > 1:
            lines.extend([
                "### Response to Previous Contributions",
                "- Address key points raised by other agents",
                "- Note areas of agreement and disagreement",
                "",
            ])

        if round_number == num_rounds and num_rounds > 1:
            lines.extend([
                "### Final Summary",
                "- Synthesize your final position considering all rounds of discussion",
                "",
            ])

        lines.extend([
            "Keep your contribution focused, well-organized, and substantive.",
            "Write in clear, professional prose suitable for compilation into "
            f"a {output_format} format.",
            "</instructions>",
        ])

        return "\n".join(lines)
