"""
Authentication Service for JWT validation with AWS Cognito and API Key support.
Validates JWT tokens and API keys, and extracts user information.
"""

import os
import json
import time
from typing import Dict, Optional, Any
from functools import lru_cache
import jwt
from jwt import PyJWKClient
import requests
from fastapi import HTTPException, Security, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

logger = logging.getLogger(__name__)

# Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "us-east-1_shvh4unI0")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "7k5b6t061bgdsiba4e3vklktq3")

# Local JWT Configuration (for backend-issued tokens)
# Check multiple env var names for compatibility
JWT_SECRET = os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET_KEY") or os.getenv("NEXTAUTH_SECRET") or "your-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"

# Cognito issuer URL
COGNITO_ISSUER = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"

# Security scheme for FastAPI — auto_error=False so we can fall through to API key check
security = HTTPBearer(auto_error=False)

# Cache for JWKS client (refresh every hour)
@lru_cache(maxsize=1)
def get_jwks_client():
    """Get cached JWKS client for token validation"""
    return PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)

class AuthService:
    """Service for handling authentication and authorization"""

    @staticmethod
    def decode_local_token(token: str) -> Optional[Dict[str, Any]]:
        """
        Try to decode a locally-issued JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload or None if not a local token
        """
        try:
            payload = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=[JWT_ALGORITHM],
                options={"verify_exp": True}
            )
            # Check if it's a local token (has 'type' field)
            if payload.get("type") in ["access", "refresh"]:
                return payload
            return None
        except Exception:
            return None

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """
        Decode and validate a JWT token.
        First tries local backend-issued JWT, then falls back to Cognito.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid or expired
        """
        # First try to decode as a local token
        local_payload = AuthService.decode_local_token(token)
        if local_payload:
            logger.debug("Validated local JWT token")
            return local_payload

        # Fall back to Cognito token validation
        try:
            # Get JWKS client
            jwks_client = get_jwks_client()

            # Get signing key from JWT
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # Decode and validate token
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=COGNITO_CLIENT_ID,
                issuer=COGNITO_ISSUER,
                options={"verify_exp": True}
            )

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @staticmethod
    def extract_user_info(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract user information from token payload.
        Handles both local backend tokens and Cognito tokens.

        Args:
            payload: Decoded JWT payload

        Returns:
            User information dictionary
        """
        # Check if this is a local token (has 'type' field)
        is_local_token = payload.get("type") in ["access", "refresh"]

        if is_local_token:
            # Local token format - fields are at top level
            return {
                "user_id": payload.get("user_id") or payload.get("sub"),
                "email": payload.get("email"),
                "email_verified": True,  # Assumed verified for local auth
                "username": payload.get("email"),
                "token_use": payload.get("type"),
                "auth_time": payload.get("iat"),
                "exp": payload.get("exp"),
                "iat": payload.get("iat"),
                "role": payload.get("role", "standardUser"),
                "organization": payload.get("organization"),
                "department": payload.get("department"),
                "groups": [],
                "custom_attributes": {}
            }

        # Cognito token format
        # Extract standard claims
        user_info = {
            "user_id": payload.get("sub"),  # Cognito user ID (UUID)
            "email": payload.get("email"),
            "email_verified": payload.get("email_verified", False),
            "username": payload.get("cognito:username", payload.get("email")),
            "token_use": payload.get("token_use"),  # 'id' or 'access'
            "auth_time": payload.get("auth_time"),
            "exp": payload.get("exp"),
            "iat": payload.get("iat")
        }

        # Extract custom attributes if present
        custom_attrs = {}
        for key, value in payload.items():
            if key.startswith("custom:"):
                attr_name = key.replace("custom:", "")
                custom_attrs[attr_name] = value

        # Add custom attributes to user info
        if custom_attrs:
            user_info["custom_attributes"] = custom_attrs
            # Also extract commonly used custom attributes to top level
            user_info["role"] = custom_attrs.get("role", "standardUser")
            user_info["organization"] = custom_attrs.get("organization")
            user_info["department"] = custom_attrs.get("department")
        else:
            # Default values if no custom attributes
            user_info["role"] = "standardUser"
            user_info["organization"] = None
            user_info["department"] = None

        # Extract Cognito groups if present
        user_info["groups"] = payload.get("cognito:groups", [])

        return user_info

    @staticmethod
    def validate_role(user_info: Dict[str, Any], required_roles: list) -> bool:
        """
        Validate if user has one of the required roles

        Args:
            user_info: User information from token
            required_roles: List of allowed roles

        Returns:
            True if user has required role, False otherwise
        """
        user_role = user_info.get("role", "standardUser")

        # Define role hierarchy (higher roles include lower permissions)
        role_hierarchy = {
            "superAdmin": 5,
            "admin": 4,
            "engineer": 3,
            "powerUser": 2,
            "standardUser": 1
        }

        user_level = role_hierarchy.get(user_role, 1)

        for required_role in required_roles:
            required_level = role_hierarchy.get(required_role, 1)
            if user_level >= required_level:
                return True

        return False

    @staticmethod
    def validate_organization(user_info: Dict[str, Any], organization: str) -> bool:
        """
        Validate if user belongs to specified organization

        Args:
            user_info: User information from token
            organization: Required organization

        Returns:
            True if user belongs to organization, False otherwise
        """
        user_org = user_info.get("organization")
        return user_org == organization if user_org else False

# FastAPI dependency for getting current user (supports Bearer JWT + API Key)
async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> Dict[str, Any]:
    """
    FastAPI dependency to get current authenticated user.

    Supports two auth methods (checked in order):
      1. X-API-Key header → validated via ApiKeyService
      2. Authorization: Bearer <jwt> → validated via JWT (local then Cognito)

    Returns:
        User information extracted from token or API key

    Raises:
        HTTPException: If authentication fails
    """
    # Skip authentication for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        logger.info("[DEBUG Auth] OPTIONS request - skipping authentication for CORS preflight")
        return {}

    # ------------------------------------------------------------------
    # 1. Try API Key authentication (X-API-Key header)
    # ------------------------------------------------------------------
    api_key = request.headers.get("X-API-Key")
    if api_key:
        logger.info("[DEBUG Auth] X-API-Key header detected, attempting API key auth")
        try:
            from database import get_database
            from repositories.api_key_repository import ApiKeyRepository
            from services.api_key_service import ApiKeyService

            db = await get_database()
            api_key_service = ApiKeyService(ApiKeyRepository(db))
            client_ip = request.client.host if request.client else None
            user_context = await api_key_service.validate_key(api_key, client_ip=client_ip)

            if user_context:
                logger.info(f"Authenticated via API key: {user_context.get('api_key_name')} (user {user_context.get('user_id')})")
                # Return user context that matches the JWT user_info shape
                return {
                    "user_id": user_context["user_id"],
                    "email": None,  # API keys don't carry email
                    "role": user_context["role"],
                    "organization": None,
                    "department": None,
                    "auth_type": "api_key",
                    "scopes": user_context["scopes"],
                    "api_key_id": user_context["api_key_id"],
                    "api_key_name": user_context["api_key_name"],
                    "rate_limit_per_minute": user_context["rate_limit_per_minute"],
                }
            else:
                logger.warning("[DEBUG Auth] Invalid or expired API key")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired API key",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[DEBUG Auth] API key validation error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key validation failed",
            )

    # ------------------------------------------------------------------
    # 2. Fall back to Bearer JWT authentication
    # ------------------------------------------------------------------
    logger.info("[DEBUG Auth] Incoming authentication request")
    logger.info(f"[DEBUG Auth] Authorization header present: {credentials is not None}")

    if not credentials:
        logger.error("[DEBUG Auth] No credentials provided - missing Authorization header and X-API-Key")
        origin = request.headers.get("origin", "")
        cors_headers = {
            "WWW-Authenticate": "Bearer",
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Credentials": "true",
        }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated - provide Authorization header or X-API-Key",
            headers=cors_headers,
        )

    token = credentials.credentials
    logger.info(f"[DEBUG Auth] Token received - Length: {len(token) if token else 0}, Preview: {token[:20] if token else 'NONE'}...")

    # Decode and validate token
    auth_service = AuthService()

    try:
        payload = auth_service.decode_token(token)
        logger.info(f"[DEBUG Auth] Token decoded successfully. Payload keys: {list(payload.keys())}")
    except HTTPException as e:
        logger.error(f"[DEBUG Auth] Token decode failed: {str(e.detail)}")
        origin = request.headers.get("origin", "")
        cors_headers = {
            **e.headers,
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Credentials": "true",
        }
        raise HTTPException(
            status_code=e.status_code,
            detail=e.detail,
            headers=cors_headers,
        )
    except Exception as e:
        logger.error(f"[DEBUG Auth] Token decode failed with unexpected error: {str(e)}")
        origin = request.headers.get("origin", "")
        cors_headers = {
            "WWW-Authenticate": "Bearer",
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Credentials": "true",
        }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers=cors_headers,
        )

    # Extract user information
    user_info = auth_service.extract_user_info(payload)
    user_info["auth_type"] = "jwt"

    logger.info(f"[DEBUG Auth] User info extracted:")
    logger.info(f"  - Email: {user_info.get('email')}")
    logger.info(f"  - User ID (sub): {user_info.get('user_id')}")
    logger.info(f"  - Role from token: {user_info.get('role')}")
    logger.info(f"  - Has custom attributes: {bool(user_info.get('custom_attributes'))}")

    if user_info.get('custom_attributes'):
        logger.info(f"  - Custom attributes: {user_info.get('custom_attributes')}")

    logger.info(f"Authenticated user: {user_info.get('email')} (ID: {user_info.get('user_id')})")

    return user_info

# Role-based access control dependencies
def require_role(*allowed_roles):
    """
    Create a dependency that requires specific roles

    Args:
        allowed_roles: Roles that are allowed to access the endpoint

    Returns:
        FastAPI dependency function
    """
    async def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)):
        auth_service = AuthService()
        if not auth_service.validate_role(current_user, list(allowed_roles)):
            logger.warning(f"Access denied for user {current_user.get('email')} - requires role(s): {allowed_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker

# Convenience role dependencies
require_admin = require_role("admin", "superAdmin")
require_power_user = require_role("powerUser", "admin", "superAdmin")
require_engineer = require_role("engineer", "admin", "superAdmin")

# Optional authentication (returns None if no token or API key)
async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> Optional[Dict[str, Any]]:
    """
    Optional authentication - returns user if authenticated, None otherwise.
    Supports both Bearer JWT and X-API-Key.

    Returns:
        User information or None
    """
    # Try API key first
    api_key = request.headers.get("X-API-Key")
    if api_key:
        try:
            from database import get_database
            from repositories.api_key_repository import ApiKeyRepository
            from services.api_key_service import ApiKeyService

            db = await get_database()
            api_key_service = ApiKeyService(ApiKeyRepository(db))
            client_ip = request.client.host if request.client else None
            user_context = await api_key_service.validate_key(api_key, client_ip=client_ip)
            if user_context:
                return {
                    "user_id": user_context["user_id"],
                    "email": None,
                    "role": user_context["role"],
                    "auth_type": "api_key",
                    "scopes": user_context["scopes"],
                    "api_key_id": user_context["api_key_id"],
                    "api_key_name": user_context["api_key_name"],
                    "rate_limit_per_minute": user_context["rate_limit_per_minute"],
                }
        except Exception:
            return None

    # Fall back to Bearer JWT
    if not credentials:
        return None

    try:
        token = credentials.credentials
        auth_service = AuthService()
        payload = auth_service.decode_token(token)
        user_info = auth_service.extract_user_info(payload)
        user_info["auth_type"] = "jwt"
        return user_info
    except HTTPException:
        return None
    except Exception:
        return None