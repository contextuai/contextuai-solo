"""
Agent Library Service for AI Team Workspace

Reads .md files from the agent library directory, parses them into structured
catalog entries, and provides import/sync functionality to persist agents
into MongoDB. Each .md file represents a complete agent definition with
expertise areas, frameworks, and behavioral guidelines.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AgentLibraryService:
    """
    Service for browsing, searching, importing, and syncing agents from
    the on-disk markdown library into the workspace_agents MongoDB collection.
    """

    # Resolve the library path.
    # In Docker: /projects is mounted from repo root's projects/ directory.
    # Locally:   go up three levels from this file to reach the repo root.
    LIBRARY_PATH = os.getenv(
        "AGENT_LIBRARY_PATH",
        os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__))
                    )
                )
            ),
            "projects",
            "agent-library",
            "agents",
        )
    )

    # Maps directory folder names to AgentCategory enum values
    CATEGORY_MAP: Dict[str, str] = {
        "c-suite": "c_suite",
        "engineering": "engineering",
        "design-ux": "design",
        "marketing-sales": "marketing_sales",
        "product-management": "product_management",
        "startup-venture": "startup_venture",
        "finance-operations": "finance_operations",
        "legal-compliance": "legal_compliance",
        "data-analytics": "data_analytics",
        "it-security": "it_security",
        "hr-people": "hr_people",
        "social-engagement": "social_engagement",
        "specialized": "specialized",
    }

    # Reverse map: enum value -> folder name (built once)
    REVERSE_CATEGORY_MAP: Dict[str, str] = {v: k for k, v in CATEGORY_MAP.items()}

    # Category display labels used in catalog responses
    CATEGORY_LABELS: Dict[str, str] = {
        "c_suite": "C-Suite",
        "engineering": "Engineering",
        "design": "Design & UX",
        "marketing_sales": "Marketing & Sales",
        "product_management": "Product Management",
        "startup_venture": "Startup & Venture",
        "finance_operations": "Finance & Operations",
        "legal_compliance": "Legal & Compliance",
        "data_analytics": "Data & Analytics",
        "it_security": "IT & Security",
        "hr_people": "HR & People",
        "social_engagement": "Social Engagement",
        "specialized": "Specialized",
    }

    # =========================================================================
    # Markdown Parsing
    # =========================================================================

    def parse_agent_md(self, file_path: str) -> Dict[str, Any]:
        """
        Read a .md file and extract structured agent data.

        Parsing rules:
        - The first H1 (``# Title``) becomes the agent *name*.
        - The first non-empty paragraph after the H1 (before any H2)
          becomes the *description*.
        - Each ``## Section`` heading starts a new section whose body is
          captured verbatim.
        - The ``Thinking Frameworks`` / ``Frameworks & Methodologies`` /
          ``Frameworks`` section is parsed for bullet-point entries to
          populate the *frameworks* list.
        - Capabilities are extracted from ``Core Expertise`` bullet headers.
        - The entire raw markdown content becomes *full_content* (used as
          the agent system prompt).

        Args:
            file_path: Absolute or relative path to the .md file.

        Returns:
            Dictionary with keys: slug, name, category, description,
            frameworks, capabilities, sections, full_content, file_path.

        Raises:
            FileNotFoundError: If the .md file does not exist.
            ValueError: If the file cannot be parsed (e.g. missing H1).
        """
        file_path = os.path.abspath(file_path)
        logger.debug(f"Parsing agent markdown: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # --- Derive slug from filename ---
        slug = Path(file_path).stem  # e.g. "ceo" from "ceo.md"

        # --- Derive category from parent directory name ---
        parent_dir = Path(file_path).parent.name
        category = self.CATEGORY_MAP.get(parent_dir, parent_dir)

        # --- Extract name from first H1 ---
        name_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if not name_match:
            raise ValueError(f"No H1 heading found in {file_path}")
        name = name_match.group(1).strip()

        # --- Extract description (first paragraph after H1, before any ##) ---
        description = ""
        after_h1 = content[name_match.end():]
        # Find everything between the H1 and the first ## heading
        desc_match = re.match(r"(.*?)(?=^##\s|\Z)", after_h1, re.DOTALL | re.MULTILINE)
        if desc_match:
            raw_desc = desc_match.group(1).strip()
            # The description is the first non-empty paragraph
            paragraphs = [p.strip() for p in raw_desc.split("\n\n") if p.strip()]
            if paragraphs:
                # Collapse newlines within the paragraph
                description = re.sub(r"\s+", " ", paragraphs[0])

        # --- Parse ## sections ---
        sections: Dict[str, str] = {}
        section_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
        section_starts = list(section_pattern.finditer(content))

        for i, match in enumerate(section_starts):
            section_name = match.group(1).strip()
            start = match.end()
            end = section_starts[i + 1].start() if i + 1 < len(section_starts) else len(content)
            section_body = content[start:end].strip()
            sections[section_name] = section_body

        # --- Extract frameworks ---
        frameworks = self._extract_frameworks(sections)

        # --- Extract capabilities from Core Expertise section ---
        capabilities = self._extract_capabilities(sections)

        return {
            "slug": slug,
            "name": name,
            "category": category,
            "description": description,
            "frameworks": frameworks,
            "capabilities": capabilities,
            "sections": sections,
            "full_content": content,
            "file_path": file_path,
        }

    # =========================================================================
    # Catalog & Detail
    # =========================================================================

    async def get_catalog(self, category: Optional[str] = None) -> Dict[str, Any]:
        """
        Read all .md files from the library and return lightweight catalog
        entries suitable for browsing.

        Args:
            category: Optional category enum value (e.g. ``"c_suite"``) to
                filter by.  If ``None``, all categories are returned.

        Returns:
            Dictionary with keys:
            - agents: list of catalog entry dicts
            - total_count: int
            - categories: dict mapping category -> count
        """
        agents: List[Dict[str, Any]] = []
        categories: Dict[str, int] = {}
        library = Path(self.LIBRARY_PATH)

        if not library.exists():
            logger.warning(f"Agent library path does not exist: {self.LIBRARY_PATH}")
            return {"agents": [], "total_count": 0, "categories": {}}

        for category_dir in sorted(library.iterdir()):
            if not category_dir.is_dir():
                continue

            folder_name = category_dir.name
            cat_enum = self.CATEGORY_MAP.get(folder_name)
            if cat_enum is None:
                logger.warning(f"Unknown category folder: {folder_name}")
                continue

            # If a category filter is specified, skip non-matching categories
            if category and cat_enum != category:
                continue

            md_files = sorted(category_dir.glob("*.md"))
            categories[cat_enum] = len(md_files)

            for md_file in md_files:
                try:
                    parsed = self.parse_agent_md(str(md_file))
                    agents.append({
                        "slug": parsed["slug"],
                        "name": parsed["name"],
                        "category": parsed["category"],
                        "description": parsed["description"],
                        "frameworks": parsed["frameworks"],
                        "capabilities": parsed["capabilities"],
                        "file_path": str(md_file),
                    })
                except Exception as e:
                    logger.error(f"Failed to parse {md_file}: {e}")

        return {
            "agents": agents,
            "total_count": len(agents),
            "categories": categories,
        }

    async def get_agent_detail(self, category: str, slug: str) -> Dict[str, Any]:
        """
        Read a specific .md file and return the full parsed content including
        all sections and the raw markdown.

        Args:
            category: Category enum value (e.g. ``"c_suite"``).
            slug: Agent slug derived from the filename (e.g. ``"ceo"``).

        Returns:
            Full parsed data dict (same structure as ``parse_agent_md``).

        Raises:
            FileNotFoundError: If the .md file does not exist.
        """
        folder_name = self.REVERSE_CATEGORY_MAP.get(category)
        if not folder_name:
            raise FileNotFoundError(
                f"No folder mapping for category '{category}'"
            )

        file_path = os.path.join(self.LIBRARY_PATH, folder_name, f"{slug}.md")
        if not os.path.isfile(file_path):
            raise FileNotFoundError(
                f"Agent file not found: {file_path}"
            )

        return self.parse_agent_md(file_path)

    # =========================================================================
    # Import
    # =========================================================================

    async def import_agent(
        self,
        category: str,
        slug: str,
        user_id: str,
        agent_repo,
    ) -> Dict[str, Any]:
        """
        Parse a .md file and upsert the agent into the ``workspace_agents``
        MongoDB collection.

        If the agent already exists (matched by ``agent_id == slug``):
        - If its ``source`` is ``"admin_edit"``, the import is skipped so that
          manual admin edits are preserved.
        - Otherwise the document is updated in place.

        If the agent does not exist it is created fresh.

        Args:
            category: Category enum value.
            slug: Agent slug (filename without ``.md``).
            user_id: ID of the user performing the import.
            agent_repo: ``WorkspaceAgentRepository`` instance.

        Returns:
            The agent document dict as stored in MongoDB.
        """
        detail = await self.get_agent_detail(category, slug)
        now = datetime.utcnow().isoformat()

        # Check if agent already exists
        existing = await agent_repo.get_one({"agent_id": slug})

        if existing:
            # Preserve manually-edited agents
            if existing.get("source") == "admin_edit":
                logger.info(
                    f"Skipping import of '{slug}' -- source is 'admin_edit'"
                )
                return existing

            # Update the existing document
            update_data = {
                "name": detail["name"],
                "description": detail["description"],
                "category": detail["category"],
                "capabilities": detail["capabilities"],
                "system_prompt": detail["full_content"],
                "frameworks": detail["frameworks"],
                "sections": detail["sections"],
                "source": "library",
                "is_system": True,
                "updated_at": now,
            }
            updated = await agent_repo.update(slug, update_data)
            if updated:
                logger.info(f"Updated library agent: {slug}")
                return updated
            else:
                logger.warning(f"Failed to update agent: {slug}")
                return existing
        else:
            # Create a new agent document
            agent_data = {
                "agent_id": slug,
                "name": detail["name"],
                "description": detail["description"],
                "category": detail["category"],
                "capabilities": detail["capabilities"],
                "system_prompt": detail["full_content"],
                "frameworks": detail["frameworks"],
                "sections": detail["sections"],
                "icon": self._suggest_icon(detail["category"]),
                "source": "library",
                "is_system": True,
                "is_active": True,
                "created_by": user_id,
                "estimated_tokens": 2000,
                "estimated_cost_usd": 0.02,
                "usage_count": 0,
                "last_used": None,
                "created_at": now,
                "updated_at": now,
            }

            result = await agent_repo.collection.insert_one(agent_data)
            if result.inserted_id:
                logger.info(f"Created library agent: {slug}")
                # Re-read to get the canonical document with ``id``
                return await agent_repo.get_one({"agent_id": slug}) or agent_data
            else:
                logger.error(f"insert_one returned no inserted_id for: {slug}")
                return agent_data

    async def import_bulk(
        self,
        imports: List[Dict[str, str]],
        user_id: str,
        agent_repo,
    ) -> List[Dict[str, Any]]:
        """
        Import multiple agents at once.

        Each item in *imports* must have ``category`` and ``slug`` keys.

        Args:
            imports: List of dicts with ``category`` and ``slug``.
            user_id: ID of the user performing the import.
            agent_repo: ``WorkspaceAgentRepository`` instance.

        Returns:
            List of imported agent document dicts.
        """
        results: List[Dict[str, Any]] = []
        for item in imports:
            try:
                agent = await self.import_agent(
                    category=item["category"],
                    slug=item["slug"],
                    user_id=user_id,
                    agent_repo=agent_repo,
                )
                results.append(agent)
            except Exception as e:
                logger.error(
                    f"Failed to import {item.get('category')}/{item.get('slug')}: {e}"
                )
                results.append({
                    "slug": item.get("slug", "unknown"),
                    "category": item.get("category", "unknown"),
                    "error": str(e),
                })
        return results

    # =========================================================================
    # Sync
    # =========================================================================

    async def sync_library_to_db(self, agent_repo) -> Dict[str, Any]:
        """
        Re-sync ALL .md files from the library into MongoDB.

        Only agents whose ``source`` is ``"library"`` (or that do not yet
        exist) are written.  Agents with ``source == "admin_edit"`` are
        skipped so that manual changes are preserved.

        Args:
            agent_repo: ``WorkspaceAgentRepository`` instance.

        Returns:
            Dictionary with keys: success, created, updated, skipped, errors.
        """
        logger.info("Starting full library sync to database...")
        catalog = await self.get_catalog()

        created = 0
        updated = 0
        skipped = 0
        errors: List[str] = []

        for entry in catalog["agents"]:
            try:
                existing = await agent_repo.get_one({"agent_id": entry["slug"]})

                if existing and existing.get("source") == "admin_edit":
                    skipped += 1
                    continue

                result = await self.import_agent(
                    category=entry["category"],
                    slug=entry["slug"],
                    user_id="system",
                    agent_repo=agent_repo,
                )

                if existing:
                    updated += 1
                else:
                    created += 1

            except Exception as e:
                error_msg = f"{entry['category']}/{entry['slug']}: {e}"
                logger.error(f"Sync error -- {error_msg}")
                errors.append(error_msg)

        success = len(errors) == 0
        logger.info(
            f"Library sync complete: created={created}, updated={updated}, "
            f"skipped={skipped}, errors={len(errors)}"
        )

        return {
            "success": success,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        }

    # =========================================================================
    # Search
    # =========================================================================

    async def search_catalog(self, query: str) -> Dict[str, Any]:
        """
        Full-text search across agent names, descriptions, and capabilities.

        The search is case-insensitive and matches any agent where at least
        one of the search terms appears in the name, description, or
        capabilities list.

        Args:
            query: Free-text search string.

        Returns:
            Same structure as ``get_catalog`` but filtered to matching agents.
        """
        catalog = await self.get_catalog()
        if not query or not query.strip():
            return catalog

        terms = query.lower().split()
        matched: List[Dict[str, Any]] = []
        categories: Dict[str, int] = {}

        for agent in catalog["agents"]:
            searchable = " ".join([
                agent.get("name", ""),
                agent.get("description", ""),
                " ".join(agent.get("capabilities", [])),
                " ".join(agent.get("frameworks", [])),
            ]).lower()

            if any(term in searchable for term in terms):
                matched.append(agent)
                cat = agent.get("category", "unknown")
                categories[cat] = categories.get(cat, 0) + 1

        return {
            "agents": matched,
            "total_count": len(matched),
            "categories": categories,
        }

    # =========================================================================
    # Private Helpers
    # =========================================================================

    @staticmethod
    def _extract_frameworks(sections: Dict[str, str]) -> List[str]:
        """
        Extract framework names from ``Thinking Frameworks``,
        ``Frameworks & Methodologies``, ``Frameworks``, ``Architecture Frameworks``,
        or ``Decision Frameworks`` sections.

        Frameworks are detected as bold text (``**Name**``) at the start of
        bullet points (``- **Name**: ...``).

        Returns:
            List of framework name strings.
        """
        framework_keys = [
            "Thinking Frameworks",
            "Thinking Framework",
            "Frameworks & Methodologies",
            "Frameworks",
            "Architecture Frameworks",
            "Decision Frameworks",
        ]

        frameworks: List[str] = []
        for key in framework_keys:
            body = sections.get(key)
            if not body:
                continue
            # Match lines like: - **Name**: description
            matches = re.findall(r"^[-*]\s+\*\*(.+?)\*\*", body, re.MULTILINE)
            for m in matches:
                cleaned = m.strip().rstrip(":")
                if cleaned and cleaned not in frameworks:
                    frameworks.append(cleaned)

        return frameworks

    @staticmethod
    def _extract_capabilities(sections: Dict[str, str]) -> List[str]:
        """
        Extract capability names from the ``Core Expertise`` section.

        Capabilities are detected as bold text at the start of bullet points
        (``- **Capability Name**: ...``).

        Returns:
            List of capability name strings.
        """
        capability_keys = [
            "Core Expertise",
            "Key Metrics & Focus Areas",
            "Tools & Platforms",
        ]

        capabilities: List[str] = []
        for key in capability_keys:
            body = sections.get(key)
            if not body:
                continue
            # Match lines like: - **Capability Name**: ...
            matches = re.findall(r"^[-*]\s+\*\*(.+?)\*\*", body, re.MULTILINE)
            for m in matches:
                cleaned = m.strip().rstrip(":")
                if cleaned and cleaned not in capabilities:
                    capabilities.append(cleaned)

        return capabilities

    @staticmethod
    def _suggest_icon(category: str) -> str:
        """
        Suggest a default icon identifier based on agent category.

        Args:
            category: AgentCategory enum value string.

        Returns:
            Icon identifier string.
        """
        icon_map: Dict[str, str] = {
            "c_suite": "crown",
            "engineering": "code",
            "design": "layout",
            "marketing_sales": "trending-up",
            "product_management": "clipboard",
            "startup_venture": "rocket",
            "finance_operations": "dollar-sign",
            "legal_compliance": "shield",
            "data_analytics": "bar-chart-2",
            "it_security": "lock",
            "hr_people": "users",
            "social_engagement": "message-circle",
            "specialized": "star",
        }
        return icon_map.get(category, "bot")
