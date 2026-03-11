"""
Business Terminology Manager Service
Manages business term to database column mappings in DynamoDB.
Supports CRUD operations, synonyms, and automatic term discovery.
"""

import os
import time
import logging
import uuid
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class TerminologyManager:
    """
    Business terminology management service for database connectors.

    Features:
    - CRUD operations for business terms
    - Synonym management (e.g., "customer" → "client", "revenue" → "total_sales")
    - Domain-specific terminology (property management, sales, HR)
    - Automatic term discovery from queries
    - DynamoDB persistence with caching
    """

    def __init__(self):
        """Initialize terminology manager"""
        self._dynamodb = None  # Lazy initialization
        self._dynamodb_available = None
        self.environment = self._get_environment()

        # DynamoDB table for terminology
        self.table_name = f"contextuai-backend-db-terminology-{self.environment}"

        # In-memory cache for frequently used terms
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_timestamps: Dict[str, float] = {}
        self.cache_ttl = 3600  # 1 hour cache TTL

        logger.info(f"TerminologyManager initialized for environment: {self.environment}")

    @property
    def dynamodb(self):
        """Lazy initialization of DynamoDB resource with region fallback."""
        if self._dynamodb is None and self._dynamodb_available is not False:
            try:
                region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
                self._dynamodb = boto3.resource('dynamodb', region_name=region)
                self._dynamodb_available = True
            except Exception as e:
                logger.warning(f"DynamoDB not available for terminology: {e}")
                self._dynamodb_available = False
        return self._dynamodb

    def _get_environment(self) -> str:
        """Get current environment from env vars"""
        return os.getenv("ENVIRONMENT", "dev")

    async def create_term(
        self,
        database_id: str,
        business_term: str,
        table_name: str,
        column_name: str,
        synonyms: Optional[List[str]] = None,
        description: Optional[str] = None,
        domain: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new business term mapping.

        Args:
            database_id: Database/persona identifier
            business_term: Business term (e.g., "customer", "revenue")
            table_name: Database table name
            column_name: Database column name
            synonyms: Optional list of synonyms
            description: Optional term description
            domain: Optional domain (e.g., "property_management", "sales")
            created_by: Optional user ID who created the term

        Returns:
            Created term dictionary
        """
        try:
            table = self.dynamodb.Table(self.table_name)

            term_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()

            term_data = {
                "term_id": term_id,
                "database_id": database_id,
                "business_term": business_term.lower().strip(),
                "table_name": table_name,
                "column_name": column_name,
                "synonyms": synonyms or [],
                "description": description or "",
                "domain": domain or "general",
                "created_by": created_by or "system",
                "created_at": now,
                "updated_at": now,
                "usage_count": 0,
                "last_used_at": None,
                "is_active": True
            }

            # Store in DynamoDB
            table.put_item(Item=term_data)

            # Update cache
            cache_key = self._get_cache_key(database_id, business_term)
            self.cache[cache_key] = term_data
            self.cache_timestamps[cache_key] = time.time()

            logger.info(f"Created business term: '{business_term}' → {table_name}.{column_name}")

            return {
                "success": True,
                "term": term_data
            }

        except ClientError as e:
            logger.error(f"DynamoDB error creating term: {e}")
            return {
                "success": False,
                "error": f"Failed to create term: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error creating term: {e}")
            return {
                "success": False,
                "error": f"Failed to create term: {str(e)}"
            }

    async def get_term(
        self,
        database_id: str,
        business_term: str,
        check_synonyms: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get a business term mapping.

        Args:
            database_id: Database/persona identifier
            business_term: Business term to lookup
            check_synonyms: Whether to check synonyms if exact match not found

        Returns:
            Term dictionary or None if not found
        """
        try:
            # Normalize term
            normalized_term = business_term.lower().strip()

            # Check cache first
            cache_key = self._get_cache_key(database_id, normalized_term)
            if cache_key in self.cache:
                if time.time() - self.cache_timestamps.get(cache_key, 0) < self.cache_ttl:
                    logger.debug(f"Cache hit for term: {normalized_term}")
                    return self.cache[cache_key]

            # Query DynamoDB using GSI
            table = self.dynamodb.Table(self.table_name)

            response = table.query(
                IndexName="database_id-business_term-index",
                KeyConditionExpression="database_id = :db_id AND business_term = :term",
                ExpressionAttributeValues={
                    ":db_id": database_id,
                    ":term": normalized_term
                }
            )

            items = response.get("Items", [])

            if items:
                term_data = items[0]

                # Update cache
                self.cache[cache_key] = term_data
                self.cache_timestamps[cache_key] = time.time()

                logger.debug(f"Found term: '{normalized_term}' → {term_data['table_name']}.{term_data['column_name']}")
                return term_data

            # If not found and check_synonyms is True, search by synonyms
            if check_synonyms:
                synonym_result = await self._find_by_synonym(database_id, normalized_term)
                if synonym_result:
                    return synonym_result

            logger.debug(f"Term not found: {normalized_term}")
            return None

        except ClientError as e:
            logger.error(f"DynamoDB error getting term: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting term: {e}")
            return None

    async def _find_by_synonym(
        self,
        database_id: str,
        synonym: str
    ) -> Optional[Dict[str, Any]]:
        """Find term by synonym"""
        try:
            table = self.dynamodb.Table(self.table_name)

            # Scan for synonyms (not ideal but needed for synonym search)
            # In production, consider denormalizing synonyms for better performance
            response = table.query(
                IndexName="database_id-index",
                KeyConditionExpression="database_id = :db_id",
                ExpressionAttributeValues={
                    ":db_id": database_id
                }
            )

            for item in response.get("Items", []):
                synonyms = item.get("synonyms", [])
                if synonym in [s.lower() for s in synonyms]:
                    logger.debug(f"Found term by synonym: '{synonym}' → '{item['business_term']}'")
                    return item

            return None

        except Exception as e:
            logger.error(f"Error finding by synonym: {e}")
            return None

    async def update_term(
        self,
        term_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update a business term mapping.

        Args:
            term_id: Term ID to update
            updates: Dictionary of fields to update

        Returns:
            Updated term dictionary
        """
        try:
            table = self.dynamodb.Table(self.table_name)

            # Build update expression
            update_expr_parts = []
            expr_attr_values = {}
            expr_attr_names = {}

            allowed_fields = [
                "table_name", "column_name", "synonyms", "description",
                "domain", "is_active"
            ]

            for field, value in updates.items():
                if field in allowed_fields:
                    update_expr_parts.append(f"#{field} = :{field}")
                    expr_attr_names[f"#{field}"] = field
                    expr_attr_values[f":{field}"] = value

            # Always update updated_at
            update_expr_parts.append("#updated_at = :updated_at")
            expr_attr_names["#updated_at"] = "updated_at"
            expr_attr_values[":updated_at"] = datetime.utcnow().isoformat()

            if not update_expr_parts:
                return {
                    "success": False,
                    "error": "No valid fields to update"
                }

            update_expression = "SET " + ", ".join(update_expr_parts)

            # Update in DynamoDB
            response = table.update_item(
                Key={"term_id": term_id},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expr_attr_names,
                ExpressionAttributeValues=expr_attr_values,
                ReturnValues="ALL_NEW"
            )

            updated_term = response.get("Attributes", {})

            # Clear cache for this term
            database_id = updated_term.get("database_id")
            business_term = updated_term.get("business_term")
            if database_id and business_term:
                cache_key = self._get_cache_key(database_id, business_term)
                if cache_key in self.cache:
                    del self.cache[cache_key]
                    del self.cache_timestamps[cache_key]

            logger.info(f"Updated term: {term_id}")

            return {
                "success": True,
                "term": updated_term
            }

        except ClientError as e:
            logger.error(f"DynamoDB error updating term: {e}")
            return {
                "success": False,
                "error": f"Failed to update term: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error updating term: {e}")
            return {
                "success": False,
                "error": f"Failed to update term: {str(e)}"
            }

    async def delete_term(self, term_id: str) -> Dict[str, Any]:
        """
        Delete a business term mapping.

        Args:
            term_id: Term ID to delete

        Returns:
            Success/failure dictionary
        """
        try:
            table = self.dynamodb.Table(self.table_name)

            # Get term before deletion for cache clearing
            response = table.get_item(Key={"term_id": term_id})
            term = response.get("Item")

            if not term:
                return {
                    "success": False,
                    "error": "Term not found"
                }

            # Delete from DynamoDB
            table.delete_item(Key={"term_id": term_id})

            # Clear cache
            database_id = term.get("database_id")
            business_term = term.get("business_term")
            if database_id and business_term:
                cache_key = self._get_cache_key(database_id, business_term)
                if cache_key in self.cache:
                    del self.cache[cache_key]
                    del self.cache_timestamps[cache_key]

            logger.info(f"Deleted term: {term_id}")

            return {
                "success": True,
                "message": "Term deleted successfully"
            }

        except ClientError as e:
            logger.error(f"DynamoDB error deleting term: {e}")
            return {
                "success": False,
                "error": f"Failed to delete term: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error deleting term: {e}")
            return {
                "success": False,
                "error": f"Failed to delete term: {str(e)}"
            }

    async def list_terms(
        self,
        database_id: str,
        domain: Optional[str] = None,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List all business terms for a database.

        Args:
            database_id: Database/persona identifier
            domain: Optional domain filter
            active_only: Whether to return only active terms

        Returns:
            List of term dictionaries
        """
        try:
            table = self.dynamodb.Table(self.table_name)

            # Query using GSI
            response = table.query(
                IndexName="database_id-index",
                KeyConditionExpression="database_id = :db_id",
                ExpressionAttributeValues={
                    ":db_id": database_id
                }
            )

            terms = response.get("Items", [])

            # Apply filters
            if domain:
                terms = [t for t in terms if t.get("domain") == domain]

            if active_only:
                terms = [t for t in terms if t.get("is_active", True)]

            # Sort by usage count (most used first)
            terms.sort(key=lambda x: x.get("usage_count", 0), reverse=True)

            logger.debug(f"Listed {len(terms)} terms for database {database_id}")

            return terms

        except ClientError as e:
            logger.error(f"DynamoDB error listing terms: {e}")
            return []
        except Exception as e:
            logger.error(f"Error listing terms: {e}")
            return []

    async def record_usage(self, term_id: str):
        """
        Record usage of a business term.

        Args:
            term_id: Term ID to record usage for
        """
        try:
            table = self.dynamodb.Table(self.table_name)

            table.update_item(
                Key={"term_id": term_id},
                UpdateExpression="SET usage_count = usage_count + :inc, last_used_at = :now",
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":now": datetime.utcnow().isoformat()
                }
            )

            logger.debug(f"Recorded usage for term: {term_id}")

        except Exception as e:
            logger.error(f"Error recording usage: {e}")
            # Don't fail the operation if usage recording fails

    async def discover_terms(
        self,
        database_id: str,
        query_text: str
    ) -> List[str]:
        """
        Discover potential business terms from a natural language query.

        Args:
            database_id: Database/persona identifier
            query_text: Natural language query text

        Returns:
            List of discovered term strings
        """
        # Common business terms to look for
        common_terms = {
            # Property Management
            "property", "properties", "tenant", "tenants", "lease", "leases",
            "rent", "rental", "payment", "payments", "maintenance", "repair",
            "vacant", "occupied", "expense", "expenses", "income", "revenue",

            # Sales
            "customer", "customers", "client", "clients", "product", "products",
            "order", "orders", "sale", "sales", "invoice", "invoices",
            "revenue", "profit", "discount", "inventory", "stock",

            # HR
            "employee", "employees", "staff", "department", "salary",
            "payroll", "benefits", "leave", "attendance",

            # General
            "total", "sum", "count", "average", "max", "min",
            "recent", "latest", "last", "first", "top", "bottom"
        }

        # Extract words from query
        words = query_text.lower().split()

        # Find matching terms
        discovered = []
        for word in words:
            # Remove punctuation
            clean_word = ''.join(c for c in word if c.isalnum())

            if clean_word in common_terms:
                discovered.append(clean_word)

        # Remove duplicates while preserving order
        seen = set()
        unique_discovered = []
        for term in discovered:
            if term not in seen:
                seen.add(term)
                unique_discovered.append(term)

        if unique_discovered:
            logger.debug(f"Discovered terms in query: {unique_discovered}")

        return unique_discovered

    async def get_terms_as_dict(self, database_id: str) -> Dict[str, str]:
        """
        Get all terms as a dictionary mapping business term to column reference.

        Args:
            database_id: Database/persona identifier

        Returns:
            Dictionary: {business_term: "table.column"}
        """
        terms = await self.list_terms(database_id)

        term_dict = {}
        for term in terms:
            business_term = term.get("business_term", "")
            table_name = term.get("table_name", "")
            column_name = term.get("column_name", "")

            if business_term and table_name and column_name:
                term_dict[business_term] = f"{table_name}.{column_name}"

                # Add synonyms
                for synonym in term.get("synonyms", []):
                    term_dict[synonym.lower()] = f"{table_name}.{column_name}"

        return term_dict

    async def bulk_create_domain_terms(
        self,
        database_id: str,
        domain: str,
        created_by: str = "system"
    ) -> Dict[str, Any]:
        """
        Bulk create common business terms for a domain.

        Args:
            database_id: Database/persona identifier
            domain: Domain type (property_management, sales, hr)
            created_by: User ID who created the terms

        Returns:
            Dictionary with creation results
        """
        domain_terms = self._get_domain_term_templates(domain)

        created_count = 0
        failed_count = 0
        errors = []

        for term_config in domain_terms:
            result = await self.create_term(
                database_id=database_id,
                business_term=term_config["business_term"],
                table_name=term_config["table_name"],
                column_name=term_config["column_name"],
                synonyms=term_config.get("synonyms", []),
                description=term_config.get("description", ""),
                domain=domain,
                created_by=created_by
            )

            if result.get("success"):
                created_count += 1
            else:
                failed_count += 1
                errors.append(result.get("error", "Unknown error"))

        logger.info(f"Bulk created {created_count} terms for domain {domain} (failed: {failed_count})")

        return {
            "success": failed_count == 0,
            "created_count": created_count,
            "failed_count": failed_count,
            "errors": errors
        }

    def _get_domain_term_templates(self, domain: str) -> List[Dict[str, Any]]:
        """Get predefined term templates for a domain"""
        templates = {
            "property_management": [
                {
                    "business_term": "property",
                    "table_name": "properties",
                    "column_name": "property_id",
                    "synonyms": ["building", "unit", "home"],
                    "description": "Property identifier"
                },
                {
                    "business_term": "tenant",
                    "table_name": "tenants",
                    "column_name": "tenant_id",
                    "synonyms": ["renter", "resident"],
                    "description": "Tenant identifier"
                },
                {
                    "business_term": "rent",
                    "table_name": "leases",
                    "column_name": "monthly_rent",
                    "synonyms": ["rental", "monthly_payment"],
                    "description": "Monthly rent amount"
                },
                {
                    "business_term": "vacant",
                    "table_name": "properties",
                    "column_name": "property_status",
                    "synonyms": ["empty", "available"],
                    "description": "Property vacancy status"
                }
            ],
            "sales": [
                {
                    "business_term": "customer",
                    "table_name": "customers",
                    "column_name": "customer_id",
                    "synonyms": ["client", "buyer"],
                    "description": "Customer identifier"
                },
                {
                    "business_term": "revenue",
                    "table_name": "orders",
                    "column_name": "total_amount",
                    "synonyms": ["sales", "income"],
                    "description": "Total revenue/sales amount"
                },
                {
                    "business_term": "product",
                    "table_name": "products",
                    "column_name": "product_id",
                    "synonyms": ["item", "sku"],
                    "description": "Product identifier"
                }
            ]
        }

        return templates.get(domain, [])

    def _get_cache_key(self, database_id: str, business_term: str) -> str:
        """Generate cache key for a term"""
        return f"{database_id}:{business_term.lower()}"

    async def clear_cache(self, database_id: Optional[str] = None):
        """
        Clear terminology cache.

        Args:
            database_id: Optional database ID to clear specific cache
        """
        if database_id:
            # Clear specific database cache
            keys_to_remove = [k for k in self.cache.keys() if k.startswith(f"{database_id}:")]
            for key in keys_to_remove:
                del self.cache[key]
                if key in self.cache_timestamps:
                    del self.cache_timestamps[key]
            logger.info(f"Cleared terminology cache for database {database_id}")
        else:
            # Clear all cache
            self.cache.clear()
            self.cache_timestamps.clear()
            logger.info("Cleared all terminology cache")


# Global terminology manager instance
terminology_manager = TerminologyManager()
