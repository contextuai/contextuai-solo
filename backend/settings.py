"""
Application Configuration
Centralized configuration management for the ContextuAI backend.
Loads environment variables with sensible defaults for local development.
"""

import os
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Settings:
    """
    Application settings loaded from environment variables.

    Supports both local MongoDB (mongodb://mongodb:27017/contextuai)
    and MongoDB Atlas (mongodb+srv://...) connection strings.
    """

    # MongoDB Configuration
    mongodb_url: str = field(default_factory=lambda: os.getenv(
        "MONGODB_URL",
        "mongodb://mongodb:27017"
    ))
    database_name: str = field(default_factory=lambda: os.getenv(
        "DATABASE_NAME",
        "contextuai"
    ))

    # AWS Configuration
    aws_region: str = field(default_factory=lambda: os.getenv(
        "AWS_REGION",
        "us-east-1"
    ))
    aws_access_key_id: Optional[str] = field(default_factory=lambda: os.getenv(
        "AWS_ACCESS_KEY_ID"
    ))
    aws_secret_access_key: Optional[str] = field(default_factory=lambda: os.getenv(
        "AWS_SECRET_ACCESS_KEY"
    ))

    # Application Environment
    environment: str = field(default_factory=lambda: os.getenv(
        "ENVIRONMENT",
        "development"
    ))
    debug: bool = field(default_factory=lambda: os.getenv(
        "DEBUG",
        "true"
    ).lower() in ("true", "1", "yes"))

    # Server Configuration
    host: str = field(default_factory=lambda: os.getenv(
        "HOST",
        "0.0.0.0"
    ))
    port: int = field(default_factory=lambda: int(os.getenv(
        "PORT",
        "8000"
    )))

    # API Configuration
    api_prefix: str = field(default_factory=lambda: os.getenv(
        "API_PREFIX",
        "/api/v1"
    ))

    # CORS Configuration
    cors_origins: str = field(default_factory=lambda: os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:8000"
    ))

    # JWT/Auth Configuration (if needed)
    secret_key: str = field(default_factory=lambda: os.getenv(
        "SECRET_KEY",
        "dev-secret-key-change-in-production"
    ))

    @property
    def cors_origins_list(self) -> list:
        """Parse CORS origins from comma-separated string to list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() in ("production", "prod")

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() in ("development", "dev", "local")

    @property
    def is_atlas(self) -> bool:
        """Check if using MongoDB Atlas (cloud) connection."""
        return self.mongodb_url.startswith("mongodb+srv://")

    def get_mongodb_connection_string(self) -> str:
        """
        Get the full MongoDB connection string.
        For local MongoDB, appends database name if not present.
        For Atlas, returns as-is (database specified in connection options).
        """
        if self.is_atlas:
            return self.mongodb_url

        # For local MongoDB, ensure proper format
        url = self.mongodb_url.rstrip("/")
        return url


# Create a global settings instance
settings = Settings()


# Module-level convenience variables for backward compatibility
MONGODB_URL = settings.mongodb_url
DATABASE_NAME = settings.database_name
AWS_REGION = settings.aws_region
AWS_ACCESS_KEY_ID = settings.aws_access_key_id
AWS_SECRET_ACCESS_KEY = settings.aws_secret_access_key
ENVIRONMENT = settings.environment
DEBUG = settings.debug
