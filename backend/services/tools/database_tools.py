"""
Database operation tools for Strands Agent.

Legacy direct warehouse connectors (PostgreSQL, MySQL, MSSQL, Snowflake) were
retired in Vesper v1.2 in favor of MCP server connectors. This module keeps
the ``DatabaseTools`` class and ``@tool`` method signatures intact so
``ToolRegistry`` and ``PersonaService`` load cleanly without legacy warehouse
dependencies.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from strands.tools import tool

logger = logging.getLogger(__name__)


class DatabaseTools:
    """Stubbed database tools returning a retirement message directing users to MCP."""

    def __init__(self, persona_id: str, credentials: Dict[str, Any]):
        """Initialize database tools stub with persona credentials."""
        self.persona_id = persona_id
        self.credentials = credentials
        self.environment = os.getenv("ENVIRONMENT", "dev")
        self.db_type = str(credentials.get("db_type", "postgresql")).lower()
        logger.info(
            "DatabaseTools initialized for persona %s, db_type: %s (retired)",
            persona_id,
            self.db_type,
        )

    def _retired_error(self) -> Dict[str, Any]:
        return {
            "success": False,
            "error": (
                f"Legacy warehouse connector '{self.db_type}' has been retired "
                "in Vesper v1.2. Use an MCP server connector instead."
            ),
        }

    def get_tools(self) -> List[Any]:
        """Return all database operation tools as a list for Strands Agent."""
        return [
            self.query_database,
            self.get_schema_info,
            self.analyze_table,
            self.explain_query,
            self.get_relationships,
            self.test_connection,
            self.get_table_sample,
        ]

    @tool
    async def query_database(
        self,
        query: str,
        natural_language: Optional[str] = None,
        timeout: Optional[int] = None,
        row_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Retired legacy SQL query tool; returns an MCP migration message."""
        return self._retired_error()

    @tool
    async def get_schema_info(
        self,
        include_sample_data: bool = False,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Retired legacy schema introspection tool; returns an MCP migration message."""
        return self._retired_error()

    @tool
    async def analyze_table(
        self,
        table_name: str,
        include_sample: bool = True,
        sample_size: int = 10,
    ) -> Dict[str, Any]:
        """Retired legacy table analysis tool; returns an MCP migration message."""
        return self._retired_error()

    @tool
    async def explain_query(self, query: str) -> Dict[str, Any]:
        """Retired legacy EXPLAIN query tool; returns an MCP migration message."""
        return self._retired_error()

    @tool
    async def get_relationships(
        self,
        table_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retired legacy foreign-key lookup tool; returns an MCP migration message."""
        return self._retired_error()

    @tool
    async def test_connection(self) -> Dict[str, Any]:
        """Retired legacy connection test tool; returns an MCP migration message."""
        return self._retired_error()

    @tool
    async def get_table_sample(
        self,
        table_name: str,
        sample_size: int = 10,
    ) -> Dict[str, Any]:
        """Retired legacy table sampling tool; returns an MCP migration message."""
        return self._retired_error()
