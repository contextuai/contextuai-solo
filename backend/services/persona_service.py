import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from .tools import get_tool_registry

# Import database and repositories for MongoDB access
from database import get_database
from repositories import PersonaRepository, PersonaTypeRepository

logger = logging.getLogger(__name__)


class PersonaService:
    """Service for managing persona contexts and building AI prompts"""

    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "dev")

        # Initialize tool registry
        self.tool_registry = get_tool_registry()

        # Repository instances will be created when needed (async context)
        self._persona_repo: Optional[PersonaRepository] = None
        self._persona_type_repo: Optional[PersonaTypeRepository] = None

    async def _get_persona_repo(self) -> PersonaRepository:
        """Get or create PersonaRepository instance"""
        if self._persona_repo is None:
            db = await get_database()
            self._persona_repo = PersonaRepository(db)
        return self._persona_repo

    async def _get_persona_type_repo(self) -> PersonaTypeRepository:
        """Get or create PersonaTypeRepository instance"""
        if self._persona_type_repo is None:
            db = await get_database()
            self._persona_type_repo = PersonaTypeRepository(db)
        return self._persona_type_repo

    async def build_persona_context(self, persona_id: Optional[str]) -> Dict[str, Any]:
        """
        Build persona context for AI prompt generation

        Args:
            persona_id: ID of the persona to load

        Returns:
            Dict containing system prompt, tools, constraints, and connection config
        """
        if not persona_id:
            return self._get_default_context()

        try:
            # Get persona configuration from MongoDB
            persona_type_repo = await self._get_persona_type_repo()
            persona_data = await persona_type_repo.get_by_id(persona_id)

            if not persona_data:
                print(f"WARNING: Persona {persona_id} not found, using default context")
                return self._get_default_context()

            # Build comprehensive context
            context = {
                "persona_id": persona_id,
                "name": persona_data.get("name", "Assistant"),
                "system_prompt": self._build_system_prompt(persona_data),
                "tools": self._extract_tools(persona_data),
                "constraints": self._extract_constraints(persona_data),
                "connection_config": self._extract_connection_config(persona_data),
                "capabilities": persona_data.get("capabilities", []),
                "metadata": {
                    "category": persona_data.get("category", "general"),
                    "version": persona_data.get("version", "1.0"),
                    "last_updated": persona_data.get("updated_at", ""),
                    "description": persona_data.get("description", "")
                }
            }

            return context

        except Exception as e:
            print(f"ERROR: Failed to build persona context for {persona_id}: {e}")
            return self._get_default_context()

    async def build_persona_instance_context(self, persona_instance_id: Optional[str]) -> Dict[str, Any]:
        """
        Build persona context for AI prompt generation from a persona INSTANCE.
        This loads the persona instance (with credentials) and the persona type,
        then builds a context that includes system_instructions for generic personas.

        Args:
            persona_instance_id: ID of the persona instance to load

        Returns:
            Dict containing system prompt, tools, constraints, and connection config
        """
        if not persona_instance_id:
            return self._get_default_context()

        try:
            # Get persona INSTANCE from personas collection (contains credentials)
            persona_repo = await self._get_persona_repo()
            persona_instance = await persona_repo.get_by_id_with_credentials(persona_instance_id)

            if not persona_instance:
                print(f"WARNING: Persona instance {persona_instance_id} not found, using default context")
                return self._get_default_context()

            persona_type_id = persona_instance.get("persona_type_id")
            credentials = persona_instance.get("credentials", {})

            # Get persona TYPE from persona_types collection (contains schema/definition)
            persona_type_repo = await self._get_persona_type_repo()
            persona_type_data = await persona_type_repo.get_by_id(persona_type_id) or {}

            # Build base system prompt
            system_prompt = self._build_system_prompt(persona_type_data, credentials)

            # For database personas, inject cached schema summary into system prompt
            category = persona_type_data.get("category", "general")
            if category == "database" and credentials:
                schema_summary = await self._build_schema_summary(persona_instance_id, credentials)
                if schema_summary:
                    system_prompt += f"\n\n{schema_summary}"

            # Build comprehensive context
            context = {
                "persona_id": persona_instance_id,
                "persona_type_id": persona_type_id,
                "name": persona_instance.get("name", persona_type_data.get("name", "Assistant")),
                "system_prompt": system_prompt,
                "tools": self._extract_tools(persona_type_data),
                "constraints": self._extract_constraints(persona_type_data),
                "connection_config": self._extract_connection_config(persona_type_data),
                "capabilities": persona_type_data.get("capabilities", []),
                "metadata": {
                    "category": category,
                    "version": persona_type_data.get("version", "1.0"),
                    "last_updated": persona_instance.get("updated_at", ""),
                    "description": persona_instance.get("description", persona_type_data.get("description", ""))
                }
            }

            return context

        except Exception as e:
            print(f"ERROR: Failed to build persona instance context for {persona_instance_id}: {e}")
            import traceback
            traceback.print_exc()
            return self._get_default_context()

    def _build_system_prompt(self, persona_data: Dict[str, Any], credentials: Dict[str, Any] = None) -> str:
        """Build comprehensive system prompt from persona data and optional credentials

        Args:
            persona_data: The persona type data from MongoDB
            credentials: Optional credentials/config from persona instance (for generic personas)

        Returns:
            Formatted system prompt string
        """

        prompt_parts = []

        # Check for generic persona with system_instructions in credentials
        if credentials and credentials.get("system_instructions"):
            # Use system_instructions as the PRIMARY identity for generic personas
            prompt_parts.append(credentials["system_instructions"])

            # Add expertise area context if provided
            expertise = credentials.get("expertise_area")
            if expertise:
                prompt_parts.append(f"Your area of expertise is: {expertise}")

            # Add tone modifier
            tone = credentials.get("tone")
            if tone:
                tone_instructions = {
                    "Professional": "Maintain a professional, business-appropriate tone.",
                    "Casual": "Use a relaxed, conversational tone.",
                    "Friendly": "Be warm, approachable, and encouraging.",
                    "Formal": "Use formal language and maintain proper etiquette.",
                    "Technical": "Use precise technical terminology and detailed explanations."
                }
                if tone in tone_instructions:
                    prompt_parts.append(tone_instructions[tone])

            # Add response style modifier
            style = credentials.get("response_style")
            if style:
                style_instructions = {
                    "Concise": "Keep responses brief and to the point. Prioritize clarity over detail.",
                    "Detailed": "Provide comprehensive, thorough responses with full explanations.",
                    "Balanced": "Balance detail with conciseness based on question complexity."
                }
                if style in style_instructions:
                    prompt_parts.append(style_instructions[style])

            # Add language preference
            language = credentials.get("language")
            if language:
                prompt_parts.append(f"Respond in {language}.")

            # Add behavioral guidelines for generic personas too
            guidelines = self._get_behavioral_guidelines(persona_data)
            if guidelines:
                prompt_parts.append(guidelines)

            return "\n\n".join(prompt_parts)

        # Standard persona handling (database, API, etc.)
        # Base identity and role
        name = persona_data.get("name", "Assistant")
        description = persona_data.get("description", "")

        if description:
            prompt_parts.append(f"You are {name}, {description}")
        else:
            prompt_parts.append(f"You are {name}, an AI assistant.")

        # Add category-specific behavior
        category = persona_data.get("category", "")
        if category:
            category_prompt = self._get_category_prompt(category)
            if category_prompt:
                prompt_parts.append(category_prompt)

        # Add capabilities and tools context
        capabilities = persona_data.get("capabilities", [])
        if capabilities:
            capabilities_text = ", ".join(capabilities)
            prompt_parts.append(f"Your capabilities include: {capabilities_text}")

        # Add behavioral guidelines
        guidelines = self._get_behavioral_guidelines(persona_data)
        if guidelines:
            prompt_parts.append(guidelines)

        # Add connection-specific context
        connection_context = self._get_connection_context(persona_data)
        if connection_context:
            prompt_parts.append(connection_context)

        # Add custom instructions if available
        custom_instructions = persona_data.get("custom_instructions", "")
        if custom_instructions:
            prompt_parts.append(f"Additional instructions: {custom_instructions}")

        return "\n\n".join(prompt_parts)

    def _get_category_prompt(self, category: str) -> str:
        """Get category-specific prompt additions"""

        category_prompts = {
            "database": (
                "You are specialized in database operations, SQL queries, and data analysis. "
                "Always prioritize data accuracy and security. When working with databases, "
                "explain your queries and suggest optimizations where appropriate."
            ),
            "api": (
                "You are specialized in API integration and web services. "
                "Focus on proper authentication, error handling, and data validation. "
                "Provide clear examples and explain API best practices."
            ),
            "analytics": (
                "You are specialized in data analytics and business intelligence. "
                "Focus on generating insights, creating meaningful visualizations, "
                "and explaining statistical concepts in accessible terms."
            ),
            "development": (
                "You are a software development assistant. "
                "Focus on clean code, best practices, testing, and maintainability. "
                "Provide code examples and explain technical concepts clearly."
            ),
            "business": (
                "You are a business analysis assistant. "
                "Focus on strategic insights, process optimization, and data-driven decisions. "
                "Present information in a professional, executive-friendly format."
            ),
            "general": (
                "You are a general-purpose assistant. "
                "Be helpful, accurate, and adapt your communication style to the user's needs."
            )
        }

        return category_prompts.get(category.lower(), "")

    def _get_behavioral_guidelines(self, persona_data: Dict[str, Any]) -> str:
        """Get behavioral guidelines based on persona configuration"""

        guidelines = []

        # Security and privacy guidelines
        guidelines.append(
            "Always prioritize security and privacy. Never expose sensitive information "
            "like passwords, API keys, or personal data in your responses."
        )

        # Accuracy and reliability
        guidelines.append(
            "Be accurate and reliable. If you're unsure about something, say so. "
            "Provide sources or suggest verification when dealing with factual information."
        )

        # Communication style
        guidelines.append(
            "Communicate clearly and professionally. Adapt your technical depth "
            "to the user's apparent expertise level."
        )

        # Error handling
        guidelines.append(
            "If you encounter errors or limitations, explain them clearly and "
            "suggest alternative approaches when possible."
        )

        return "Guidelines:\n" + "\n".join(f"- {guideline}" for guideline in guidelines)

    def _get_connection_context(self, persona_data: Dict[str, Any]) -> str:
        """Get connection-specific context and instructions"""

        connection_fields = persona_data.get("connection_fields", [])
        if not connection_fields:
            return ""

        context_parts = []

        # Determine connection type
        connection_types = set()
        for field in connection_fields:
            field_name = field.get("name", "").lower()
            if "database" in field_name or "host" in field_name or "port" in field_name:
                connection_types.add("database")
            elif "api" in field_name or "endpoint" in field_name or "token" in field_name:
                connection_types.add("api")

        # Add connection-specific instructions
        if "database" in connection_types:
            context_parts.append(
                "You have access to database connections. When querying data, "
                "always use parameterized queries to prevent SQL injection. "
                "Limit result sets appropriately and explain your query logic."
            )

        if "api" in connection_types:
            context_parts.append(
                "You have access to API connections. Always handle authentication "
                "securely and implement proper error handling for API calls. "
                "Respect rate limits and provide meaningful error messages."
            )

        if context_parts:
            return "Connection Context:\n" + "\n".join(f"- {part}" for part in context_parts)

        return ""

    async def _build_schema_summary(self, persona_id: str, credentials: Dict[str, Any]) -> str:
        """
        Build a compact schema summary for database personas to inject into the system prompt.
        This allows the AI to know the schema upfront without needing a tool call first.

        Returns a formatted string like:
        Database Schema:
        - orders: id, customer_id, total, status, created_at
        - customers: id, name, email, phone
        """
        try:
            from services.database_metadata_service import db_metadata_service

            schema_metadata = await db_metadata_service.get_schema_metadata(
                persona_id, credentials
            )

            tables = schema_metadata.get("tables", [])
            if not tables:
                return ""

            lines = ["Database Schema (use this to write accurate SQL):"]
            char_count = len(lines[0])

            for table in tables[:50]:  # Cap at 50 tables
                table_name = table.get("table_name", "unknown")
                columns = table.get("columns", [])
                col_names = [c.get("column_name", c.get("name", "?")) for c in columns]
                col_str = ", ".join(col_names)
                line = f"- {table_name}: {col_str}"

                # Truncate at ~2000 chars to keep prompt reasonable
                if char_count + len(line) > 2000:
                    lines.append(f"... and {len(tables) - len(lines) + 1} more tables")
                    break

                lines.append(line)
                char_count += len(line)

            return "\n".join(lines)

        except Exception as e:
            logger.warning(f"Failed to build schema summary for persona {persona_id}: {e}")
            return ""

    def _extract_tools(self, persona_data: Dict[str, Any]) -> List[Any]:
        """Extract and format available tools from persona data using tool registry"""

        capabilities = persona_data.get("capabilities", [])
        persona_id = persona_data.get("id", "unknown")

        # Get actual Strands tools from registry based on capabilities
        tools = self.tool_registry.get_tools_for_persona(persona_id, capabilities)

        # Log tool loading
        print(f"Loaded {len(tools)} tools for persona {persona_id} with capabilities: {capabilities}")

        return tools

    def _extract_constraints(self, persona_data: Dict[str, Any]) -> List[str]:
        """Extract operational constraints from persona data"""

        constraints = []

        # Add general security constraints
        constraints.extend([
            "Never expose sensitive credentials or connection strings",
            "Always validate input parameters before processing",
            "Limit query results to reasonable sizes (max 1000 rows)",
            "Timeout long-running operations after 30 seconds"
        ])

        # Add category-specific constraints
        category = persona_data.get("category", "")
        if category == "database":
            constraints.extend([
                "Only execute SELECT queries unless explicitly authorized for modifications",
                "Always use LIMIT clauses in SELECT statements",
                "Avoid queries that could cause performance issues"
            ])
        elif category == "api":
            constraints.extend([
                "Respect API rate limits and implement backoff strategies",
                "Never log or expose API response data containing PII",
                "Validate API responses before processing"
            ])

        return constraints

    def _extract_connection_config(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract connection configuration (without sensitive data)"""

        connection_fields = persona_data.get("connection_fields", [])

        config = {
            "has_connections": len(connection_fields) > 0,
            "connection_types": [],
            "required_fields": [],
            "optional_fields": []
        }

        for field in connection_fields:
            field_name = field.get("name", "")
            field_type = field.get("type", "")
            is_required = field.get("required", True)

            # Categorize connection types
            if "database" in field_name.lower() or "host" in field_name.lower():
                if "database" not in config["connection_types"]:
                    config["connection_types"].append("database")
            elif "api" in field_name.lower() or "token" in field_name.lower():
                if "api" not in config["connection_types"]:
                    config["connection_types"].append("api")

            # Track required vs optional fields
            field_info = {
                "name": field_name,
                "type": field_type,
                "label": field.get("label", field_name)
            }

            if is_required:
                config["required_fields"].append(field_info)
            else:
                config["optional_fields"].append(field_info)

        return config

    def _get_default_context(self) -> Dict[str, Any]:
        """Get default context when no persona is specified"""

        return {
            "persona_id": None,
            "name": "Assistant",
            "system_prompt": (
                "You are a helpful AI assistant. Provide accurate, helpful responses "
                "while being professional and clear in your communication. "
                "If you're unsure about something, say so rather than guessing."
            ),
            "tools": [],
            "constraints": [
                "Always prioritize user privacy and data security",
                "Provide accurate information and cite sources when possible",
                "Be helpful while staying within ethical guidelines"
            ],
            "connection_config": {
                "has_connections": False,
                "connection_types": [],
                "required_fields": [],
                "optional_fields": []
            },
            "capabilities": ["general_assistance"],
            "metadata": {
                "category": "general",
                "version": "1.0",
                "last_updated": datetime.utcnow().isoformat() + "Z",
                "description": "Default general-purpose assistant"
            }
        }

    async def validate_persona_access(self, user_id: str, persona_id: str) -> bool:
        """
        Validate if user has access to the specified persona
        TODO: Implement when persona access control is added
        """
        # For now, return True (all personas are accessible)
        # This should integrate with the persona_access router when implemented
        return True

    async def get_persona_summary(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """Get basic persona information for display purposes"""

        try:
            persona_type_repo = await self._get_persona_type_repo()
            persona_data = await persona_type_repo.get_by_id(persona_id)

            if not persona_data:
                return None

            return {
                "id": persona_id,
                "name": persona_data.get("name", "Unknown"),
                "description": persona_data.get("description", ""),
                "category": persona_data.get("category", "general"),
                "capabilities": persona_data.get("capabilities", []),
                "icon": persona_data.get("icon", ""),
                "color": persona_data.get("color", "#6366f1")
            }

        except Exception as e:
            print(f"ERROR: Failed to get persona summary for {persona_id}: {e}")
            return None

    async def get_persona_tools(self, persona_id: Optional[str], persona_type: Optional[str] = None) -> List[Any]:
        """
        Get Strands tools for a persona based on its persona_type_id.

        Args:
            persona_id: ID of the persona instance
            persona_type: Optional persona type from frontend (optimization to avoid MongoDB lookup)

        Returns:
            List of Strands tool instances
        """
        if not persona_id:
            # Return empty list for default persona (no tools)
            return []

        try:
            # Get persona instance from personas collection
            persona_repo = await self._get_persona_repo()
            persona_instance = await persona_repo.get_by_id_with_credentials(persona_id)

            if not persona_instance:
                print(f"WARNING: Persona instance {persona_id} not found, returning empty tools")
                return []

            # Use persona_type from frontend if provided (optimization)
            if persona_type:
                print(f"Using provided persona_type from frontend: {persona_type}")
                effective_type = persona_type
            else:
                # Fallback to MongoDB lookup (backwards compatibility)
                effective_type = persona_instance.get("persona_type_id")
                print(f"No persona_type provided, using persona_type_id from MongoDB: {effective_type}")

            if not effective_type:
                print(f"WARNING: Persona {persona_id} has no persona_type_id, returning empty tools")
                return []

            # Inject db_type into credentials for database personas
            if persona_instance.get("credentials"):
                db_type = self._map_persona_type_to_db_type(effective_type)
                persona_instance["credentials"]["db_type"] = db_type
                print(f"Injected db_type into credentials: {db_type}")

            # Get tools from registry based on persona_type_id
            # Pass persona_instance as persona_data (includes credentials for database personas)
            tools = self.tool_registry.get_tools_for_persona_type(
                persona_id=persona_id,
                persona_type_id=effective_type,
                persona_data=persona_instance
            )

            print(f"Retrieved {len(tools)} tools for persona {persona_id} (type: {effective_type})")
            return tools

        except Exception as e:
            print(f"ERROR: Failed to get tools for persona {persona_id}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _map_persona_type_to_db_type(self, persona_type: str) -> str:
        """
        Map persona type to database type.

        Args:
            persona_type: The persona type from frontend or MongoDB

        Returns:
            Clean database type (postgresql, mysql, mssql, etc.)
        """
        if not persona_type:
            return "unknown"

        persona_lower = persona_type.lower()

        # PostgreSQL variants
        if 'postgresql' in persona_lower or 'postgres' in persona_lower:
            return 'postgresql'

        # MySQL variants
        elif 'mysql' in persona_lower:
            return 'mysql'

        # Microsoft SQL Server variants
        elif 'mssql' in persona_lower or 'sqlserver' in persona_lower or 'sql server' in persona_lower:
            return 'mssql'

        # MongoDB
        elif 'mongodb' in persona_lower or 'mongo' in persona_lower:
            return 'mongodb'

        # Oracle
        elif 'oracle' in persona_lower:
            return 'oracle'

        # SQLite
        elif 'sqlite' in persona_lower:
            return 'sqlite'

        # Default: assume it's already clean
        return persona_lower
