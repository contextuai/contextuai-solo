"""
Blueprint Library Service

Reads .md files from the blueprints directory, parses them into structured
catalog entries, and provides sync functionality to persist blueprints
into the database. Mirrors the AgentLibraryService pattern.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class BlueprintLibraryService:
    """
    Service for browsing, searching, and syncing blueprints from
    the on-disk markdown library into the blueprints collection.
    """

    LIBRARY_PATH = os.getenv(
        "BLUEPRINT_LIBRARY_PATH",
        os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )
            ),
            "blueprints",
        )
    )

    CATEGORY_MAP: Dict[str, str] = {
        "strategy": "strategy",
        "product": "product",
        "marketing": "marketing",
        "content": "content",
        "research": "research",
        "operations": "operations",
        "general": "general",
    }

    CATEGORY_LABELS: Dict[str, str] = {
        "strategy": "Strategy",
        "product": "Product",
        "marketing": "Marketing",
        "content": "Content",
        "research": "Research",
        "operations": "Operations",
        "general": "General",
    }

    # =========================================================================
    # Markdown Parsing
    # =========================================================================

    def parse_blueprint_md(self, file_path: str) -> Dict[str, Any]:
        """
        Read a .md file and extract structured blueprint data.

        Parsing rules:
        - The first H1 becomes the blueprint *name*.
        - The first non-empty paragraph after the H1 becomes the *description*.
        - Each ## heading starts a new section.
        - Tags are extracted from a "Tags" section (comma-separated).
        - Recommended agents from "Recommended Agents" section (comma or bullet list).
        - The entire raw markdown content becomes *full_content*.
        """
        file_path = os.path.abspath(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        slug = Path(file_path).stem
        parent_dir = Path(file_path).parent.name
        category = self.CATEGORY_MAP.get(parent_dir, parent_dir)

        # Extract name from first H1
        name_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if not name_match:
            raise ValueError(f"No H1 heading found in {file_path}")
        name = name_match.group(1).strip()

        # Extract description (first paragraph after H1, before any ##)
        description = ""
        after_h1 = content[name_match.end():]
        desc_match = re.match(r"(.*?)(?=^##\s|\Z)", after_h1, re.DOTALL | re.MULTILINE)
        if desc_match:
            raw_desc = desc_match.group(1).strip()
            paragraphs = [p.strip() for p in raw_desc.split("\n\n") if p.strip()]
            if paragraphs:
                description = re.sub(r"\s+", " ", paragraphs[0])

        # Parse ## sections
        sections: Dict[str, str] = {}
        section_pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
        section_starts = list(section_pattern.finditer(content))

        for i, match in enumerate(section_starts):
            section_name = match.group(1).strip()
            start = match.end()
            end = section_starts[i + 1].start() if i + 1 < len(section_starts) else len(content)
            section_body = content[start:end].strip()
            sections[section_name] = section_body

        # Extract tags
        tags = self._extract_tags(sections)

        # Extract recommended agents
        recommended_agents = self._extract_recommended_agents(sections)

        return {
            "slug": slug,
            "name": name,
            "category": category,
            "description": description,
            "sections": sections,
            "tags": tags,
            "recommended_agents": recommended_agents,
            "full_content": content,
            "file_path": file_path,
        }

    def _extract_tags(self, sections: Dict[str, str]) -> List[str]:
        """Extract tags from a Tags section."""
        for key in ("Tags", "tags"):
            if key in sections:
                raw = sections[key].strip()
                # Handle comma-separated or bullet list
                if "," in raw:
                    return [t.strip().lower() for t in raw.split(",") if t.strip()]
                return [
                    line.lstrip("- *").strip().lower()
                    for line in raw.split("\n")
                    if line.strip() and not line.startswith("#")
                ]
        return []

    def _extract_recommended_agents(self, sections: Dict[str, str]) -> List[str]:
        """Extract recommended agents from a Recommended Agents section."""
        for key in ("Recommended Agents", "recommended_agents", "Agents"):
            if key in sections:
                raw = sections[key].strip()
                agents = []
                for line in raw.split("\n"):
                    line = line.lstrip("- *").strip()
                    if not line or line.startswith("#"):
                        continue
                    # Handle comma-separated on a single line
                    if "," in line:
                        agents.extend(t.strip() for t in line.split(",") if t.strip())
                    else:
                        agents.append(line)
                return agents
        return []

    # =========================================================================
    # Catalog & Detail
    # =========================================================================

    async def get_catalog(self, category: Optional[str] = None) -> Dict[str, Any]:
        """
        Read all .md files from the library and return lightweight catalog entries.
        """
        blueprints: List[Dict[str, Any]] = []
        categories: Dict[str, int] = {}
        library = Path(self.LIBRARY_PATH)

        if not library.exists():
            logger.warning("Blueprint library not found at %s", library)
            return {"blueprints": [], "total_count": 0, "categories": {}}

        for category_dir in sorted(library.iterdir()):
            if not category_dir.is_dir():
                continue

            folder_name = category_dir.name
            cat = self.CATEGORY_MAP.get(folder_name, folder_name)

            for md_file in sorted(category_dir.glob("*.md")):
                try:
                    parsed = self.parse_blueprint_md(str(md_file))
                    categories[cat] = categories.get(cat, 0) + 1

                    if category and cat != category:
                        continue

                    blueprints.append({
                        "slug": parsed["slug"],
                        "name": parsed["name"],
                        "category": cat,
                        "category_label": self.CATEGORY_LABELS.get(cat, cat),
                        "description": parsed["description"][:500],
                        "tags": parsed["tags"],
                        "recommended_agents": parsed["recommended_agents"],
                    })
                except Exception:
                    logger.warning("Failed to parse blueprint: %s", md_file.name, exc_info=True)

        return {
            "blueprints": blueprints,
            "total_count": len(blueprints),
            "categories": categories,
        }

    async def search_catalog(self, query: str) -> Dict[str, Any]:
        """Full-text search over blueprint files."""
        query_lower = query.lower()
        results: List[Dict[str, Any]] = []
        library = Path(self.LIBRARY_PATH)

        if not library.exists():
            return {"blueprints": [], "total_count": 0}

        for category_dir in sorted(library.iterdir()):
            if not category_dir.is_dir():
                continue

            for md_file in sorted(category_dir.glob("*.md")):
                try:
                    parsed = self.parse_blueprint_md(str(md_file))
                    searchable = f"{parsed['name']} {parsed['description']} {' '.join(parsed['tags'])}".lower()
                    if query_lower in searchable:
                        cat = parsed["category"]
                        results.append({
                            "slug": parsed["slug"],
                            "name": parsed["name"],
                            "category": cat,
                            "category_label": self.CATEGORY_LABELS.get(cat, cat),
                            "description": parsed["description"][:500],
                            "tags": parsed["tags"],
                            "recommended_agents": parsed["recommended_agents"],
                        })
                except Exception:
                    logger.warning("Failed to parse blueprint: %s", md_file.name, exc_info=True)

        return {"blueprints": results, "total_count": len(results)}

    async def get_detail(self, category: str, slug: str) -> Optional[Dict[str, Any]]:
        """Get full parsed content for a specific blueprint file."""
        # Resolve folder name from category enum value
        folder = category  # categories map 1:1 with folder names
        library = Path(self.LIBRARY_PATH)
        file_path = library / folder / f"{slug}.md"

        if not file_path.exists():
            return None

        return self.parse_blueprint_md(str(file_path))

    # =========================================================================
    # Sync to DB
    # =========================================================================

    async def sync_library_to_db(self, collection) -> int:
        """
        Scan all .md files and upsert into the blueprints collection.

        Returns the number of newly seeded blueprints.
        """
        library = Path(self.LIBRARY_PATH)
        if not library.exists():
            logger.warning("Blueprint library not found at %s — skipping sync", library)
            return 0

        seeded = 0
        for category_dir in sorted(library.iterdir()):
            if not category_dir.is_dir():
                continue

            folder_name = category_dir.name
            category = self.CATEGORY_MAP.get(folder_name, folder_name)

            for md_file in sorted(category_dir.glob("*.md")):
                try:
                    parsed = self.parse_blueprint_md(str(md_file))
                    blueprint_id = f"{category}-{parsed['slug']}"

                    existing = await collection.find_one({"_id": blueprint_id})
                    if existing is not None:
                        continue

                    doc = {
                        "_id": blueprint_id,
                        "blueprint_id": blueprint_id,
                        "name": parsed["name"],
                        "slug": parsed["slug"],
                        "description": parsed["description"][:500],
                        "category": category,
                        "category_label": self.CATEGORY_LABELS.get(category, category),
                        "content": parsed["full_content"],
                        "sections": parsed["sections"],
                        "tags": parsed["tags"],
                        "recommended_agents": parsed["recommended_agents"],
                        "source": "library",
                        "is_system": True,
                        "usage_count": 0,
                        "created_by": "system",
                        "deleted_at": None,
                        "created_at": datetime.utcnow().isoformat() + "Z",
                    }

                    await collection.insert_one(doc)
                    seeded += 1
                except Exception:
                    logger.warning("Failed to sync blueprint: %s", md_file.name, exc_info=True)

        return seeded
