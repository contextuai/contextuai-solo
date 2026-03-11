"""
Template Service for AI Team Workspace Feature

Provides business logic for managing workspace templates,
including system templates, user templates, and project-to-template conversion.
"""

import logging
from typing import Dict, Any, List, Optional

from repositories.workspace_template_repository import WorkspaceTemplateRepository
from repositories.workspace_agent_repository import WorkspaceAgentRepository

# Configure logging
logger = logging.getLogger(__name__)


class TemplateService:
    """
    Service for workspace template management.

    Provides methods for retrieving templates, resolving agent details,
    and creating templates from projects.
    """

    # Valid template categories
    VALID_CATEGORIES = ["web", "api", "mobile", "data", "ml", "devops", "fullstack", "custom"]

    # Valid complexity levels
    VALID_COMPLEXITY = ["simple", "medium", "complex", "enterprise"]

    async def get_all_templates(
        self,
        user_id: Optional[str],
        template_repo: WorkspaceTemplateRepository
    ) -> List[Dict[str, Any]]:
        """
        Get all available templates (system + user templates).

        Args:
            user_id: Optional user ID to include user-created templates
            template_repo: WorkspaceTemplateRepository instance

        Returns:
            List of template documents
        """
        try:
            templates = await template_repo.get_all_available(user_id)

            # Separate system and user templates for organized response
            system_templates = [t for t in templates if t.get("is_system", False)]
            user_templates = [t for t in templates if not t.get("is_system", False)]

            logger.debug(
                f"Retrieved {len(system_templates)} system templates and "
                f"{len(user_templates)} user templates"
            )

            return templates

        except Exception as e:
            logger.error(f"Error getting templates: {e}")
            return []

    async def get_template_with_agents(
        self,
        template_id: str,
        template_repo: WorkspaceTemplateRepository,
        agent_repo: WorkspaceAgentRepository
    ) -> Optional[Dict[str, Any]]:
        """
        Get template with resolved agent details.

        Args:
            template_id: ID of the template
            template_repo: WorkspaceTemplateRepository instance
            agent_repo: WorkspaceAgentRepository instance

        Returns:
            Template document with 'agents' field containing full agent details,
            or None if template not found
        """
        try:
            # Get template
            template = await template_repo.get_by_id(template_id)
            if not template:
                logger.warning(f"Template not found: {template_id}")
                return None

            # Get agents
            agent_ids = template.get("team_agent_ids", [])
            if agent_ids:
                agents = await agent_repo.get_by_ids(agent_ids)
                template["agents"] = agents

                # Check for missing agents
                found_ids = {a.get("agent_id") for a in agents}
                missing = set(agent_ids) - found_ids
                if missing:
                    template["missing_agents"] = list(missing)
                    logger.warning(f"Template {template_id} references missing agents: {missing}")
            else:
                template["agents"] = []

            logger.debug(f"Retrieved template {template_id} with {len(template['agents'])} agents")

            return template

        except Exception as e:
            logger.error(f"Error getting template with agents: {e}")
            return None

    async def create_template_from_project(
        self,
        project: Dict[str, Any],
        name: str,
        description: str,
        template_repo: WorkspaceTemplateRepository
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new template from an existing project.

        Args:
            project: Project document to create template from
            name: Name for the new template
            description: Description for the new template
            template_repo: WorkspaceTemplateRepository instance

        Returns:
            Created template document or None if creation failed
        """
        try:
            # Validate project has required fields
            if not project:
                logger.error("Cannot create template from empty project")
                return None

            # Extract template data from project
            tech_stack = project.get("tech_stack", [])
            complexity = project.get("complexity", "medium")
            team_agent_ids = project.get("team_agent_ids", [])
            user_id = project.get("user_id")

            # Determine category based on tech stack or project config
            category = self._infer_category(tech_stack, project.get("config", {}))

            # Build config from project
            config = {
                "source_project_id": project.get("project_id"),
                "original_name": project.get("name"),
                **project.get("config", {})
            }

            # Create the template
            template = await template_repo.create(
                name=name,
                description=description,
                category=category,
                tech_stack=tech_stack,
                complexity=complexity,
                team_agent_ids=team_agent_ids,
                config=config,
                user_id=user_id,
                is_system=False
            )

            logger.info(f"Created template '{name}' from project {project.get('project_id')}")

            return template

        except Exception as e:
            logger.error(f"Error creating template from project: {e}")
            return None

    async def validate_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate template configuration data.

        Args:
            template_data: Template configuration to validate

        Returns:
            Dictionary with 'valid' boolean and 'errors' list
        """
        errors: List[str] = []

        try:
            # Check required fields
            required_fields = ["name", "description", "category", "tech_stack", "complexity", "team_agent_ids"]
            for field in required_fields:
                if field not in template_data or not template_data.get(field):
                    errors.append(f"Missing required field: {field}")

            # Validate name
            name = template_data.get("name", "")
            if name and (len(name) < 3 or len(name) > 100):
                errors.append("Template name must be between 3 and 100 characters")

            # Validate description
            description = template_data.get("description", "")
            if description and len(description) > 1000:
                errors.append("Description must not exceed 1000 characters")

            # Validate category
            category = template_data.get("category", "")
            if category and category not in self.VALID_CATEGORIES:
                errors.append(f"Invalid category. Must be one of: {', '.join(self.VALID_CATEGORIES)}")

            # Validate complexity
            complexity = template_data.get("complexity", "")
            if complexity and complexity not in self.VALID_COMPLEXITY:
                errors.append(f"Invalid complexity. Must be one of: {', '.join(self.VALID_COMPLEXITY)}")

            # Validate tech stack
            tech_stack = template_data.get("tech_stack", [])
            if tech_stack and not isinstance(tech_stack, list):
                errors.append("tech_stack must be a list")
            elif tech_stack and len(tech_stack) > 20:
                errors.append("tech_stack cannot exceed 20 items")

            # Validate team agent IDs
            team_agent_ids = template_data.get("team_agent_ids", [])
            if team_agent_ids:
                if not isinstance(team_agent_ids, list):
                    errors.append("team_agent_ids must be a list")
                elif len(team_agent_ids) == 0:
                    errors.append("Template must include at least one agent")
                elif len(team_agent_ids) > 10:
                    errors.append("Template cannot exceed 10 agents")
                elif len(team_agent_ids) != len(set(team_agent_ids)):
                    errors.append("Duplicate agents in team_agent_ids")

            logger.debug(f"Template validation result: valid={len(errors) == 0}")

            return {
                "valid": len(errors) == 0,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"Error validating template: {e}")
            return {
                "valid": False,
                "errors": [f"Validation error: {str(e)}"]
            }

    async def get_templates_by_category(
        self,
        category: str,
        user_id: Optional[str],
        template_repo: WorkspaceTemplateRepository
    ) -> List[Dict[str, Any]]:
        """
        Get templates filtered by category.

        Args:
            category: Template category to filter by
            user_id: Optional user ID to include user templates
            template_repo: WorkspaceTemplateRepository instance

        Returns:
            List of templates in the specified category
        """
        try:
            templates = await template_repo.get_by_category(
                category=category,
                include_system=True,
                user_id=user_id
            )

            logger.debug(f"Retrieved {len(templates)} templates in category '{category}'")

            return templates

        except Exception as e:
            logger.error(f"Error getting templates by category: {e}")
            return []

    async def get_popular_templates(
        self,
        limit: int,
        template_repo: WorkspaceTemplateRepository
    ) -> List[Dict[str, Any]]:
        """
        Get most popular templates by usage count.

        Args:
            limit: Maximum number of templates to return
            template_repo: WorkspaceTemplateRepository instance

        Returns:
            List of popular templates
        """
        try:
            templates = await template_repo.get_popular_templates(limit)
            logger.debug(f"Retrieved {len(templates)} popular templates")
            return templates

        except Exception as e:
            logger.error(f"Error getting popular templates: {e}")
            return []

    async def increment_usage(
        self,
        template_id: str,
        template_repo: WorkspaceTemplateRepository
    ) -> Optional[Dict[str, Any]]:
        """
        Increment template usage count.

        Args:
            template_id: ID of the template
            template_repo: WorkspaceTemplateRepository instance

        Returns:
            Updated template or None
        """
        try:
            result = await template_repo.increment_usage_count(template_id)
            if result:
                logger.debug(f"Incremented usage count for template {template_id}")
            return result

        except Exception as e:
            logger.error(f"Error incrementing template usage: {e}")
            return None

    def _infer_category(self, tech_stack: List[str], config: Dict[str, Any]) -> str:
        """
        Infer template category from tech stack.

        Args:
            tech_stack: List of technologies
            config: Project configuration

        Returns:
            Inferred category string
        """
        # Check config for explicit category
        if config.get("category"):
            return config["category"]

        tech_stack_lower = [t.lower() for t in tech_stack]

        # Check for web frameworks
        web_frameworks = ["react", "vue", "angular", "next.js", "nextjs", "nuxt", "svelte"]
        if any(fw in tech_stack_lower for fw in web_frameworks):
            # Check if it's fullstack
            backend_frameworks = ["node", "express", "fastapi", "django", "flask", "rails"]
            if any(bf in tech_stack_lower for bf in backend_frameworks):
                return "fullstack"
            return "web"

        # Check for API/backend
        api_frameworks = ["fastapi", "express", "django", "flask", "rails", "spring", "gin"]
        if any(fw in tech_stack_lower for fw in api_frameworks):
            return "api"

        # Check for mobile
        mobile_frameworks = ["react native", "flutter", "swift", "kotlin", "ionic"]
        if any(fw in tech_stack_lower for fw in mobile_frameworks):
            return "mobile"

        # Check for ML/AI
        ml_tools = ["tensorflow", "pytorch", "scikit", "keras", "pandas", "numpy", "ml", "ai"]
        if any(tool in tech_stack_lower for tool in ml_tools):
            return "ml"

        # Check for data
        data_tools = ["spark", "hadoop", "airflow", "dbt", "snowflake", "bigquery"]
        if any(tool in tech_stack_lower for tool in data_tools):
            return "data"

        # Check for devops
        devops_tools = ["docker", "kubernetes", "terraform", "ansible", "jenkins", "github actions"]
        if any(tool in tech_stack_lower for tool in devops_tools):
            return "devops"

        return "custom"


# Create singleton instance
template_service = TemplateService()
