"""
NLP-to-SQL Parser Service
Converts natural language queries to SQL using Strands Agent and Claude.
Integrates with database metadata service for schema context.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from strands import Agent
from strands.models import BedrockModel

from services.database_metadata_service import db_metadata_service

logger = logging.getLogger(__name__)


class NLPToSQLParser:
    """
    NLP-to-SQL parser using Strands Agent with Claude for SQL generation.

    Features:
    - Schema-aware SQL generation using cached metadata
    - Business terminology resolution
    - Common query pattern templates
    - Query optimization suggestions
    - Support for various query types (SELECT, aggregations, joins)
    """

    def __init__(self):
        """Initialize NLP-to-SQL parser with Strands Agent"""
        # Initialize Strands Agent with Claude model
        self.model = BedrockModel(
            model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            temperature=0.1,  # Low temperature for consistent SQL generation
            max_tokens=4096,
            streaming=False  # SQL generation doesn't need streaming
        )

        self.agent = Agent(model=self.model)

        logger.info("NLP-to-SQL parser initialized with Claude 3.5 Sonnet")

    async def parse_to_sql(
        self,
        natural_language_query: str,
        persona_id: str,
        credentials: Dict[str, Any],
        business_terms: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Convert natural language query to SQL.

        Args:
            natural_language_query: User's natural language question
            persona_id: Database persona identifier
            credentials: Database connection credentials
            business_terms: Optional business term mappings (term -> column)

        Returns:
            Dictionary with:
            {
                "success": bool,
                "sql": str,  # Generated SQL query
                "explanation": str,  # Human-readable explanation
                "confidence": float,  # Confidence score (0-1)
                "tables_used": List[str],  # Tables referenced
                "optimization_suggestions": List[str],  # Optional optimization tips
                "error": str  # Error message if failed
            }
        """
        try:
            logger.info(f"Parsing NLP query: {natural_language_query[:100]}...")

            # Get schema metadata from cache
            schema_metadata = await db_metadata_service.get_schema_metadata(
                persona_id, credentials
            )

            if not schema_metadata.get("tables"):
                return {
                    "success": False,
                    "error": "No schema metadata available. Please refresh schema cache."
                }

            # Build context for SQL generation
            context = self._build_schema_context(schema_metadata, business_terms)

            # Create prompt for SQL generation
            prompt = self._create_sql_generation_prompt(
                natural_language_query,
                context,
                credentials.get("db_type", "postgresql")
            )

            # Generate SQL using Strands Agent
            logger.debug(f"Sending prompt to Claude for SQL generation")
            response = self.agent(prompt)

            # Parse the response
            result = self._parse_agent_response(response, schema_metadata)

            logger.info(f"SQL generation {'successful' if result['success'] else 'failed'}")
            if result.get("success"):
                logger.debug(f"Generated SQL: {result.get('sql', '')[:200]}...")

            return result

        except Exception as e:
            logger.error(f"Error parsing NLP to SQL: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to generate SQL: {str(e)}"
            }

    def _build_schema_context(
        self,
        schema_metadata: Dict[str, Any],
        business_terms: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Build schema context string for SQL generation prompt.

        Args:
            schema_metadata: Schema metadata from database_metadata_service
            business_terms: Optional business term mappings

        Returns:
            Formatted schema context string
        """
        context_parts = []

        # Database info
        db_type = schema_metadata.get("db_type", "postgresql")
        database = schema_metadata.get("database", "")
        context_parts.append(f"Database Type: {db_type}")
        context_parts.append(f"Database Name: {database}")
        context_parts.append("")

        # Tables and columns
        context_parts.append("AVAILABLE TABLES AND COLUMNS:")
        context_parts.append("-" * 60)

        for table in schema_metadata.get("tables", []):
            schema = table.get("schema", "public")
            table_name = table.get("table_name", "")

            # Table header
            context_parts.append(f"\nTable: {schema}.{table_name}")

            # Primary keys
            primary_keys = table.get("primary_keys", [])
            if primary_keys:
                context_parts.append(f"  Primary Key: {', '.join(primary_keys)}")

            # Columns
            context_parts.append("  Columns:")
            for col in table.get("columns", []):
                col_name = col.get("column_name", "")
                data_type = col.get("data_type", "")
                nullable = " (nullable)" if col.get("nullable") else " (NOT NULL)"
                default = f" DEFAULT {col.get('default_value')}" if col.get("default_value") else ""

                context_parts.append(f"    - {col_name}: {data_type}{nullable}{default}")

            # Indexes (excluding primary key indexes)
            indexes = [idx for idx in table.get("indexes", []) if not idx.get("is_primary")]
            if indexes:
                context_parts.append("  Indexes:")
                for idx in indexes:
                    idx_name = idx.get("index_name", "")
                    idx_cols = ", ".join(idx.get("columns", []))
                    unique = "UNIQUE " if idx.get("is_unique") else ""
                    context_parts.append(f"    - {unique}INDEX {idx_name} ON ({idx_cols})")

        # Foreign key relationships
        relationships = schema_metadata.get("relationships", [])
        if relationships:
            context_parts.append("\nFOREIGN KEY RELATIONSHIPS:")
            context_parts.append("-" * 60)
            for rel in relationships:
                source = f"{rel['source_schema']}.{rel['source_table']}.{rel['source_column']}"
                target = f"{rel['target_schema']}.{rel['target_table']}.{rel['target_column']}"
                context_parts.append(f"  {source} -> {target}")

        # Business terminology
        if business_terms:
            context_parts.append("\nBUSINESS TERM MAPPINGS:")
            context_parts.append("-" * 60)
            for term, column in business_terms.items():
                context_parts.append(f"  '{term}' refers to column: {column}")

        return "\n".join(context_parts)

    def _create_sql_generation_prompt(
        self,
        natural_language_query: str,
        schema_context: str,
        db_type: str
    ) -> str:
        """
        Create prompt for SQL generation using Claude.

        Args:
            natural_language_query: User's natural language question
            schema_context: Formatted schema context
            db_type: Database type (postgresql, mysql, mssql)

        Returns:
            Formatted prompt string
        """
        db_specific_notes = self._get_db_specific_notes(db_type)

        prompt = f"""You are an expert SQL query generator. Your task is to convert natural language questions into precise, efficient SQL queries.

SCHEMA CONTEXT:
{schema_context}

{db_specific_notes}

NATURAL LANGUAGE QUERY:
"{natural_language_query}"

INSTRUCTIONS:
1. Generate a valid {db_type.upper()} SQL query that answers the natural language question
2. Use appropriate JOIN conditions based on foreign key relationships
3. Apply filters, aggregations, and sorting as needed
4. Limit results to a reasonable number (default 100 unless specified)
5. Use table aliases for readability
6. Include column aliases for calculated fields
7. Ensure the query is safe (no destructive operations like DROP, DELETE, UPDATE, INSERT)
8. Use schema-qualified table names (schema.table_name)

COMMON QUERY PATTERNS:
- For "show/list/get all X": SELECT * FROM table WHERE conditions
- For "how many/count": SELECT COUNT(*) FROM table WHERE conditions
- For "top N": Use ORDER BY with LIMIT (PostgreSQL/MySQL) or TOP (MSSQL)
- For "total/sum": Use SUM() with GROUP BY if needed
- For "average": Use AVG() with GROUP BY if needed
- For "last/recent": ORDER BY date_column DESC LIMIT N
- For relationships: Use JOIN on foreign key columns

RESPONSE FORMAT (JSON):
{{
    "sql": "YOUR GENERATED SQL QUERY HERE",
    "explanation": "Brief explanation of what the query does and why",
    "confidence": 0.95,
    "tables_used": ["schema.table1", "schema.table2"],
    "optimization_suggestions": ["Optional: suggestions for query optimization"]
}}

Generate the SQL query now:"""

        return prompt

    def _get_db_specific_notes(self, db_type: str) -> str:
        """Get database-specific SQL syntax notes"""
        notes = {
            "postgresql": """
DATABASE-SPECIFIC SYNTAX (PostgreSQL):
- Use $1, $2 for parameterized queries (but avoid for generated SQL)
- String concatenation: || operator or CONCAT()
- Date functions: CURRENT_DATE, DATE_TRUNC(), EXTRACT()
- LIMIT and OFFSET for pagination
- ILIKE for case-insensitive search
- Array operations: ANY(), ALL()
- Window functions supported: ROW_NUMBER(), RANK(), etc.
""",
            "mysql": """
DATABASE-SPECIFIC SYNTAX (MySQL):
- Use LIMIT for row limiting
- String concatenation: CONCAT()
- Date functions: CURDATE(), DATE_FORMAT(), YEAR()
- Backticks for identifiers with special characters
- LIKE for pattern matching (case-insensitive by default on some collations)
""",
            "mssql": """
DATABASE-SPECIFIC SYNTAX (MSSQL):
- Use TOP N for limiting results (or OFFSET/FETCH in newer versions)
- String concatenation: + operator or CONCAT()
- Date functions: GETDATE(), DATEPART(), YEAR()
- Square brackets for identifiers with special characters
- LIKE for pattern matching
"""
        }

        return notes.get(db_type.lower(), "")

    def _parse_agent_response(
        self,
        response: str,
        schema_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Parse the Strands Agent response into structured result.

        Args:
            response: Raw response from Strands Agent
            schema_metadata: Schema metadata for validation

        Returns:
            Parsed result dictionary
        """
        try:
            # Try to extract JSON from response
            # Claude might wrap JSON in code blocks
            response_text = str(response).strip()

            # Remove markdown code blocks if present
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            # Parse JSON
            parsed = json.loads(response_text)

            # Validate required fields
            if "sql" not in parsed:
                return {
                    "success": False,
                    "error": "Generated response missing SQL query"
                }

            # Validate SQL safety (basic check)
            sql_upper = parsed["sql"].upper()
            dangerous_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE", "ALTER", "CREATE"]
            for keyword in dangerous_keywords:
                if keyword in sql_upper:
                    return {
                        "success": False,
                        "error": f"Generated SQL contains dangerous operation: {keyword}. Only SELECT queries are allowed."
                    }

            # Return validated result
            return {
                "success": True,
                "sql": parsed.get("sql", ""),
                "explanation": parsed.get("explanation", ""),
                "confidence": float(parsed.get("confidence", 0.8)),
                "tables_used": parsed.get("tables_used", []),
                "optimization_suggestions": parsed.get("optimization_suggestions", [])
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Agent response: {e}")
            logger.debug(f"Raw response: {response}")

            # Attempt to extract SQL from non-JSON response
            response_text = str(response).strip()

            # Look for SQL SELECT statement
            if "SELECT" in response_text.upper():
                # Try to extract SQL query
                lines = response_text.split("\n")
                sql_lines = []
                in_sql = False

                for line in lines:
                    line_upper = line.strip().upper()
                    if line_upper.startswith("SELECT"):
                        in_sql = True

                    if in_sql:
                        sql_lines.append(line)

                        # Check if query ends
                        if line.strip().endswith(";"):
                            break

                if sql_lines:
                    sql = "\n".join(sql_lines).strip()
                    return {
                        "success": True,
                        "sql": sql,
                        "explanation": "SQL query extracted from response",
                        "confidence": 0.7,
                        "tables_used": [],
                        "optimization_suggestions": []
                    }

            return {
                "success": False,
                "error": f"Could not parse SQL from response: {str(e)}"
            }

        except Exception as e:
            logger.error(f"Error parsing agent response: {e}")
            return {
                "success": False,
                "error": f"Failed to parse response: {str(e)}"
            }

    async def explain_query(
        self,
        sql_query: str,
        schema_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate human-readable explanation of an SQL query.

        Args:
            sql_query: SQL query to explain
            schema_metadata: Schema metadata for context

        Returns:
            Dictionary with explanation and query analysis
        """
        try:
            # Build schema context
            context = self._build_schema_context(schema_metadata)

            prompt = f"""You are an SQL expert. Explain the following SQL query in simple, human-readable terms.

SCHEMA CONTEXT:
{context}

SQL QUERY:
{sql_query}

Provide:
1. A brief summary of what the query does
2. Which tables it accesses
3. Any filters or conditions applied
4. What data it returns
5. Any potential performance considerations

Response format (JSON):
{{
    "summary": "One sentence summary",
    "detailed_explanation": "Detailed explanation in plain English",
    "tables_accessed": ["table1", "table2"],
    "performance_notes": ["Any performance considerations"]
}}
"""

            response = self.agent(prompt)

            # Parse response
            response_text = str(response).strip()
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            parsed = json.loads(response_text)

            return {
                "success": True,
                "explanation": parsed
            }

        except Exception as e:
            logger.error(f"Error explaining query: {e}")
            return {
                "success": False,
                "error": f"Failed to explain query: {str(e)}"
            }

    async def optimize_query(
        self,
        sql_query: str,
        schema_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Suggest optimizations for an SQL query.

        Args:
            sql_query: SQL query to optimize
            schema_metadata: Schema metadata with index information

        Returns:
            Dictionary with optimization suggestions
        """
        try:
            # Build schema context with index information
            context = self._build_schema_context(schema_metadata)

            prompt = f"""You are an SQL performance optimization expert. Analyze the following query and suggest optimizations.

SCHEMA CONTEXT (includes indexes):
{context}

SQL QUERY TO OPTIMIZE:
{sql_query}

Provide optimization suggestions considering:
1. Index usage and recommendations
2. JOIN optimization
3. WHERE clause efficiency
4. SELECT column optimization (avoid SELECT *)
5. Subquery optimization
6. Potential performance bottlenecks

Response format (JSON):
{{
    "optimized_query": "Optimized version of the SQL query",
    "suggestions": [
        "Suggestion 1",
        "Suggestion 2"
    ],
    "index_recommendations": [
        "Recommended index 1",
        "Recommended index 2"
    ],
    "performance_impact": "High/Medium/Low improvement expected"
}}
"""

            response = self.agent(prompt)

            # Parse response
            response_text = str(response).strip()
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            parsed = json.loads(response_text)

            return {
                "success": True,
                "optimization": parsed
            }

        except Exception as e:
            logger.error(f"Error optimizing query: {e}")
            return {
                "success": False,
                "error": f"Failed to optimize query: {str(e)}"
            }


# Global NLP-to-SQL parser instance
nlp_to_sql_parser = NLPToSQLParser()
