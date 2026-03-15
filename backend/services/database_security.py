"""
Database Security Service
Provides comprehensive security controls for database operations including
audit logging, rate limiting, access control, and sensitive data protection.

Security Features:
- Read-only connection enforcement
- Query audit logging to DynamoDB
- Rate limiting per user
- Sensitive data masking
- Access control validation
- Query timeout enforcement
- Row limit enforcement
"""

import time
import json
import logging
import hashlib
import re
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)


class AccessLevel(str, Enum):
    """Database access levels"""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    ADMIN = "admin"


class AuditEventType(str, Enum):
    """Audit event types"""
    QUERY_EXECUTED = "query_executed"
    QUERY_BLOCKED = "query_blocked"
    ACCESS_DENIED = "access_denied"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SENSITIVE_DATA_ACCESS = "sensitive_data_access"
    ERROR = "error"


class DataClassification(str, Enum):
    """Data sensitivity classifications"""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class DatabaseSecurity:
    """
    Database security manager with comprehensive protection features.

    Features:
    - Multi-layered access control
    - Query audit logging
    - Rate limiting
    - Sensitive data protection
    - Connection security
    - Compliance tracking
    """

    def __init__(self):
        """Initialize database security manager"""
        self._dynamodb = None  # Lazy initialization
        self._dynamodb_available = None
        self._audit_table = None

        # Get environment
        import os
        self.environment = os.getenv("ENVIRONMENT", "dev")

        # DynamoDB table names
        self.audit_table_name = f"contextuai-backend-query-audit-{self.environment}"

    @property
    def dynamodb(self):
        """Lazy initialization of DynamoDB resource with region fallback."""
        if self._dynamodb is None and self._dynamodb_available is not False:
            try:
                import os
                region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
                self._dynamodb = boto3.resource('dynamodb', region_name=region)
                self._dynamodb_available = True
            except Exception as e:
                logger.warning(f"DynamoDB not available for audit logging: {e}")
                self._dynamodb_available = False
        return self._dynamodb

    @property
    def audit_table(self):
        """Lazy initialization of audit table."""
        if self._audit_table is None and self.dynamodb is not None:
            self._audit_table = self.dynamodb.Table(self.audit_table_name)
        return self._audit_table

        # Rate limiting configuration
        self.rate_limits = {
            AccessLevel.READ_ONLY: {
                "queries_per_minute": 100,
                "queries_per_hour": 1000,
                "max_concurrent": 5
            },
            AccessLevel.READ_WRITE: {
                "queries_per_minute": 50,
                "queries_per_hour": 500,
                "max_concurrent": 3
            },
            AccessLevel.ADMIN: {
                "queries_per_minute": 200,
                "queries_per_hour": 2000,
                "max_concurrent": 10
            }
        }

        # Rate limit tracking (in-memory for performance)
        self.rate_limiter = defaultdict(lambda: {
            "minute_window": [],
            "hour_window": [],
            "concurrent": 0
        })

        # Sensitive data patterns
        self.sensitive_patterns = {
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b',
            "credit_card": r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "api_key": r'[A-Za-z0-9]{32,}',
            "password": r'password|passwd|pwd',
            "token": r'token|bearer|jwt',
            "secret": r'secret|private_key|api_key'
        }

        # Sensitive column patterns
        self.sensitive_columns = {
            "ssn", "social_security", "tax_id", "credit_card", "card_number",
            "cvv", "pin", "password", "passwd", "pwd", "token", "api_key",
            "secret", "private_key", "encryption_key", "salt", "hash",
            "email", "phone", "mobile", "address", "dob", "date_of_birth",
            "salary", "compensation", "bank_account", "routing_number"
        }

        # Compliance requirements
        self.compliance_checks = {
            "gdpr": ["email", "phone", "address", "dob"],
            "pci": ["credit_card", "card_number", "cvv"],
            "hipaa": ["ssn", "medical_record", "patient_id"]
        }

    async def validate_access(
        self,
        user_id: str,
        persona_id: str,
        query: str,
        access_level: AccessLevel = AccessLevel.READ_ONLY
    ) -> Dict[str, Any]:
        """
        Validate user access for database operation.

        Args:
            user_id: User identifier
            persona_id: Persona/database identifier
            query: SQL query to execute
            access_level: Required access level

        Returns:
            Validation result:
            {
                "allowed": bool,
                "access_level": AccessLevel,
                "reason": Optional[str],
                "warnings": List[str]
            }
        """
        result = {
            "allowed": True,
            "access_level": access_level,
            "reason": None,
            "warnings": []
        }

        try:
            # Check if user has access to persona
            if not await self._check_persona_access(user_id, persona_id):
                result["allowed"] = False
                result["reason"] = f"User {user_id} does not have access to persona {persona_id}"
                await self._log_audit_event(
                    user_id=user_id,
                    persona_id=persona_id,
                    event_type=AuditEventType.ACCESS_DENIED,
                    details={"reason": result["reason"]}
                )
                return result

            # Check rate limits
            rate_check = await self._check_rate_limit(user_id, access_level)
            if not rate_check["allowed"]:
                result["allowed"] = False
                result["reason"] = rate_check["reason"]
                await self._log_audit_event(
                    user_id=user_id,
                    persona_id=persona_id,
                    event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
                    details=rate_check
                )
                return result

            # Check query permissions based on access level
            if access_level == AccessLevel.READ_ONLY:
                # Validate query is read-only
                query_upper = query.upper()
                write_operations = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
                for op in write_operations:
                    if op in query_upper:
                        result["allowed"] = False
                        result["reason"] = f"Write operation '{op}' not allowed with read-only access"
                        return result

            # Check for sensitive data access
            sensitive_cols = self._detect_sensitive_columns(query)
            if sensitive_cols:
                result["warnings"].append(f"Query accesses sensitive columns: {', '.join(sensitive_cols)}")
                await self._log_audit_event(
                    user_id=user_id,
                    persona_id=persona_id,
                    event_type=AuditEventType.SENSITIVE_DATA_ACCESS,
                    details={"sensitive_columns": list(sensitive_cols)}
                )

            # Increment concurrent query counter
            self.rate_limiter[user_id]["concurrent"] += 1

        except Exception as e:
            logger.error(f"Access validation error: {str(e)}", exc_info=True)
            result["allowed"] = False
            result["reason"] = "Access validation failed"

        return result

    async def _check_persona_access(self, user_id: str, persona_id: str) -> bool:
        """Check if user has access to specific persona. Solo: always True (single user)."""
        return True

    async def _check_rate_limit(self, user_id: str, access_level: AccessLevel) -> Dict[str, Any]:
        """Check rate limits for user"""
        limits = self.rate_limits[access_level]
        user_limits = self.rate_limiter[user_id]
        current_time = time.time()

        # Clean old entries
        minute_ago = current_time - 60
        hour_ago = current_time - 3600

        user_limits["minute_window"] = [t for t in user_limits["minute_window"] if t > minute_ago]
        user_limits["hour_window"] = [t for t in user_limits["hour_window"] if t > hour_ago]

        # Check per-minute limit
        if len(user_limits["minute_window"]) >= limits["queries_per_minute"]:
            return {
                "allowed": False,
                "reason": f"Rate limit exceeded: {limits['queries_per_minute']} queries per minute",
                "retry_after": 60 - (current_time - user_limits["minute_window"][0])
            }

        # Check per-hour limit
        if len(user_limits["hour_window"]) >= limits["queries_per_hour"]:
            return {
                "allowed": False,
                "reason": f"Rate limit exceeded: {limits['queries_per_hour']} queries per hour",
                "retry_after": 3600 - (current_time - user_limits["hour_window"][0])
            }

        # Check concurrent query limit
        if user_limits["concurrent"] >= limits["max_concurrent"]:
            return {
                "allowed": False,
                "reason": f"Concurrent query limit exceeded: {limits['max_concurrent']} concurrent queries",
                "retry_after": 5
            }

        # Add current request to windows
        user_limits["minute_window"].append(current_time)
        user_limits["hour_window"].append(current_time)

        return {"allowed": True}

    def _detect_sensitive_columns(self, query: str) -> Set[str]:
        """Detect sensitive columns in query"""
        sensitive_found = set()
        query_lower = query.lower()

        for col in self.sensitive_columns:
            if col in query_lower:
                sensitive_found.add(col)

        return sensitive_found

    async def _log_audit_event(
        self,
        user_id: str,
        persona_id: str,
        event_type: AuditEventType,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log audit event to DynamoDB"""
        try:
            timestamp = datetime.utcnow().isoformat()
            event_id = hashlib.sha256(f"{user_id}-{persona_id}-{timestamp}".encode()).hexdigest()[:16]

            item = {
                "event_id": event_id,
                "user_id": user_id,
                "persona_id": persona_id,
                "event_type": event_type.value,
                "timestamp": timestamp,
                "details": json.dumps(details) if details else None
            }

            await self._write_to_dynamodb(self.audit_table, item)

        except Exception as e:
            logger.error(f"Failed to log audit event: {str(e)}", exc_info=True)

    async def log_query_execution(
        self,
        user_id: str,
        persona_id: str,
        query: str,
        query_hash: str,
        execution_time_ms: float,
        row_count: int,
        success: bool,
        error: Optional[str] = None
    ):
        """
        Log query execution details for audit.

        Args:
            user_id: User identifier
            persona_id: Persona/database identifier
            query: Executed SQL query
            query_hash: Hash of the query
            execution_time_ms: Query execution time
            row_count: Number of rows returned/affected
            success: Whether query succeeded
            error: Error message if failed
        """
        try:
            timestamp = datetime.utcnow().isoformat()
            event_id = hashlib.sha256(f"{user_id}-{query_hash}-{timestamp}".encode()).hexdigest()[:16]

            # Truncate query if too long for DynamoDB
            max_query_length = 4000
            truncated_query = query[:max_query_length] if len(query) > max_query_length else query

            item = {
                "event_id": event_id,
                "user_id": user_id,
                "persona_id": persona_id,
                "event_type": AuditEventType.QUERY_EXECUTED.value,
                "timestamp": timestamp,
                "query_hash": query_hash,
                "query": truncated_query,
                "execution_time_ms": execution_time_ms,
                "row_count": row_count,
                "success": success,
                "error": error
            }

            await self._write_to_dynamodb(self.audit_table, item)

            # Decrement concurrent counter
            if user_id in self.rate_limiter:
                self.rate_limiter[user_id]["concurrent"] = max(0, self.rate_limiter[user_id]["concurrent"] - 1)

        except Exception as e:
            logger.error(f"Failed to log query execution: {str(e)}", exc_info=True)

    async def _write_to_dynamodb(self, table, item: Dict[str, Any]):
        """Write item to DynamoDB table"""
        try:
            # DynamoDB operations in FastAPI should be sync for now
            # In production, use aioboto3 for true async
            table.put_item(Item=item)
        except Exception as e:
            logger.error(f"DynamoDB write error: {str(e)}", exc_info=True)
            raise

    def mask_sensitive_data(self, data: List[Dict[str, Any]], columns: List[str]) -> List[Dict[str, Any]]:
        """
        Mask sensitive data in query results.

        Args:
            data: Query result rows
            columns: Column names

        Returns:
            Data with sensitive values masked
        """
        if not data:
            return data

        masked_data = []
        sensitive_cols = set()

        # Identify sensitive columns
        for col in columns:
            col_lower = col.lower()
            if any(sensitive in col_lower for sensitive in self.sensitive_columns):
                sensitive_cols.add(col)

        # Mask sensitive data
        for row in data:
            masked_row = row.copy()
            for col in sensitive_cols:
                if col in masked_row and masked_row[col]:
                    masked_row[col] = self._mask_value(masked_row[col], col.lower())

            # Also check values for sensitive patterns
            for col, value in masked_row.items():
                if value and isinstance(value, str):
                    for pattern_name, pattern in self.sensitive_patterns.items():
                        if re.search(pattern, str(value), re.IGNORECASE):
                            masked_row[col] = self._mask_value(value, pattern_name)
                            break

            masked_data.append(masked_row)

        return masked_data

    def _mask_value(self, value: Any, data_type: str) -> str:
        """Mask sensitive value based on type"""
        if value is None:
            return None

        value_str = str(value)

        if "ssn" in data_type or "social" in data_type:
            # Show last 4 digits only
            if len(value_str) >= 4:
                return f"***-**-{value_str[-4:]}"
            return "***"

        elif "credit" in data_type or "card" in data_type:
            # Show first 4 and last 4 digits
            if len(value_str) >= 8:
                return f"{value_str[:4]}****{value_str[-4:]}"
            return "****"

        elif "email" in data_type:
            # Show first letter and domain
            parts = value_str.split('@')
            if len(parts) == 2:
                return f"{parts[0][0]}***@{parts[1]}"
            return "***@***"

        elif "phone" in data_type:
            # Show area code only
            if len(value_str) >= 10:
                return f"{value_str[:3]}-***-****"
            return "***"

        else:
            # Generic masking
            if len(value_str) > 4:
                return value_str[0] + "*" * (len(value_str) - 2) + value_str[-1]
            return "*" * len(value_str)

    def enforce_row_limit(self, row_count: int, max_rows: int) -> bool:
        """
        Enforce row limit for query results.

        Args:
            row_count: Number of rows to return
            max_rows: Maximum allowed rows

        Returns:
            True if within limit, False otherwise
        """
        return row_count <= max_rows

    def validate_connection_security(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate database connection security settings.

        Args:
            credentials: Database connection credentials

        Returns:
            Validation result with security recommendations
        """
        result = {
            "secure": True,
            "issues": [],
            "recommendations": []
        }

        # Check for SSL/TLS
        if not credentials.get("ssl_enabled", False):
            result["issues"].append("Connection not using SSL/TLS encryption")
            result["recommendations"].append("Enable SSL/TLS for encrypted connections")
            result["secure"] = False

        # Check for plaintext password
        if "password" in credentials and credentials["password"]:
            # Password should be from Secrets Manager, not plaintext
            if not credentials.get("from_secrets_manager", False):
                result["issues"].append("Password not from secure storage")
                result["recommendations"].append("Store credentials in AWS Secrets Manager")
                result["secure"] = False

        # Check for default ports
        default_ports = {5432: "PostgreSQL", 3306: "MySQL", 1433: "MSSQL"}
        port = credentials.get("port")
        if port in default_ports:
            result["recommendations"].append(f"Consider using non-default port (currently {port})")

        # Check for public endpoints
        host = credentials.get("host", "")
        if any(public in host for public in ["0.0.0.0", "public", "external"]):
            result["issues"].append("Database appears to be publicly accessible")
            result["recommendations"].append("Use VPC endpoints or private subnets")
            result["secure"] = False

        return result

    async def get_audit_logs(
        self,
        user_id: Optional[str] = None,
        persona_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_type: Optional[AuditEventType] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs based on filters.

        Args:
            user_id: Filter by user
            persona_id: Filter by persona
            start_time: Start time for query
            end_time: End time for query
            event_type: Filter by event type
            limit: Maximum records to return

        Returns:
            List of audit log entries
        """
        try:
            # Build query based on filters
            if user_id:
                # Query by user_id GSI
                response = self.audit_table.query(
                    IndexName='user_id-timestamp-index',
                    KeyConditionExpression=Key('user_id').eq(user_id),
                    Limit=limit,
                    ScanIndexForward=False  # Most recent first
                )
            else:
                # Scan with filters (less efficient, use sparingly)
                scan_kwargs = {'Limit': limit}
                filter_expressions = []

                if persona_id:
                    filter_expressions.append(Key('persona_id').eq(persona_id))
                if event_type:
                    filter_expressions.append(Key('event_type').eq(event_type.value))

                if filter_expressions:
                    scan_kwargs['FilterExpression'] = filter_expressions[0]
                    for expr in filter_expressions[1:]:
                        scan_kwargs['FilterExpression'] = scan_kwargs['FilterExpression'] & expr

                response = self.audit_table.scan(**scan_kwargs)

            return response.get('Items', [])

        except Exception as e:
            logger.error(f"Failed to retrieve audit logs: {str(e)}", exc_info=True)
            return []

    def check_compliance_requirements(
        self,
        data_accessed: List[str],
        compliance_framework: str = "gdpr"
    ) -> Dict[str, Any]:
        """
        Check if data access meets compliance requirements.

        Args:
            data_accessed: List of data fields accessed
            compliance_framework: Compliance framework to check (gdpr, pci, hipaa)

        Returns:
            Compliance check result
        """
        result = {
            "compliant": True,
            "framework": compliance_framework,
            "sensitive_data_accessed": [],
            "requirements": []
        }

        if compliance_framework not in self.compliance_checks:
            result["requirements"].append(f"Unknown compliance framework: {compliance_framework}")
            return result

        sensitive_fields = self.compliance_checks[compliance_framework]

        for field in data_accessed:
            field_lower = field.lower()
            for sensitive in sensitive_fields:
                if sensitive in field_lower:
                    result["sensitive_data_accessed"].append(field)
                    result["requirements"].append(f"{compliance_framework.upper()}: Accessing {sensitive} requires audit logging")

        if result["sensitive_data_accessed"]:
            result["requirements"].append(f"Ensure {compliance_framework.upper()} compliance for sensitive data access")

        return result

    def generate_security_report(self, user_id: str, period_days: int = 7) -> Dict[str, Any]:
        """
        Generate security report for user activity.

        Args:
            user_id: User to generate report for
            period_days: Number of days to include

        Returns:
            Security report with metrics and recommendations
        """
        report = {
            "user_id": user_id,
            "period_days": period_days,
            "generated_at": datetime.utcnow().isoformat(),
            "metrics": {
                "total_queries": 0,
                "blocked_queries": 0,
                "sensitive_data_accesses": 0,
                "rate_limit_violations": 0,
                "failed_queries": 0
            },
            "recommendations": []
        }

        # This would query audit logs and compile metrics
        # Implementation depends on actual audit log structure

        return report


# Global database security instance
database_security = DatabaseSecurity()