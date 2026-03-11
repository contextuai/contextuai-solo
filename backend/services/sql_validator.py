"""
SQL Validator Service
Provides comprehensive SQL validation, injection prevention, and query analysis.

Security Features:
- SQL injection prevention techniques
- Dangerous operation detection
- Query complexity analysis
- Cost estimation based on table sizes
- Read-only mode enforcement
- Parameter binding validation
"""

import re
import logging
import hashlib
from typing import Dict, Any, List, Optional, Set, Tuple
from enum import Enum
import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Where, Comparison
from sqlparse.tokens import Keyword, DML, DDL

logger = logging.getLogger(__name__)


class QueryRisk(str, Enum):
    """Query risk levels"""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    BLOCKED = "blocked"


class QueryType(str, Enum):
    """SQL query types"""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    DROP = "DROP"
    CREATE = "CREATE"
    ALTER = "ALTER"
    TRUNCATE = "TRUNCATE"
    GRANT = "GRANT"
    REVOKE = "REVOKE"
    EXECUTE = "EXECUTE"
    UNKNOWN = "UNKNOWN"


class SQLValidator:
    """
    SQL validation and security analyzer.

    Features:
    - SQL injection detection and prevention
    - Query complexity analysis
    - Dangerous operation detection
    - Cost estimation
    - Read-only enforcement
    - Parameter validation
    """

    def __init__(self):
        """Initialize SQL validator with security patterns"""

        # SQL injection patterns to detect
        self.injection_patterns = [
            # Classic SQL injection patterns
            r"(\s|^)(OR|AND)\s+\d+\s*=\s*\d+",  # OR 1=1
            r"(\s|^)(OR|AND)\s+['\"].*['\"]\s*=\s*['\"].*['\"]",  # OR 'a'='a'
            r"--\s*$",  # SQL comment at end
            r"/\*.*\*/",  # Block comments
            r";\s*(DROP|DELETE|UPDATE|INSERT|CREATE|ALTER|EXEC)",  # Command stacking
            r"(UNION\s+ALL\s+SELECT|UNION\s+SELECT)",  # Union attacks
            r"(xp_|sp_|exec|execute)\s*\(",  # Stored procedure execution
            r"CHAR\s*\(\s*\d+",  # Character encoding bypass
            r"(0x[0-9A-Fa-f]+)",  # Hex encoding
            r"(SLEEP|BENCHMARK|WAITFOR|PG_SLEEP)\s*\(",  # Time-based attacks
            r"(LOAD_FILE|INTO\s+OUTFILE|INTO\s+DUMPFILE)",  # File operations
            r"(@@version|@@hostname|version\(\)|database\(\))",  # Information disclosure
            r"(INFORMATION_SCHEMA|mysql\.|pg_catalog\.|sys\.)",  # System tables
            r"[\'\"].*[\'\"];.*[\'\"]",  # String concatenation attacks
            r"CONCAT\s*\(.*CHAR\s*\(",  # Obfuscation attempts
        ]

        # Dangerous keywords that should be blocked
        self.dangerous_keywords = {
            "DROP", "TRUNCATE", "DELETE", "UPDATE", "INSERT", "CREATE",
            "ALTER", "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL",
            "SHUTDOWN", "KILL", "USE", "ATTACH", "DETACH"
        }

        # Read-only allowed operations
        self.readonly_operations = {"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH"}

        # Suspicious functions that could be used maliciously
        self.suspicious_functions = {
            "SLEEP", "BENCHMARK", "WAITFOR", "PG_SLEEP", "DELAY",
            "LOAD_FILE", "INTO", "OUTFILE", "DUMPFILE",
            "EXEC", "EXECUTE", "SYSTEM", "EVAL",
            "XP_CMDSHELL", "SP_CONFIGURE", "SP_ADDLOGIN"
        }

        # Maximum query complexity thresholds
        self.complexity_thresholds = {
            "max_joins": 5,
            "max_subqueries": 3,
            "max_union_statements": 2,
            "max_where_conditions": 10,
            "max_query_length": 10000,
            "max_identifiers": 20
        }

    def validate_query(
        self,
        query: str,
        read_only: bool = True,
        allow_params: bool = True,
        schema_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive SQL query validation.

        Args:
            query: SQL query to validate
            read_only: Enforce read-only operations
            allow_params: Allow parameterized queries
            schema_info: Optional schema information for validation

        Returns:
            Validation result with risk assessment:
            {
                "valid": bool,
                "risk_level": QueryRisk,
                "query_type": QueryType,
                "issues": List[str],
                "warnings": List[str],
                "complexity": Dict[str, int],
                "estimated_cost": Optional[float],
                "sanitized_query": str
            }
        """
        result = {
            "valid": True,
            "risk_level": QueryRisk.SAFE,
            "query_type": QueryType.UNKNOWN,
            "issues": [],
            "warnings": [],
            "complexity": {},
            "estimated_cost": None,
            "sanitized_query": query
        }

        try:
            # Basic validation
            if not query or not query.strip():
                result["valid"] = False
                result["issues"].append("Empty query")
                return result

            # Length check
            if len(query) > self.complexity_thresholds["max_query_length"]:
                result["valid"] = False
                result["risk_level"] = QueryRisk.HIGH
                result["issues"].append(f"Query too long ({len(query)} chars)")
                return result

            # Parse SQL
            parsed = sqlparse.parse(query)[0]

            # Detect query type
            query_type = self._detect_query_type(parsed)
            result["query_type"] = query_type

            # Check for SQL injection patterns
            injection_detected = self._detect_sql_injection(query)
            if injection_detected:
                result["valid"] = False
                result["risk_level"] = QueryRisk.BLOCKED
                result["issues"].extend(injection_detected)
                return result

            # Enforce read-only mode
            if read_only:
                if query_type not in [QueryType.SELECT, QueryType.UNKNOWN]:
                    result["valid"] = False
                    result["risk_level"] = QueryRisk.BLOCKED
                    result["issues"].append(f"Operation {query_type} not allowed in read-only mode")
                    return result

            # Check for dangerous operations
            dangerous_ops = self._detect_dangerous_operations(parsed)
            if dangerous_ops:
                result["valid"] = False
                result["risk_level"] = QueryRisk.CRITICAL
                result["issues"].extend(dangerous_ops)
                return result

            # Analyze query complexity
            complexity = self._analyze_complexity(parsed)
            result["complexity"] = complexity

            # Check complexity thresholds
            complexity_issues = self._check_complexity_thresholds(complexity)
            if complexity_issues:
                result["warnings"].extend(complexity_issues)
                result["risk_level"] = QueryRisk.MEDIUM

            # Validate table and column names against schema
            if schema_info:
                schema_issues = self._validate_against_schema(parsed, schema_info)
                if schema_issues:
                    result["warnings"].extend(schema_issues)

            # Estimate query cost
            if schema_info:
                result["estimated_cost"] = self._estimate_cost(parsed, complexity, schema_info)

            # Check for missing WHERE clause in UPDATE/DELETE
            if query_type in [QueryType.UPDATE, QueryType.DELETE]:
                if not self._has_where_clause(parsed):
                    result["risk_level"] = QueryRisk.HIGH
                    result["warnings"].append(f"{query_type} without WHERE clause affects all rows")

            # Parameter binding validation
            if allow_params:
                param_issues = self._validate_parameters(query)
                if param_issues:
                    result["warnings"].extend(param_issues)

            # Generate sanitized query (remove comments, normalize)
            result["sanitized_query"] = self._sanitize_query(query)

            # Set final risk level based on accumulated issues
            result["risk_level"] = self._calculate_final_risk(result)

        except Exception as e:
            logger.error(f"Query validation error: {str(e)}", exc_info=True)
            result["valid"] = False
            result["risk_level"] = QueryRisk.HIGH
            result["issues"].append(f"Validation error: {str(e)}")

        return result

    def _detect_query_type(self, parsed) -> QueryType:
        """Detect the type of SQL query"""
        query_upper = str(parsed).upper().strip()

        for token in parsed.tokens:
            if token.ttype in (DML, DDL, Keyword):
                keyword = token.value.upper()
                if keyword in ["SELECT", "WITH"]:
                    return QueryType.SELECT
                elif keyword == "INSERT":
                    return QueryType.INSERT
                elif keyword == "UPDATE":
                    return QueryType.UPDATE
                elif keyword == "DELETE":
                    return QueryType.DELETE
                elif keyword == "DROP":
                    return QueryType.DROP
                elif keyword == "CREATE":
                    return QueryType.CREATE
                elif keyword == "ALTER":
                    return QueryType.ALTER
                elif keyword == "TRUNCATE":
                    return QueryType.TRUNCATE
                elif keyword == "GRANT":
                    return QueryType.GRANT
                elif keyword == "REVOKE":
                    return QueryType.REVOKE
                elif keyword in ["EXEC", "EXECUTE", "CALL"]:
                    return QueryType.EXECUTE

        return QueryType.UNKNOWN

    def _detect_sql_injection(self, query: str) -> List[str]:
        """Detect potential SQL injection attempts"""
        issues = []
        query_upper = query.upper()

        # Check for injection patterns
        for pattern in self.injection_patterns:
            if re.search(pattern, query, re.IGNORECASE | re.MULTILINE):
                issues.append(f"Potential SQL injection pattern detected: {pattern}")

        # Check for suspicious character sequences
        if "''" in query or '""' in query:
            issues.append("Suspicious quote escaping detected")

        # Check for multiple statements
        if query.count(';') > 1:
            issues.append("Multiple SQL statements detected")

        # Check for suspicious encoding
        if any(enc in query_upper for enc in ["CHR(", "CHAR(", "ASCII(", "HEX("]):
            issues.append("Suspicious character encoding detected")

        # Check for system commands
        if any(cmd in query_upper for cmd in ["XP_", "SP_CONFIGURE", "@@"]):
            issues.append("System command or variable access detected")

        return issues

    def _detect_dangerous_operations(self, parsed) -> List[str]:
        """Detect dangerous SQL operations"""
        issues = []
        query_upper = str(parsed).upper()

        # Check for dangerous keywords
        for keyword in self.dangerous_keywords:
            if re.search(r'\b' + keyword + r'\b', query_upper):
                issues.append(f"Dangerous operation detected: {keyword}")

        # Check for suspicious functions
        for func in self.suspicious_functions:
            if func in query_upper:
                issues.append(f"Suspicious function detected: {func}")

        # Check for system table access
        system_tables = ["INFORMATION_SCHEMA", "MYSQL.", "PG_CATALOG.", "SYS."]
        for table in system_tables:
            if table in query_upper:
                issues.append(f"System table access detected: {table}")

        return issues

    def _analyze_complexity(self, parsed) -> Dict[str, int]:
        """Analyze query complexity metrics"""
        complexity = {
            "joins": 0,
            "subqueries": 0,
            "unions": 0,
            "where_conditions": 0,
            "group_by": 0,
            "order_by": 0,
            "distinct": 0,
            "aggregates": 0,
            "identifiers": 0
        }

        query_upper = str(parsed).upper()

        # Count JOINs
        complexity["joins"] = len(re.findall(r'\b(INNER|LEFT|RIGHT|FULL|CROSS)\s+JOIN\b', query_upper))

        # Count subqueries (simplified)
        complexity["subqueries"] = query_upper.count("(SELECT")

        # Count UNIONs
        complexity["unions"] = query_upper.count("UNION")

        # Count WHERE conditions (AND/OR)
        if "WHERE" in query_upper:
            complexity["where_conditions"] = query_upper.count(" AND ") + query_upper.count(" OR ") + 1

        # Count other complexity indicators
        complexity["group_by"] = 1 if "GROUP BY" in query_upper else 0
        complexity["order_by"] = 1 if "ORDER BY" in query_upper else 0
        complexity["distinct"] = 1 if "DISTINCT" in query_upper else 0

        # Count aggregate functions
        aggregates = ["COUNT(", "SUM(", "AVG(", "MIN(", "MAX(", "GROUP_CONCAT("]
        complexity["aggregates"] = sum(1 for agg in aggregates if agg in query_upper)

        # Count identifiers (tables and columns referenced)
        complexity["identifiers"] = len(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\b', query_upper))

        return complexity

    def _check_complexity_thresholds(self, complexity: Dict[str, int]) -> List[str]:
        """Check if query complexity exceeds thresholds"""
        warnings = []

        if complexity["joins"] > self.complexity_thresholds["max_joins"]:
            warnings.append(f"Too many JOINs ({complexity['joins']}), may impact performance")

        if complexity["subqueries"] > self.complexity_thresholds["max_subqueries"]:
            warnings.append(f"Too many subqueries ({complexity['subqueries']}), consider refactoring")

        if complexity["unions"] > self.complexity_thresholds["max_union_statements"]:
            warnings.append(f"Too many UNION statements ({complexity['unions']})")

        if complexity["where_conditions"] > self.complexity_thresholds["max_where_conditions"]:
            warnings.append(f"Complex WHERE clause with {complexity['where_conditions']} conditions")

        if complexity["identifiers"] > self.complexity_thresholds["max_identifiers"]:
            warnings.append(f"Too many table/column references ({complexity['identifiers']})")

        return warnings

    def _validate_against_schema(self, parsed, schema_info: Dict[str, Any]) -> List[str]:
        """Validate table and column names against known schema"""
        warnings = []

        # Extract table names from schema
        valid_tables = set()
        valid_columns = set()

        if "tables" in schema_info:
            for table in schema_info["tables"]:
                valid_tables.add(table["name"].lower())
                if "columns" in table:
                    for col in table["columns"]:
                        valid_columns.add(f"{table['name'].lower()}.{col['name'].lower()}")
                        valid_columns.add(col['name'].lower())

        # Parse query for table/column references (simplified)
        query_text = str(parsed).lower()

        # Check for invalid table references
        from_match = re.search(r'from\s+([a-zA-Z_][a-zA-Z0-9_]*)', query_text)
        if from_match:
            table_name = from_match.group(1)
            if valid_tables and table_name not in valid_tables:
                warnings.append(f"Unknown table: {table_name}")

        return warnings

    def _has_where_clause(self, parsed) -> bool:
        """Check if query has a WHERE clause"""
        for token in parsed.tokens:
            if isinstance(token, Where):
                return True
            if token.ttype is Keyword and token.value.upper() == "WHERE":
                return True
        return "WHERE" in str(parsed).upper()

    def _validate_parameters(self, query: str) -> List[str]:
        """Validate parameter placeholders in query"""
        warnings = []

        # Check for mix of parameter styles
        has_positional = "$" in query or "?" in query
        has_named = ":" in query and not "::" in query  # Exclude PostgreSQL casting

        if has_positional and has_named:
            warnings.append("Mixed parameter styles detected")

        # Check for unbound literals (potential injection points)
        # Look for string literals not in parameters
        string_literals = re.findall(r"'[^']*'", query)
        if string_literals and not (has_positional or has_named):
            warnings.append("String literals found without parameter binding")

        return warnings

    def _sanitize_query(self, query: str) -> str:
        """Sanitize query by removing comments and normalizing"""
        # Remove single-line comments
        query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)

        # Remove multi-line comments
        query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)

        # Normalize whitespace
        query = ' '.join(query.split())

        # Remove trailing semicolon
        query = query.rstrip(';').strip()

        return query

    def _estimate_cost(self, parsed, complexity: Dict[str, int], schema_info: Dict[str, Any]) -> float:
        """
        Estimate query cost based on complexity and schema.
        Returns a relative cost score (0-100).
        """
        cost = 0.0

        # Base cost by query type
        query_type = self._detect_query_type(parsed)
        if query_type == QueryType.SELECT:
            cost = 10.0
        else:
            cost = 20.0  # Higher base cost for modifications

        # Add cost for JOINs (exponential growth)
        cost += complexity["joins"] ** 2 * 5

        # Add cost for subqueries
        cost += complexity["subqueries"] * 15

        # Add cost for missing WHERE clause (full table scan)
        if not self._has_where_clause(parsed) and query_type == QueryType.SELECT:
            cost += 30

        # Add cost for DISTINCT
        if complexity["distinct"]:
            cost += 10

        # Add cost for GROUP BY
        if complexity["group_by"]:
            cost += 15

        # Add cost for ORDER BY
        if complexity["order_by"]:
            cost += 5

        # Estimate based on table sizes if available
        if schema_info and "tables" in schema_info:
            # Find referenced tables and their sizes
            for table in schema_info["tables"]:
                if table["name"].lower() in str(parsed).lower():
                    row_count = table.get("row_count", 1000)
                    if row_count > 10000:
                        cost += 20
                    elif row_count > 100000:
                        cost += 40

        # Cap at 100
        return min(cost, 100.0)

    def _calculate_final_risk(self, result: Dict[str, Any]) -> QueryRisk:
        """Calculate final risk level based on all findings"""
        if not result["valid"]:
            return QueryRisk.BLOCKED

        if result["issues"]:
            if any("injection" in issue.lower() for issue in result["issues"]):
                return QueryRisk.BLOCKED
            return QueryRisk.CRITICAL

        warning_count = len(result["warnings"])
        complexity_score = sum(result["complexity"].values())

        if warning_count > 3 or complexity_score > 20:
            return QueryRisk.HIGH
        elif warning_count > 1 or complexity_score > 10:
            return QueryRisk.MEDIUM
        elif warning_count > 0 or complexity_score > 5:
            return QueryRisk.LOW

        return QueryRisk.SAFE

    def validate_identifier(self, identifier: str) -> bool:
        """
        Validate a SQL identifier (table/column name).

        Args:
            identifier: Identifier to validate

        Returns:
            True if valid, False otherwise
        """
        # Allow alphanumeric, underscore, and dot (for schema.table)
        pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$'
        return bool(re.match(pattern, identifier))

    def escape_identifier(self, identifier: str, dialect: str = "postgresql") -> str:
        """
        Properly escape a SQL identifier.

        Args:
            identifier: Identifier to escape
            dialect: SQL dialect (postgresql, mysql, mssql)

        Returns:
            Escaped identifier
        """
        if not self.validate_identifier(identifier):
            raise ValueError(f"Invalid identifier: {identifier}")

        if dialect == "postgresql":
            # PostgreSQL uses double quotes
            return f'"{identifier}"'
        elif dialect == "mysql":
            # MySQL uses backticks
            return f"`{identifier}`"
        elif dialect == "mssql":
            # MSSQL uses square brackets
            return f"[{identifier}]"
        else:
            return identifier

    def generate_query_hash(self, query: str) -> str:
        """
        Generate a hash for query caching and deduplication.

        Args:
            query: SQL query

        Returns:
            SHA256 hash of normalized query
        """
        # Normalize query for consistent hashing
        normalized = self._sanitize_query(query).lower()

        # Remove whitespace variations
        normalized = re.sub(r'\s+', ' ', normalized)

        # Generate hash
        return hashlib.sha256(normalized.encode()).hexdigest()


# Global SQL validator instance
sql_validator = SQLValidator()