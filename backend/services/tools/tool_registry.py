"""
Central Tool Registry for managing Strands Agent tools.
Maps persona capabilities to actual tool implementations.
"""

import logging
from typing import Dict, List, Any, Optional, Type
import os

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Central registry for managing and mapping persona tools."""

    def __init__(self):
        """Initialize the tool registry."""
        self.environment = os.getenv("ENVIRONMENT", "dev")

        # Maps capability names to tool classes
        self._capability_tool_map: Dict[str, List[Type]] = {}

        # Maps persona IDs to their specific tool instances
        self._persona_tools: Dict[str, List] = {}

        # Cached tool instances
        self._tool_instances: Dict[str, List] = {}

        # Initialize default tool mappings
        self._initialize_default_mappings()

        logger.info(f"Tool Registry initialized for environment: {self.environment}")

    def _initialize_default_mappings(self):
        """Initialize default capability to tool mappings."""
        from .file_tools import FileTools
        from .web_tools import WebTools
        from .api_tools import APITools
        from .database_tools import DatabaseTools
        from .document_tools import DocumentTools
        from .image_tools import ImageTools
        from .scm_tools import SCMTools
        from .mcp_tools import MCPTools
        from .mongodb_tools import MongoDBTools
        from .slack_tools import SlackTools
        from .email_tools import EmailTools
        from .aws_tools import AWSTools

        # Map capabilities to tool classes
        self._capability_tool_map = {
            # File operations
            "file_read": [FileTools],
            "file_write": [FileTools],
            "file_list": [FileTools],
            "file_processing": [FileTools],

            # Web operations
            "web_search": [WebTools],
            "web_scraping": [WebTools],
            "web_fetch": [WebTools],

            # API operations
            "api_call": [APITools],
            "http_request": [APITools],
            "webhook": [APITools],

            # Database operations
            "sql_query": [DatabaseTools],
            "database_query": [DatabaseTools],
            "data_analysis": [DatabaseTools],
            "schema_introspection": [DatabaseTools],

            # Document operations (PDF, DOCX)
            "document_extraction": [DocumentTools],
            "pdf_extraction": [DocumentTools],
            "docx_extraction": [DocumentTools],

            # Image operations
            "image_analysis": [ImageTools],
            "vision": [ImageTools],

            # SCM operations
            "scm_repositories": [SCMTools],
            "scm_issues": [SCMTools],
            "scm_pull_requests": [SCMTools],

            # MongoDB operations
            "mongodb_query": [MongoDBTools],
            "document_database": [MongoDBTools],

            # Slack operations
            "slack_messaging": [SlackTools],
            "slack_search": [SlackTools],

            # Email operations
            "email_send": [EmailTools],
            "email_read": [EmailTools],

            # AWS operations
            "aws_s3": [AWSTools],
            "aws_lambda": [AWSTools],
            "aws_ec2": [AWSTools],

            # Agent orchestration (autonomous crews)
            "agent_discovery": [self._get_agent_tools_class()],
            "agent_invocation": [self._get_agent_tools_class()],
        }

        # Map persona_type_id to tool classes (for Phase 1 Strands Tools integration)
        self._persona_type_tool_map = {
            # File operations
            "file_operations": FileTools,

            # Web operations
            "web_search": WebTools,

            # API operations
            "api_integration": APITools,

            # Clean database type names (from frontend persona_type optimization)
            "postgresql": DatabaseTools,  # Frontend sends this for PostgreSQL personas
            "mysql": DatabaseTools,       # Frontend sends this for MySQL personas
            "mssql": DatabaseTools,       # Frontend sends this for MSSQL personas

            # Database operations - PostgreSQL
            "postgresql_database": DatabaseTools,
            "postgres_db": DatabaseTools,

            # Database operations - MySQL
            "mysql_database": DatabaseTools,
            "mysql_db": DatabaseTools,

            # Database operations - MSSQL
            "mssql_database": DatabaseTools,
            "sqlserver_database": DatabaseTools,

            # Database operations - Snowflake
            "snowflake": DatabaseTools,
            "snowflake_database": DatabaseTools,

            # Database operations - MongoDB
            "mongodb": MongoDBTools,
            "mongodb_database": MongoDBTools,

            # Domain-specific database personas
            "property_management_db": DatabaseTools,
            "sales_database": DatabaseTools,
            "analytics_database": DatabaseTools,
            "hr_database": DatabaseTools,

            # SCM operations - GitHub
            "github": SCMTools,
            "github_scm": SCMTools,

            # SCM operations - GitLab
            "gitlab": SCMTools,
            "gitlab_scm": SCMTools,

            # MCP Server
            "mcp_server": MCPTools,

            # Communication - Slack
            "slack": SlackTools,
            "slack_integration": SlackTools,

            # Communication - Email
            "email_integration": EmailTools,
            "email": EmailTools,

            # Cloud - AWS Services
            "aws_services": AWSTools,
            "aws": AWSTools,

            # Generic persona (no tools - purely instruction-based)
            "generic": None,

            # Document operations (PDF, DOCX text extraction)
            "document_extraction": DocumentTools,
            "pdf_analysis": DocumentTools,
            "docx_analysis": DocumentTools,

            # Image operations (vision/image analysis)
            "image_analysis": ImageTools,
            "vision": ImageTools,
        }

        logger.info(f"Initialized {len(self._capability_tool_map)} capability mappings (incl. agent orchestration)")
        logger.info(f"Initialized {len(self._persona_type_tool_map)} persona type mappings")

    @staticmethod
    def _get_agent_tools_class():
        """Lazy import AgentTools to avoid circular imports."""
        from .agent_tools import AgentTools
        return AgentTools

    def get_tools_for_persona_type(
        self,
        persona_id: str,
        persona_type_id: str,
        persona_data: Optional[Dict[str, Any]] = None
    ) -> List:
        """
        Get tool instances for a specific persona based on its persona type ID.

        Args:
            persona_id: Unique identifier for the persona instance
            persona_type_id: The type of persona (e.g., 'file_operations', 'web_search')
            persona_data: Optional persona configuration data (needed for DatabaseTools)

        Returns:
            List of tool methods for the persona
        """
        # Check cache first
        if persona_id in self._persona_tools:
            logger.debug(f"Returning cached tools for persona: {persona_id}")
            return self._persona_tools[persona_id]

        tools = []

        # Tool classes that require persona-specific credentials
        _credential_tool_classes = {
            "DatabaseTools", "SCMTools", "MCPTools", "MongoDBTools",
            "SlackTools", "EmailTools", "AWSTools",
        }

        # Look up tools by persona_type_id
        if persona_type_id in self._persona_type_tool_map:
            tool_class = self._persona_type_tool_map[persona_type_id]

            # Handle generic personas (no tools - purely instruction-based)
            if tool_class is None:
                logger.info(f"Generic persona type {persona_type_id} - no tools needed (instruction-based)")
                tools = []
            # Special handling for DatabaseTools which needs persona_id and credentials
            elif tool_class.__name__ == "DatabaseTools":
                tool_methods = self._get_or_create_database_tools(
                    persona_id,
                    persona_data or {}
                )
                if tool_methods:
                    tools.extend(tool_methods)
                    logger.info(f"Loaded {len(tool_methods)} tools from {tool_class.__name__} for persona type: {persona_type_id}")
            # Handle other credential-based tool classes (SCM, MCP, MongoDB, Slack, Email, AWS)
            elif tool_class.__name__ in _credential_tool_classes:
                tool_methods = self._get_or_create_credential_tools(
                    tool_class,
                    persona_id,
                    persona_data or {}
                )
                if tool_methods:
                    tools.extend(tool_methods)
                    logger.info(f"Loaded {len(tool_methods)} tools from {tool_class.__name__} for persona type: {persona_type_id}")
            else:
                tool_methods = self._get_or_create_tool_instance(tool_class)
                if tool_methods:
                    tools.extend(tool_methods)
                    logger.info(f"Loaded {len(tool_methods)} tools from {tool_class.__name__} for persona type: {persona_type_id}")
        else:
            logger.warning(f"No tools mapped for persona_type_id: {persona_type_id}")

        # Cache the tools for this persona
        self._persona_tools[persona_id] = tools

        logger.info(f"Loaded {len(tools)} total tool methods for persona {persona_id} with type: {persona_type_id}")
        return tools

    def get_tools_for_persona(self, persona_id: str, capabilities: List[str]) -> List:
        """
        Get tool instances for a specific persona based on its capabilities.

        Args:
            persona_id: Unique identifier for the persona
            capabilities: List of capability names the persona has

        Returns:
            List of tool methods for the persona
        """
        # Check cache first
        if persona_id in self._persona_tools:
            logger.debug(f"Returning cached tools for persona: {persona_id}")
            return self._persona_tools[persona_id]

        tools = []
        loaded_tool_classes = set()  # Track which tool classes we've already instantiated

        for capability in capabilities:
            if capability in self._capability_tool_map:
                tool_classes = self._capability_tool_map[capability]

                for tool_class in tool_classes:
                    # Avoid duplicate tool instances
                    if tool_class not in loaded_tool_classes:
                        tool_methods = self._get_or_create_tool_instance(tool_class)
                        if tool_methods:
                            # Extend the tools list with the individual tool methods
                            tools.extend(tool_methods)
                            loaded_tool_classes.add(tool_class)
                            logger.info(f"Added {len(tool_methods)} tools from {tool_class.__name__} for capability: {capability}")
            else:
                logger.warning(f"No tools mapped for capability: {capability}")

        # Cache the tools for this persona
        self._persona_tools[persona_id] = tools

        logger.info(f"Loaded {len(tools)} total tool methods for persona {persona_id} with capabilities: {capabilities}")
        return tools

    def _get_or_create_tool_instance(self, tool_class: Type) -> Optional[List]:
        """
        Get or create a singleton instance of a tool class and return its tools.

        Args:
            tool_class: The tool class to instantiate

        Returns:
            List of tool methods or None if creation fails
        """
        class_name = tool_class.__name__

        # Check cache
        if class_name in self._tool_instances:
            return self._tool_instances[class_name]

        try:
            # Create new instance
            tool_instance = tool_class()

            # Get all tool methods from the class
            tools = tool_instance.get_tools()

            # Cache the tools (not the instance)
            self._tool_instances[class_name] = tools

            logger.info(f"Created new tool instance: {class_name} with {len(tools)} tools")
            return tools

        except Exception as e:
            logger.error(f"Failed to create tool instance for {class_name}: {e}")
            return None

    def _get_or_create_database_tools(
        self,
        persona_id: str,
        persona_data: Dict[str, Any]
    ) -> Optional[List]:
        """
        Create DatabaseTools instance with persona-specific credentials.

        Args:
            persona_id: Unique identifier for the persona
            persona_data: Persona configuration including credentials

        Returns:
            List of database tool methods or None if creation fails
        """
        from .database_tools import DatabaseTools

        # Use persona_id as cache key for database tools (persona-specific)
        cache_key = f"DatabaseTools_{persona_id}"

        # Check cache
        if cache_key in self._tool_instances:
            logger.debug(f"Returning cached DatabaseTools for persona: {persona_id}")
            return self._tool_instances[cache_key]

        try:
            # Extract credentials from persona data
            credentials = persona_data.get("credentials", {})

            if not credentials:
                logger.warning(
                    f"No credentials found for database persona {persona_id}. "
                    "DatabaseTools requires connection credentials."
                )
                # Return empty list instead of None to avoid errors
                return []

            # Create DatabaseTools instance with credentials
            tool_instance = DatabaseTools(
                persona_id=persona_id,
                credentials=credentials
            )

            # Get all tool methods
            tools = tool_instance.get_tools()

            # Cache the tools
            self._tool_instances[cache_key] = tools

            logger.info(
                f"Created DatabaseTools for persona {persona_id} with {len(tools)} tools, "
                f"db_type: {credentials.get('db_type', 'unknown')}"
            )
            return tools

        except Exception as e:
            logger.error(f"Failed to create DatabaseTools for persona {persona_id}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _get_or_create_credential_tools(
        self,
        tool_class: Type,
        persona_id: str,
        persona_data: Dict[str, Any]
    ) -> Optional[List]:
        """
        Create tool instances that require persona-specific credentials (SCM, MCP, MongoDB, etc.).

        Args:
            tool_class: The tool class to instantiate
            persona_id: Unique identifier for the persona
            persona_data: Persona configuration including credentials

        Returns:
            List of tool methods or empty list if creation fails
        """
        class_name = tool_class.__name__
        cache_key = f"{class_name}_{persona_id}"

        # Check cache
        if cache_key in self._tool_instances:
            logger.debug(f"Returning cached {class_name} for persona: {persona_id}")
            return self._tool_instances[cache_key]

        try:
            credentials = persona_data.get("credentials", {})

            if not credentials:
                logger.warning(
                    f"No credentials found for {class_name} persona {persona_id}. "
                    f"{class_name} requires connection credentials."
                )
                return []

            # Create tool instance with persona_id and credentials
            tool_instance = tool_class(
                persona_id=persona_id,
                credentials=credentials
            )

            # Get all tool methods
            tools = tool_instance.get_tools()

            # Cache the tools
            self._tool_instances[cache_key] = tools

            logger.info(
                f"Created {class_name} for persona {persona_id} with {len(tools)} tools"
            )
            return tools

        except Exception as e:
            logger.error(f"Failed to create {class_name} for persona {persona_id}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_tool_metadata(self, capability: str) -> Dict[str, Any]:
        """
        Get metadata about tools available for a capability.

        Args:
            capability: The capability name

        Returns:
            Dictionary containing tool metadata
        """
        if capability not in self._capability_tool_map:
            return {
                "capability": capability,
                "available": False,
                "tools": []
            }

        tool_classes = self._capability_tool_map[capability]
        tools_info = []

        for tool_class in tool_classes:
            tools_info.append({
                "name": tool_class.__name__,
                "description": tool_class.__doc__ or "No description available",
                "methods": self._get_tool_methods(tool_class)
            })

        return {
            "capability": capability,
            "available": True,
            "tools": tools_info
        }

    def _get_tool_methods(self, tool_class: Type) -> List[Dict[str, str]]:
        """
        Extract tool methods from a tool class.

        Args:
            tool_class: The tool class to inspect

        Returns:
            List of method information dictionaries
        """
        methods = []

        # Get all methods decorated with @tool
        for attr_name in dir(tool_class):
            if not attr_name.startswith('_'):  # Skip private methods
                attr = getattr(tool_class, attr_name)
                if callable(attr) and hasattr(attr, '__wrapped__'):
                    # This is likely a tool-decorated method
                    methods.append({
                        "name": attr_name,
                        "description": attr.__doc__ or "No description available"
                    })

        return methods

    def list_all_capabilities(self) -> List[str]:
        """
        Get a list of all available capabilities.

        Returns:
            List of capability names
        """
        return list(self._capability_tool_map.keys())

    def clear_cache(self, persona_id: Optional[str] = None):
        """
        Clear cached tools for a persona or all personas.

        Args:
            persona_id: Optional specific persona to clear, or None for all
        """
        if persona_id:
            if persona_id in self._persona_tools:
                del self._persona_tools[persona_id]
                logger.info(f"Cleared tool cache for persona: {persona_id}")
        else:
            self._persona_tools.clear()
            logger.info("Cleared all persona tool caches")

    def register_custom_tool(self, capability: str, tool_class: Type):
        """
        Register a custom tool for a capability.

        Args:
            capability: The capability name
            tool_class: The tool class to register
        """
        if capability not in self._capability_tool_map:
            self._capability_tool_map[capability] = []

        if tool_class not in self._capability_tool_map[capability]:
            self._capability_tool_map[capability].append(tool_class)
            logger.info(f"Registered {tool_class.__name__} for capability: {capability}")

            # Clear any cached persona tools to force reload
            self.clear_cache()


# Global singleton instance
_tool_registry_instance: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """
    Get the global tool registry instance.

    Returns:
        The singleton ToolRegistry instance
    """
    global _tool_registry_instance

    if _tool_registry_instance is None:
        _tool_registry_instance = ToolRegistry()

    return _tool_registry_instance