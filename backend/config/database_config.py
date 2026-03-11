"""
Database Configuration
Centralized configuration for database connectors, connection pools, and caching.
"""

import os
from typing import Dict, Any
from enum import Enum


class Environment(str, Enum):
    """Environment types"""
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class DatabaseConfig:
    """
    Database connection and performance configuration per environment.

    Configuration Strategy:
    - Dev: Smaller pools, shorter timeouts, more aggressive cleanup
    - Staging: Medium pools, balanced timeouts
    - Prod: Larger pools, longer timeouts, optimized for high load
    """

    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "dev")
        self._load_config()

    def _load_config(self):
        """Load environment-specific configuration"""
        env_configs = {
            Environment.DEV: self._dev_config(),
            Environment.STAGING: self._staging_config(),
            Environment.PROD: self._prod_config()
        }

        config = env_configs.get(self.environment, self._dev_config())

        # Connection Pool Settings
        self.pool_config = config["pool"]

        # Query Execution Settings
        self.query_config = config["query"]

        # Cache Settings
        self.cache_config = config["cache"]

        # Monitoring Settings
        self.monitoring_config = config["monitoring"]

    def _dev_config(self) -> Dict[str, Any]:
        """Development environment configuration"""
        return {
            "pool": {
                # Connection pool sizes
                "min_size": 1,
                "max_size": 5,

                # Timeouts (seconds)
                "connection_timeout": 10,
                "command_timeout": 30,

                # Pool maintenance
                "pool_recycle": 1800,  # 30 minutes
                "max_inactive_connection_lifetime": 300.0,  # 5 minutes

                # Cleanup settings
                "idle_pool_ttl": 900,  # 15 minutes
                "pool_cleanup_interval": 180,  # 3 minutes
            },
            "query": {
                # Query execution limits
                "default_timeout": 30,  # 30 seconds
                "max_timeout": 60,  # 1 minute

                # Row limits
                "default_row_limit": 1000,
                "max_row_limit": 5000,

                # Batch settings
                "batch_size": 100,
            },
            "cache": {
                # Schema cache TTL (seconds)
                "schema_cache_ttl": 1800,  # 30 minutes

                # Query cache TTL (seconds)
                "query_cache_ttl": 300,  # 5 minutes

                # Terminology cache TTL (seconds)
                "terminology_cache_ttl": 3600,  # 1 hour

                # Memory cache settings
                "max_memory_cache_items": 100,
                "memory_cache_ttl": 600,  # 10 minutes

                # DynamoDB cache settings
                "enable_dynamodb_cache": True,
                "cache_compression": False,
            },
            "monitoring": {
                # Metrics collection
                "enable_metrics": True,
                "metrics_interval": 60,  # 1 minute

                # Performance monitoring
                "slow_query_threshold_ms": 1000,  # 1 second
                "enable_query_logging": True,

                # Health checks
                "health_check_interval": 300,  # 5 minutes
            }
        }

    def _staging_config(self) -> Dict[str, Any]:
        """Staging environment configuration"""
        return {
            "pool": {
                # Connection pool sizes
                "min_size": 2,
                "max_size": 10,

                # Timeouts (seconds)
                "connection_timeout": 15,
                "command_timeout": 45,

                # Pool maintenance
                "pool_recycle": 3600,  # 1 hour
                "max_inactive_connection_lifetime": 600.0,  # 10 minutes

                # Cleanup settings
                "idle_pool_ttl": 1800,  # 30 minutes
                "pool_cleanup_interval": 300,  # 5 minutes
            },
            "query": {
                # Query execution limits
                "default_timeout": 45,  # 45 seconds
                "max_timeout": 120,  # 2 minutes

                # Row limits
                "default_row_limit": 2000,
                "max_row_limit": 10000,

                # Batch settings
                "batch_size": 200,
            },
            "cache": {
                # Schema cache TTL (seconds)
                "schema_cache_ttl": 3600,  # 1 hour

                # Query cache TTL (seconds)
                "query_cache_ttl": 600,  # 10 minutes

                # Terminology cache TTL (seconds)
                "terminology_cache_ttl": 7200,  # 2 hours

                # Memory cache settings
                "max_memory_cache_items": 200,
                "memory_cache_ttl": 900,  # 15 minutes

                # DynamoDB cache settings
                "enable_dynamodb_cache": True,
                "cache_compression": True,
            },
            "monitoring": {
                # Metrics collection
                "enable_metrics": True,
                "metrics_interval": 60,  # 1 minute

                # Performance monitoring
                "slow_query_threshold_ms": 2000,  # 2 seconds
                "enable_query_logging": True,

                # Health checks
                "health_check_interval": 300,  # 5 minutes
            }
        }

    def _prod_config(self) -> Dict[str, Any]:
        """Production environment configuration"""
        return {
            "pool": {
                # Connection pool sizes
                "min_size": 5,
                "max_size": 20,

                # Timeouts (seconds)
                "connection_timeout": 20,
                "command_timeout": 60,

                # Pool maintenance
                "pool_recycle": 7200,  # 2 hours
                "max_inactive_connection_lifetime": 1800.0,  # 30 minutes

                # Cleanup settings
                "idle_pool_ttl": 3600,  # 1 hour
                "pool_cleanup_interval": 600,  # 10 minutes
            },
            "query": {
                # Query execution limits
                "default_timeout": 60,  # 1 minute
                "max_timeout": 180,  # 3 minutes

                # Row limits
                "default_row_limit": 5000,
                "max_row_limit": 50000,

                # Batch settings
                "batch_size": 500,
            },
            "cache": {
                # Schema cache TTL (seconds)
                "schema_cache_ttl": 7200,  # 2 hours

                # Query cache TTL (seconds)
                "query_cache_ttl": 1800,  # 30 minutes

                # Terminology cache TTL (seconds)
                "terminology_cache_ttl": 14400,  # 4 hours

                # Memory cache settings
                "max_memory_cache_items": 500,
                "memory_cache_ttl": 1800,  # 30 minutes

                # DynamoDB cache settings
                "enable_dynamodb_cache": True,
                "cache_compression": True,
            },
            "monitoring": {
                # Metrics collection
                "enable_metrics": True,
                "metrics_interval": 30,  # 30 seconds

                # Performance monitoring
                "slow_query_threshold_ms": 3000,  # 3 seconds
                "enable_query_logging": True,

                # Health checks
                "health_check_interval": 180,  # 3 minutes
            }
        }

    def get_pool_config(self, db_type: str = "postgresql") -> Dict[str, Any]:
        """
        Get connection pool configuration for specific database type.

        Args:
            db_type: Database type (postgresql, mysql, mssql, snowflake)

        Returns:
            Pool configuration dictionary
        """
        base_config = self.pool_config.copy()

        # Database-specific overrides
        if db_type == "postgresql":
            # PostgreSQL works well with asyncpg defaults
            pass
        elif db_type == "mysql":
            # MySQL may need slightly different settings
            base_config["pool_recycle"] = min(base_config["pool_recycle"], 3600)
        elif db_type == "mssql":
            # MSSQL through ODBC may need more conservative settings
            base_config["max_size"] = min(base_config["max_size"], 10)
            base_config["connection_timeout"] = max(base_config["connection_timeout"], 30)
        elif db_type == "snowflake":
            # Snowflake cloud data warehouse may need different settings
            # Snowflake handles connection pooling differently, optimize for cloud latency
            base_config["connection_timeout"] = max(base_config["connection_timeout"], 30)
            base_config["command_timeout"] = max(base_config["command_timeout"], 60)

        return base_config

    def get_query_config(self) -> Dict[str, Any]:
        """Get query execution configuration"""
        return self.query_config.copy()

    def get_cache_config(self, cache_type: str = "schema") -> Dict[str, Any]:
        """
        Get cache configuration for specific cache type.

        Args:
            cache_type: Type of cache (schema, query, terminology)

        Returns:
            Cache configuration dictionary
        """
        config = self.cache_config.copy()

        # Add cache-specific TTL key for convenience
        if cache_type == "schema":
            config["ttl"] = config["schema_cache_ttl"]
        elif cache_type == "query":
            config["ttl"] = config["query_cache_ttl"]
        elif cache_type == "terminology":
            config["ttl"] = config["terminology_cache_ttl"]

        return config

    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring configuration"""
        return self.monitoring_config.copy()


# Global database configuration instance
db_config = DatabaseConfig()


# Convenience functions for direct access
def get_pool_config(db_type: str = "postgresql") -> Dict[str, Any]:
    """Get connection pool configuration"""
    return db_config.get_pool_config(db_type)


def get_query_config() -> Dict[str, Any]:
    """Get query execution configuration"""
    return db_config.get_query_config()


def get_cache_config(cache_type: str = "schema") -> Dict[str, Any]:
    """Get cache configuration"""
    return db_config.get_cache_config(cache_type)


def get_monitoring_config() -> Dict[str, Any]:
    """Get monitoring configuration"""
    return db_config.get_monitoring_config()
