"""
Workshop Compiler for AI Team Workspace Feature

Compiles agent contributions from workshop sessions into structured documents.
Supports multiple output formats: report, slides, canvas, and brief.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class WorkshopCompiler:
    """
    Compiler for workshop agent contributions.

    Takes the collected contributions from all agents across all rounds
    and compiles them into a structured output document in the requested format.
    """

    # Supported output formats
    SUPPORTED_FORMATS = {"report", "slides", "canvas", "brief"}

    def compile(self, contributions: List[Dict[str, Any]], config: Dict[str, Any]) -> str:
        """
        Compile contributions into the configured output format.

        Dispatches to the appropriate format-specific compiler method
        based on config["output_format"].

        Args:
            contributions: List of contribution dicts, each with:
                - agent_id (str): ID of the contributing agent
                - agent_name (str): Display name of the contributing agent
                - content (str): The contribution text
                - round_number (int): Which round the contribution was made in
            config: Workshop configuration dict with:
                - topic (str): The workshop topic
                - workshop_type (str): Type of workshop
                - num_rounds (int): Total number of rounds
                - output_format (str): Target format ("report", "slides", "canvas", "brief")
                - facilitation_style (str): Style of facilitation used

        Returns:
            Compiled Markdown document string
        """
        output_format = config.get("output_format", "report")

        if output_format not in self.SUPPORTED_FORMATS:
            logger.warning(
                f"Unsupported output format '{output_format}', falling back to 'report'"
            )
            output_format = "report"

        logger.info(
            f"Compiling {len(contributions)} contributions into '{output_format}' format"
        )

        compiler_map = {
            "report": self.compile_report,
            "slides": self.compile_slides,
            "canvas": self.compile_canvas,
            "brief": self.compile_brief,
        }

        compiler_fn = compiler_map[output_format]
        result = compiler_fn(contributions, config)

        logger.debug(f"Compiled output length: {len(result)} characters")

        return result

    def compile_report(
        self, contributions: List[Dict[str, Any]], config: Dict[str, Any]
    ) -> str:
        """
        Compile contributions into a structured Markdown report.

        Generates a formal report with:
        - Title and metadata
        - Executive Summary section
        - Per-agent analysis sections
        - Key Themes and Consensus Points
        - Action Items and Next Steps
        - If multi-round, evolution of discussion

        Args:
            contributions: List of contribution dicts
            config: Workshop configuration

        Returns:
            Structured Markdown report string
        """
        topic = config.get("topic", "Workshop Discussion")
        workshop_type = config.get("workshop_type", "discussion")
        num_rounds = config.get("num_rounds", 1)
        facilitation_style = config.get("facilitation_style", "structured")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        # Group contributions by agent and by round
        by_agent = self._group_by_agent(contributions)
        by_round = self._group_by_round(contributions)
        agent_names = self._get_ordered_agent_names(contributions)

        sections = []

        # Title
        sections.append(f"# Workshop Report: {topic}")
        sections.append("")
        sections.append(f"**Date:** {timestamp}")
        sections.append(f"**Workshop Type:** {workshop_type}")
        sections.append(f"**Facilitation Style:** {facilitation_style}")
        sections.append(f"**Participants:** {', '.join(agent_names)}")
        sections.append(f"**Rounds:** {num_rounds}")
        sections.append("")
        sections.append("---")
        sections.append("")

        # Executive Summary
        sections.append("## Executive Summary")
        sections.append("")
        sections.append(
            f"This workshop brought together {len(agent_names)} specialist agents "
            f"to collaboratively analyze and discuss: **{topic}**."
        )
        if num_rounds > 1:
            sections.append(
                f"The discussion spanned {num_rounds} rounds, allowing agents to "
                "build on each other's insights and refine their positions over "
                "the course of the session."
            )
        sections.append(
            "The following report compiles all contributions organized by participant, "
            "with synthesis of key themes and actionable recommendations."
        )
        sections.append("")

        # Multi-round evolution (if applicable)
        if num_rounds > 1:
            sections.append("## Discussion Evolution")
            sections.append("")
            for rnd in sorted(by_round.keys()):
                round_contribs = by_round[rnd]
                contributing_agents = [c.get("agent_name", "Unknown") for c in round_contribs]
                sections.append(f"### Round {rnd}")
                sections.append(
                    f"**Contributors:** {', '.join(contributing_agents)}"
                )
                sections.append("")
                for contrib in round_contribs:
                    agent_name = contrib.get("agent_name", "Unknown Agent")
                    content = contrib.get("content", "").strip()
                    # Show a brief summary for the evolution section
                    summary = self._extract_summary(content, max_length=300)
                    sections.append(f"- **{agent_name}:** {summary}")
                sections.append("")

        # Per-agent detailed sections
        sections.append("## Detailed Agent Contributions")
        sections.append("")

        for agent_name in agent_names:
            agent_contribs = by_agent.get(agent_name, [])
            if not agent_contribs:
                continue

            sections.append(f"### {agent_name}")
            sections.append("")

            if num_rounds > 1:
                # Show contributions organized by round
                for contrib in sorted(agent_contribs, key=lambda c: c.get("round_number", 1)):
                    rnd = contrib.get("round_number", 1)
                    content = contrib.get("content", "").strip()
                    sections.append(f"#### Round {rnd}")
                    sections.append("")
                    sections.append(content)
                    sections.append("")
            else:
                # Single round: just show the content
                for contrib in agent_contribs:
                    content = contrib.get("content", "").strip()
                    sections.append(content)
                    sections.append("")

        # Key Themes and Consensus Points
        sections.append("## Key Themes & Consensus Points")
        sections.append("")
        sections.append(
            "The following themes emerged across multiple agent contributions:"
        )
        sections.append("")
        # We note these as placeholders since we compile raw agent output
        # rather than using another LLM call to synthesize
        sections.append(
            "*The themes below are derived from the individual agent contributions above. "
            "Review each agent's analysis for detailed supporting evidence.*"
        )
        sections.append("")
        for i, agent_name in enumerate(agent_names, 1):
            agent_contribs = by_agent.get(agent_name, [])
            # Use the latest round contribution for theme extraction
            if agent_contribs:
                latest = max(agent_contribs, key=lambda c: c.get("round_number", 1))
                summary = self._extract_summary(latest.get("content", ""), max_length=200)
                sections.append(f"{i}. **{agent_name}'s perspective:** {summary}")
        sections.append("")

        # Action Items and Next Steps
        sections.append("## Action Items & Next Steps")
        sections.append("")
        sections.append(
            "Based on the workshop discussion, the following action items are recommended:"
        )
        sections.append("")
        for i, agent_name in enumerate(agent_names, 1):
            sections.append(
                f"{i}. Review and validate **{agent_name}**'s recommendations "
                "for implementation feasibility"
            )
        sections.append(
            f"{len(agent_names) + 1}. Prioritize identified themes and create execution plan"
        )
        sections.append(
            f"{len(agent_names) + 2}. Schedule follow-up session to track progress"
        )
        sections.append("")

        # Footer
        sections.append("---")
        sections.append(
            f"*Report generated automatically from workshop session on {timestamp}*"
        )

        return "\n".join(sections)

    def compile_slides(
        self, contributions: List[Dict[str, Any]], config: Dict[str, Any]
    ) -> str:
        """
        Compile contributions into slide-formatted Markdown.

        Each ## heading becomes a new slide. Structure:
        - Title slide
        - Agenda slide
        - Per-agent contribution slides
        - Summary and next steps slide

        Args:
            contributions: List of contribution dicts
            config: Workshop configuration

        Returns:
            Slide-formatted Markdown string
        """
        topic = config.get("topic", "Workshop Discussion")
        workshop_type = config.get("workshop_type", "discussion")
        num_rounds = config.get("num_rounds", 1)
        timestamp = datetime.utcnow().strftime("%Y-%m-%d")

        by_agent = self._group_by_agent(contributions)
        agent_names = self._get_ordered_agent_names(contributions)

        slides = []

        # Title Slide
        slides.append(f"## {topic}")
        slides.append("")
        slides.append(f"**Workshop Type:** {workshop_type}")
        slides.append(f"**Date:** {timestamp}")
        slides.append(f"**Participants:** {len(agent_names)} agents")
        if num_rounds > 1:
            slides.append(f"**Rounds:** {num_rounds}")
        slides.append("")

        # Agenda Slide
        slides.append("## Agenda")
        slides.append("")
        for i, agent_name in enumerate(agent_names, 1):
            slides.append(f"{i}. {agent_name}'s Analysis")
        slides.append(f"{len(agent_names) + 1}. Key Takeaways")
        slides.append(f"{len(agent_names) + 2}. Next Steps")
        slides.append("")

        # Per-agent slides
        for agent_name in agent_names:
            agent_contribs = by_agent.get(agent_name, [])
            if not agent_contribs:
                continue

            # Use the latest contribution (final round) for slides
            latest = max(agent_contribs, key=lambda c: c.get("round_number", 1))
            content = latest.get("content", "").strip()

            slides.append(f"## {agent_name}")
            slides.append("")

            # Extract key bullet points from content
            bullet_points = self._extract_bullet_points(content, max_points=6)
            for point in bullet_points:
                slides.append(f"- {point}")
            slides.append("")

            # If multi-round, add a mini evolution note
            if num_rounds > 1 and len(agent_contribs) > 1:
                slides.append(f"*Refined across {len(agent_contribs)} rounds of discussion*")
                slides.append("")

        # Key Takeaways Slide
        slides.append("## Key Takeaways")
        slides.append("")
        for agent_name in agent_names:
            agent_contribs = by_agent.get(agent_name, [])
            if agent_contribs:
                latest = max(agent_contribs, key=lambda c: c.get("round_number", 1))
                summary = self._extract_summary(latest.get("content", ""), max_length=150)
                slides.append(f"- **{agent_name}:** {summary}")
        slides.append("")

        # Next Steps Slide
        slides.append("## Next Steps")
        slides.append("")
        slides.append("- Review workshop findings with stakeholders")
        slides.append("- Prioritize recommendations by impact and effort")
        slides.append("- Assign ownership for top action items")
        slides.append("- Schedule follow-up review session")
        slides.append("")

        # Thank You Slide
        slides.append("## Thank You")
        slides.append("")
        slides.append(f"Workshop: {topic}")
        slides.append(f"Generated: {timestamp}")
        slides.append("")

        return "\n".join(slides)

    def compile_canvas(
        self, contributions: List[Dict[str, Any]], config: Dict[str, Any]
    ) -> str:
        """
        Compile contributions into a business canvas format (BMC-style grid in Markdown).

        Maps agent contributions to canvas sections based on agent category/role.
        Uses a table-based layout for the canvas grid.

        Args:
            contributions: List of contribution dicts
            config: Workshop configuration

        Returns:
            Canvas-formatted Markdown string
        """
        topic = config.get("topic", "Workshop Discussion")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        by_agent = self._group_by_agent(contributions)
        agent_names = self._get_ordered_agent_names(contributions)

        # Define canvas sections (Business Model Canvas style)
        canvas_sections = [
            ("Key Partners", "Who are the key partners and suppliers?"),
            ("Key Activities", "What are the most important activities?"),
            ("Key Resources", "What key resources does the value proposition require?"),
            ("Value Propositions", "What value do we deliver to the customer?"),
            ("Customer Relationships", "What type of relationship does each segment expect?"),
            ("Channels", "Through which channels do our segments want to be reached?"),
            ("Customer Segments", "For whom are we creating value?"),
            ("Cost Structure", "What are the most important costs inherent to our model?"),
            ("Revenue Streams", "For what value are our customers willing to pay?"),
        ]

        sections = []

        # Title
        sections.append(f"# Business Canvas: {topic}")
        sections.append("")
        sections.append(f"**Date:** {timestamp}")
        sections.append(f"**Contributors:** {', '.join(agent_names)}")
        sections.append("")
        sections.append("---")
        sections.append("")

        # Canvas grid (rendered as sections since Markdown tables are limited)
        sections.append("## Canvas Overview")
        sections.append("")

        for section_name, section_question in canvas_sections:
            sections.append(f"### {section_name}")
            sections.append(f"*{section_question}*")
            sections.append("")

            # Collect relevant points from all agents
            has_content = False
            for agent_name in agent_names:
                agent_contribs = by_agent.get(agent_name, [])
                if agent_contribs:
                    latest = max(
                        agent_contribs, key=lambda c: c.get("round_number", 1)
                    )
                    content = latest.get("content", "")
                    # Extract a brief contribution mapped to this canvas section
                    relevant = self._extract_summary(content, max_length=200)
                    if relevant:
                        sections.append(f"- **{agent_name}:** {relevant}")
                        has_content = True

            if not has_content:
                sections.append("- *No specific input captured for this section*")

            sections.append("")

        # Agent Contributions Detail
        sections.append("---")
        sections.append("")
        sections.append("## Detailed Agent Contributions")
        sections.append("")

        for agent_name in agent_names:
            agent_contribs = by_agent.get(agent_name, [])
            if not agent_contribs:
                continue

            sections.append(f"### {agent_name}")
            sections.append("")

            latest = max(agent_contribs, key=lambda c: c.get("round_number", 1))
            content = latest.get("content", "").strip()
            sections.append(content)
            sections.append("")

        # Footer
        sections.append("---")
        sections.append(
            f"*Canvas generated from workshop session on {timestamp}*"
        )

        return "\n".join(sections)

    def compile_brief(
        self, contributions: List[Dict[str, Any]], config: Dict[str, Any]
    ) -> str:
        """
        Compile contributions into a short executive brief (1-2 pages max).

        Focuses on concise, decision-ready output with only the most
        essential insights and recommendations.

        Args:
            contributions: List of contribution dicts
            config: Workshop configuration

        Returns:
            Brief-formatted Markdown string
        """
        topic = config.get("topic", "Workshop Discussion")
        workshop_type = config.get("workshop_type", "discussion")
        num_rounds = config.get("num_rounds", 1)
        timestamp = datetime.utcnow().strftime("%Y-%m-%d")

        by_agent = self._group_by_agent(contributions)
        agent_names = self._get_ordered_agent_names(contributions)

        sections = []

        # Title
        sections.append(f"# Executive Brief: {topic}")
        sections.append("")
        sections.append(f"**Date:** {timestamp} | **Type:** {workshop_type} | "
                        f"**Participants:** {len(agent_names)}")
        sections.append("")
        sections.append("---")
        sections.append("")

        # Overview (2-3 sentences)
        sections.append("## Overview")
        sections.append("")
        sections.append(
            f"A {workshop_type} workshop was conducted with {len(agent_names)} "
            f"specialist agents on the topic of **{topic}**."
        )
        if num_rounds > 1:
            sections.append(
                f"The discussion was conducted over {num_rounds} rounds to allow "
                "iterative refinement of positions and consensus building."
            )
        sections.append("")

        # Key Findings (one bullet per agent)
        sections.append("## Key Findings")
        sections.append("")
        for agent_name in agent_names:
            agent_contribs = by_agent.get(agent_name, [])
            if agent_contribs:
                latest = max(
                    agent_contribs, key=lambda c: c.get("round_number", 1)
                )
                summary = self._extract_summary(
                    latest.get("content", ""), max_length=250
                )
                sections.append(f"- **{agent_name}:** {summary}")
        sections.append("")

        # Recommendations (concise)
        sections.append("## Recommendations")
        sections.append("")
        sections.append("Based on the collective analysis:")
        sections.append("")
        sections.append("1. **Immediate Actions:** Review and validate the specialist "
                        "recommendations against current constraints")
        sections.append("2. **Short-term:** Develop implementation plan for high-impact, "
                        "low-effort items identified")
        sections.append("3. **Medium-term:** Address strategic themes that require "
                        "cross-functional coordination")
        sections.append("")

        # Decision Required
        sections.append("## Decision Required")
        sections.append("")
        sections.append(
            "Stakeholders should review the detailed agent contributions and "
            "determine priority order for the recommended action items."
        )
        sections.append("")

        # Footer
        sections.append("---")
        sections.append(f"*Brief generated on {timestamp}*")

        return "\n".join(sections)

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _group_by_agent(
        self, contributions: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group contributions by agent name.

        Args:
            contributions: List of contribution dicts

        Returns:
            Dict mapping agent_name to list of contributions
        """
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for contrib in contributions:
            agent_name = contrib.get("agent_name", "Unknown Agent")
            if agent_name not in grouped:
                grouped[agent_name] = []
            grouped[agent_name].append(contrib)
        return grouped

    def _group_by_round(
        self, contributions: List[Dict[str, Any]]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Group contributions by round number.

        Args:
            contributions: List of contribution dicts

        Returns:
            Dict mapping round_number to list of contributions
        """
        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for contrib in contributions:
            rnd = contrib.get("round_number", 1)
            if rnd not in grouped:
                grouped[rnd] = []
            grouped[rnd].append(contrib)
        return grouped

    def _get_ordered_agent_names(
        self, contributions: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Get agent names in order of first appearance.

        Args:
            contributions: List of contribution dicts

        Returns:
            Ordered list of unique agent names
        """
        seen = set()
        ordered = []
        for contrib in contributions:
            name = contrib.get("agent_name", "Unknown Agent")
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered

    def _extract_summary(self, content: str, max_length: int = 200) -> str:
        """
        Extract a brief summary from content.

        Takes the first meaningful sentence(s) up to max_length characters.

        Args:
            content: Full content text
            max_length: Maximum summary length

        Returns:
            Summary string
        """
        if not content:
            return ""

        # Clean up content: remove Markdown headings for summary
        lines = content.strip().split("\n")
        text_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip empty lines, headings, and horizontal rules
            if not stripped or stripped.startswith("#") or stripped.startswith("---"):
                continue
            # Skip bullet markers at start but keep the text
            if stripped.startswith("- ") or stripped.startswith("* "):
                stripped = stripped[2:]
            text_lines.append(stripped)

        combined = " ".join(text_lines)

        if len(combined) <= max_length:
            return combined

        # Truncate at word boundary
        truncated = combined[:max_length]
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.5:
            truncated = truncated[:last_space]

        return truncated + "..."

    def _extract_bullet_points(
        self, content: str, max_points: int = 6
    ) -> List[str]:
        """
        Extract key bullet points from content.

        Looks for existing bullet points or extracts first sentences
        from paragraphs.

        Args:
            content: Full content text
            max_points: Maximum number of bullet points to extract

        Returns:
            List of bullet point strings
        """
        if not content:
            return ["No content provided"]

        points = []
        lines = content.strip().split("\n")

        for line in lines:
            stripped = line.strip()

            # Extract existing bullet points
            if stripped.startswith("- ") or stripped.startswith("* "):
                point_text = stripped[2:].strip()
                if point_text and len(point_text) > 10:
                    # Truncate long bullet points for slides
                    if len(point_text) > 120:
                        point_text = point_text[:120] + "..."
                    points.append(point_text)

            # Extract numbered points
            elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".)" :
                point_text = stripped[2:].strip()
                if point_text and len(point_text) > 10:
                    if len(point_text) > 120:
                        point_text = point_text[:120] + "..."
                    points.append(point_text)

            if len(points) >= max_points:
                break

        # If no bullet points found, extract from paragraphs
        if not points:
            for line in lines:
                stripped = line.strip()
                # Skip headings and empty lines
                if not stripped or stripped.startswith("#") or stripped.startswith("---"):
                    continue
                # Take first sentence or truncate
                sentence = stripped.split(". ")[0]
                if len(sentence) > 10:
                    if len(sentence) > 120:
                        sentence = sentence[:120] + "..."
                    points.append(sentence)
                if len(points) >= max_points:
                    break

        if not points:
            points.append("See detailed contribution for full analysis")

        return points


# Create singleton instance
workshop_compiler = WorkshopCompiler()
