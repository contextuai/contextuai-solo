"""
Tests for backend/settings.py — Settings dataclass.

All tests are synchronous since Settings is a plain dataclass with no async logic.
"""

import os
import pytest


class TestSettingsDefaults:
    """Test default values when no environment variables are set."""

    def test_default_port(self, monkeypatch):
        monkeypatch.delenv("PORT", raising=False)
        from settings import Settings
        s = Settings()
        assert s.port == 18741

    def test_default_environment(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        from settings import Settings
        s = Settings()
        assert s.environment == "development"

    def test_default_debug_is_true(self, monkeypatch):
        monkeypatch.delenv("DEBUG", raising=False)
        from settings import Settings
        s = Settings()
        assert s.debug is True

    def test_default_host(self, monkeypatch):
        monkeypatch.delenv("HOST", raising=False)
        from settings import Settings
        s = Settings()
        assert s.host == "0.0.0.0"

    def test_default_api_prefix(self, monkeypatch):
        monkeypatch.delenv("API_PREFIX", raising=False)
        from settings import Settings
        s = Settings()
        assert s.api_prefix == "/api/v1"

    def test_default_mongodb_url(self, monkeypatch):
        monkeypatch.delenv("MONGODB_URL", raising=False)
        from settings import Settings
        s = Settings()
        assert s.mongodb_url == "mongodb://mongodb:27017"

    def test_default_database_name(self, monkeypatch):
        monkeypatch.delenv("DATABASE_NAME", raising=False)
        from settings import Settings
        s = Settings()
        assert s.database_name == "contextuai"

    def test_default_aws_region(self, monkeypatch):
        monkeypatch.delenv("AWS_REGION", raising=False)
        from settings import Settings
        s = Settings()
        assert s.aws_region == "us-east-1"

    def test_default_aws_keys_are_none(self, monkeypatch):
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
        monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
        from settings import Settings
        s = Settings()
        assert s.aws_access_key_id is None
        assert s.aws_secret_access_key is None

    def test_default_secret_key(self, monkeypatch):
        monkeypatch.delenv("SECRET_KEY", raising=False)
        from settings import Settings
        s = Settings()
        assert s.secret_key == "dev-secret-key-change-in-production"

    def test_default_cors_origins(self, monkeypatch):
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        from settings import Settings
        s = Settings()
        assert "http://localhost:1420" in s.cors_origins
        assert "http://127.0.0.1:18741" in s.cors_origins


class TestCorsOriginsList:
    """Test the cors_origins_list property."""

    def test_parses_comma_separated_origins(self):
        from settings import Settings
        s = Settings()
        s.cors_origins = "http://a.com,http://b.com,http://c.com"
        result = s.cors_origins_list
        assert result == ["http://a.com", "http://b.com", "http://c.com"]

    def test_strips_whitespace(self):
        from settings import Settings
        s = Settings()
        s.cors_origins = " http://a.com , http://b.com "
        result = s.cors_origins_list
        assert result == ["http://a.com", "http://b.com"]

    def test_filters_empty_strings(self):
        from settings import Settings
        s = Settings()
        s.cors_origins = "http://a.com,,http://b.com,"
        result = s.cors_origins_list
        assert result == ["http://a.com", "http://b.com"]

    def test_single_origin(self):
        from settings import Settings
        s = Settings()
        s.cors_origins = "http://localhost:3000"
        result = s.cors_origins_list
        assert result == ["http://localhost:3000"]

    def test_empty_string_returns_empty_list(self):
        from settings import Settings
        s = Settings()
        s.cors_origins = ""
        result = s.cors_origins_list
        assert result == []


class TestEnvironmentProperties:
    """Test is_production, is_development, is_atlas properties."""

    def test_is_development_default(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        from settings import Settings
        s = Settings()
        assert s.is_development is True
        assert s.is_production is False

    def test_is_development_with_dev(self):
        from settings import Settings
        s = Settings()
        s.environment = "dev"
        assert s.is_development is True

    def test_is_development_with_local(self):
        from settings import Settings
        s = Settings()
        s.environment = "local"
        assert s.is_development is True

    def test_is_production_with_production(self):
        from settings import Settings
        s = Settings()
        s.environment = "production"
        assert s.is_production is True
        assert s.is_development is False

    def test_is_production_with_prod(self):
        from settings import Settings
        s = Settings()
        s.environment = "prod"
        assert s.is_production is True

    def test_is_production_case_insensitive(self):
        from settings import Settings
        s = Settings()
        s.environment = "PRODUCTION"
        assert s.is_production is True

    def test_staging_is_neither(self):
        from settings import Settings
        s = Settings()
        s.environment = "staging"
        assert s.is_production is False
        assert s.is_development is False

    def test_is_atlas_with_srv_url(self):
        from settings import Settings
        s = Settings()
        s.mongodb_url = "mongodb+srv://user:pass@cluster.abc.mongodb.net"
        assert s.is_atlas is True

    def test_is_atlas_false_for_local(self):
        from settings import Settings
        s = Settings()
        s.mongodb_url = "mongodb://localhost:27017"
        assert s.is_atlas is False


class TestGetMongodbConnectionString:
    """Test get_mongodb_connection_string() method."""

    def test_atlas_url_returned_as_is(self):
        from settings import Settings
        s = Settings()
        atlas_url = "mongodb+srv://user:pass@cluster.abc.mongodb.net/mydb?retryWrites=true"
        s.mongodb_url = atlas_url
        assert s.get_mongodb_connection_string() == atlas_url

    def test_local_url_trailing_slash_stripped(self):
        from settings import Settings
        s = Settings()
        s.mongodb_url = "mongodb://localhost:27017/"
        result = s.get_mongodb_connection_string()
        assert result == "mongodb://localhost:27017"

    def test_local_url_no_trailing_slash(self):
        from settings import Settings
        s = Settings()
        s.mongodb_url = "mongodb://localhost:27017"
        result = s.get_mongodb_connection_string()
        assert result == "mongodb://localhost:27017"

    def test_local_url_multiple_trailing_slashes_stripped(self):
        from settings import Settings
        s = Settings()
        s.mongodb_url = "mongodb://localhost:27017///"
        result = s.get_mongodb_connection_string()
        assert not result.endswith("/")


class TestEnvironmentVariableOverrides:
    """Test that environment variables override defaults."""

    def test_port_override(self, monkeypatch):
        monkeypatch.setenv("PORT", "9999")
        from settings import Settings
        s = Settings()
        assert s.port == 9999

    def test_environment_override(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        from settings import Settings
        s = Settings()
        assert s.environment == "production"
        assert s.is_production is True

    def test_debug_false_override(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "false")
        from settings import Settings
        s = Settings()
        assert s.debug is False

    def test_debug_zero_override(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "0")
        from settings import Settings
        s = Settings()
        assert s.debug is False

    def test_debug_yes_override(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "yes")
        from settings import Settings
        s = Settings()
        assert s.debug is True

    def test_debug_one_override(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "1")
        from settings import Settings
        s = Settings()
        assert s.debug is True

    def test_host_override(self, monkeypatch):
        monkeypatch.setenv("HOST", "127.0.0.1")
        from settings import Settings
        s = Settings()
        assert s.host == "127.0.0.1"

    def test_mongodb_url_override(self, monkeypatch):
        monkeypatch.setenv("MONGODB_URL", "mongodb+srv://user:pass@cluster.net")
        from settings import Settings
        s = Settings()
        assert s.mongodb_url == "mongodb+srv://user:pass@cluster.net"
        assert s.is_atlas is True

    def test_database_name_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_NAME", "myapp_prod")
        from settings import Settings
        s = Settings()
        assert s.database_name == "myapp_prod"

    def test_aws_region_override(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        from settings import Settings
        s = Settings()
        assert s.aws_region == "eu-west-1"

    def test_aws_keys_override(self, monkeypatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secretvalue")
        from settings import Settings
        s = Settings()
        assert s.aws_access_key_id == "AKIAEXAMPLE"
        assert s.aws_secret_access_key == "secretvalue"

    def test_cors_origins_override(self, monkeypatch):
        monkeypatch.setenv("CORS_ORIGINS", "https://myapp.com")
        from settings import Settings
        s = Settings()
        assert s.cors_origins_list == ["https://myapp.com"]

    def test_api_prefix_override(self, monkeypatch):
        monkeypatch.setenv("API_PREFIX", "/api/v2")
        from settings import Settings
        s = Settings()
        assert s.api_prefix == "/api/v2"

    def test_secret_key_override(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "super-secret-prod-key")
        from settings import Settings
        s = Settings()
        assert s.secret_key == "super-secret-prod-key"
