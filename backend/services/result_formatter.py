"""
Result Formatter Service
Provides comprehensive result formatting for database query responses.

Features:
- JSON formatting for API responses
- Streaming support for large results (>1000 rows)
- Data type conversion (dates, decimals, UUIDs, etc.)
- Null handling
- Aggregation summaries
- Result metadata (row count, execution time, etc.)
"""

import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
from datetime import datetime, date, time as dt_time
from decimal import Decimal
import uuid

logger = logging.getLogger(__name__)


class ResultFormatter:
    """
    Database query result formatter with comprehensive data type handling.

    Features:
    - JSON serialization with custom type converters
    - Streaming support for large datasets
    - Metadata generation
    - Data aggregation summaries
    - Performance optimization
    """

    def __init__(self):
        """Initialize result formatter"""
        # Streaming threshold (rows)
        self.streaming_threshold = 1000

        # Metrics
        self.metrics = {
            "total_formatted": 0,
            "streaming_responses": 0,
            "type_conversions": 0
        }

    def format_json_response(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        include_metadata: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Format query results as JSON-serializable dictionaries.

        Args:
            rows: List of result rows
            columns: Column names
            include_metadata: Whether to include additional metadata

        Returns:
            Formatted list of dictionaries
        """
        self.metrics["total_formatted"] += 1

        if not rows:
            return []

        formatted_rows = []

        for row in rows:
            formatted_row = {}

            for key, value in row.items():
                # Convert value to JSON-serializable format
                formatted_row[key] = self._convert_value(value)

            if include_metadata:
                formatted_row["_metadata"] = {
                    "column_count": len(columns),
                    "has_null_values": any(v is None for v in row.values())
                }

            formatted_rows.append(formatted_row)

        logger.debug(f"Formatted {len(formatted_rows)} rows with {len(columns)} columns")

        return formatted_rows

    def _convert_value(self, value: Any) -> Any:
        """
        Convert database value to JSON-serializable format.

        Args:
            value: Database value

        Returns:
            JSON-serializable value
        """
        if value is None:
            return None

        # Handle datetime types
        if isinstance(value, datetime):
            self.metrics["type_conversions"] += 1
            return value.isoformat()

        if isinstance(value, date):
            self.metrics["type_conversions"] += 1
            return value.isoformat()

        if isinstance(value, dt_time):
            self.metrics["type_conversions"] += 1
            return value.isoformat()

        # Handle Decimal (PostgreSQL NUMERIC, DECIMAL)
        if isinstance(value, Decimal):
            self.metrics["type_conversions"] += 1
            # Convert to float or string based on precision
            if value % 1 == 0:
                return int(value)
            return float(value)

        # Handle UUID
        if isinstance(value, uuid.UUID):
            self.metrics["type_conversions"] += 1
            return str(value)

        # Handle bytes (PostgreSQL bytea)
        if isinstance(value, bytes):
            self.metrics["type_conversions"] += 1
            try:
                return value.decode('utf-8')
            except UnicodeDecodeError:
                # If not UTF-8, return hex representation
                return value.hex()

        # Handle memoryview (PostgreSQL bytea)
        if isinstance(value, memoryview):
            self.metrics["type_conversions"] += 1
            return bytes(value).hex()

        # Handle dict (PostgreSQL JSON/JSONB)
        if isinstance(value, dict):
            return {k: self._convert_value(v) for k, v in value.items()}

        # Handle list/tuple (PostgreSQL ARRAY)
        if isinstance(value, (list, tuple)):
            return [self._convert_value(v) for v in value]

        # Handle bool explicitly (ensure it stays as bool, not int)
        if isinstance(value, bool):
            return value

        # Handle numeric types
        if isinstance(value, (int, float)):
            return value

        # Handle string types
        if isinstance(value, str):
            return value

        # Fallback: convert to string
        logger.debug(f"Unknown type {type(value)}, converting to string")
        return str(value)

    async def format_streaming_response(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        chunk_size: int = 100
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Format query results as streaming chunks.

        Args:
            rows: List of result rows
            columns: Column names
            chunk_size: Number of rows per chunk

        Yields:
            Chunks of formatted data:
            {
                "chunk": List[Dict],
                "chunk_number": int,
                "total_chunks": int,
                "is_final": bool
            }
        """
        self.metrics["streaming_responses"] += 1

        if not rows:
            yield {
                "chunk": [],
                "chunk_number": 0,
                "total_chunks": 0,
                "is_final": True
            }
            return

        total_rows = len(rows)
        total_chunks = (total_rows + chunk_size - 1) // chunk_size

        logger.info(f"Streaming {total_rows} rows in {total_chunks} chunks of {chunk_size}")

        for chunk_num in range(total_chunks):
            start_idx = chunk_num * chunk_size
            end_idx = min(start_idx + chunk_size, total_rows)

            chunk_rows = rows[start_idx:end_idx]
            formatted_chunk = self.format_json_response(chunk_rows, columns)

            yield {
                "chunk": formatted_chunk,
                "chunk_number": chunk_num + 1,
                "total_chunks": total_chunks,
                "rows_in_chunk": len(formatted_chunk),
                "total_rows": total_rows,
                "is_final": (chunk_num == total_chunks - 1)
            }

    def should_stream(self, row_count: int) -> bool:
        """
        Determine if results should be streamed based on size.

        Args:
            row_count: Number of rows in result

        Returns:
            True if streaming is recommended
        """
        return row_count > self.streaming_threshold

    def generate_metadata(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        execution_time_ms: float,
        from_cache: bool = False
    ) -> Dict[str, Any]:
        """
        Generate comprehensive result metadata.

        Args:
            rows: Query result rows
            columns: Column names
            execution_time_ms: Query execution time
            from_cache: Whether results came from cache

        Returns:
            Metadata dictionary
        """
        metadata = {
            "row_count": len(rows),
            "column_count": len(columns),
            "columns": columns,
            "execution_time_ms": execution_time_ms,
            "from_cache": from_cache,
            "data_types": {},
            "null_counts": {},
            "has_data": len(rows) > 0
        }

        # Analyze data types and null counts
        if rows:
            # Initialize counters
            null_counts = {col: 0 for col in columns}
            data_types = {}

            # Sample first row for types
            first_row = rows[0]
            for col in columns:
                if col in first_row:
                    value = first_row[col]
                    data_types[col] = self._get_type_name(value)

            # Count nulls
            for row in rows:
                for col in columns:
                    if col in row and row[col] is None:
                        null_counts[col] += 1

            metadata["data_types"] = data_types
            metadata["null_counts"] = null_counts

        return metadata

    def _get_type_name(self, value: Any) -> str:
        """
        Get human-readable type name for value.

        Args:
            value: Value to check

        Returns:
            Type name string
        """
        if value is None:
            return "null"

        if isinstance(value, bool):
            return "boolean"

        if isinstance(value, int):
            return "integer"

        if isinstance(value, float):
            return "float"

        if isinstance(value, Decimal):
            return "decimal"

        if isinstance(value, str):
            return "string"

        if isinstance(value, datetime):
            return "datetime"

        if isinstance(value, date):
            return "date"

        if isinstance(value, dt_time):
            return "time"

        if isinstance(value, uuid.UUID):
            return "uuid"

        if isinstance(value, (bytes, memoryview)):
            return "binary"

        if isinstance(value, dict):
            return "json"

        if isinstance(value, (list, tuple)):
            return "array"

        return "unknown"

    def generate_summary(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str]
    ) -> Dict[str, Any]:
        """
        Generate aggregation summary for numeric columns.

        Args:
            rows: Query result rows
            columns: Column names

        Returns:
            Summary statistics dictionary
        """
        summary = {
            "total_rows": len(rows),
            "columns": {},
            "has_numeric_data": False
        }

        if not rows:
            return summary

        # Identify numeric columns and calculate statistics
        for col in columns:
            numeric_values = []

            for row in rows:
                if col in row:
                    value = row[col]
                    if isinstance(value, (int, float, Decimal)) and value is not None:
                        numeric_values.append(float(value))

            if numeric_values:
                summary["has_numeric_data"] = True
                summary["columns"][col] = {
                    "type": "numeric",
                    "count": len(numeric_values),
                    "min": min(numeric_values),
                    "max": max(numeric_values),
                    "sum": sum(numeric_values),
                    "avg": sum(numeric_values) / len(numeric_values) if numeric_values else 0
                }

        return summary

    def format_error_response(
        self,
        error: str,
        query: Optional[str] = None,
        execution_time_ms: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Format error response.

        Args:
            error: Error message
            query: Optional query that failed
            execution_time_ms: Optional execution time

        Returns:
            Formatted error response
        """
        response = {
            "success": False,
            "error": error,
            "data": [],
            "metadata": {
                "row_count": 0,
                "columns": [],
                "has_data": False
            }
        }

        if execution_time_ms is not None:
            response["metadata"]["execution_time_ms"] = execution_time_ms

        if query:
            response["metadata"]["query_preview"] = query[:200] + ("..." if len(query) > 200 else "")

        return response

    def format_csv_response(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str]
    ) -> str:
        """
        Format query results as CSV string.

        Args:
            rows: Query result rows
            columns: Column names

        Returns:
            CSV formatted string
        """
        if not rows:
            return ",".join(columns) + "\n"

        lines = []

        # Header
        lines.append(",".join(f'"{col}"' for col in columns))

        # Data rows
        for row in rows:
            formatted_values = []
            for col in columns:
                value = row.get(col)
                formatted_value = self._convert_value(value)

                # CSV formatting
                if formatted_value is None:
                    formatted_values.append("")
                elif isinstance(formatted_value, str):
                    # Escape quotes
                    escaped = formatted_value.replace('"', '""')
                    formatted_values.append(f'"{escaped}"')
                else:
                    formatted_values.append(str(formatted_value))

            lines.append(",".join(formatted_values))

        return "\n".join(lines)

    def format_table_response(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        max_width: int = 50
    ) -> str:
        """
        Format query results as ASCII table.

        Args:
            rows: Query result rows
            columns: Column names
            max_width: Maximum column width

        Returns:
            ASCII table string
        """
        if not rows:
            return f"No results. Columns: {', '.join(columns)}"

        # Calculate column widths
        col_widths = {}
        for col in columns:
            col_widths[col] = min(len(col), max_width)

        for row in rows:
            for col in columns:
                value = row.get(col)
                formatted_value = str(self._convert_value(value)) if value is not None else "NULL"
                col_widths[col] = min(max(col_widths[col], len(formatted_value)), max_width)

        # Build table
        lines = []

        # Header separator
        separator = "+" + "+".join("-" * (width + 2) for width in col_widths.values()) + "+"
        lines.append(separator)

        # Header
        header = "|" + "|".join(
            f" {col:<{col_widths[col]}} " for col in columns
        ) + "|"
        lines.append(header)
        lines.append(separator)

        # Data rows
        for row in rows:
            row_values = []
            for col in columns:
                value = row.get(col)
                formatted_value = str(self._convert_value(value)) if value is not None else "NULL"

                # Truncate if too long
                if len(formatted_value) > max_width:
                    formatted_value = formatted_value[:max_width - 3] + "..."

                row_values.append(f" {formatted_value:<{col_widths[col]}} ")

            lines.append("|" + "|".join(row_values) + "|")

        lines.append(separator)

        # Add row count
        lines.append(f"\n{len(rows)} row(s) returned")

        return "\n".join(lines)

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get formatter metrics.

        Returns:
            Metrics dictionary
        """
        return {
            **self.metrics,
            "streaming_threshold": self.streaming_threshold
        }


# Global result formatter instance
result_formatter = ResultFormatter()
