"""
Authentication Adapters

Provides a common interface for authentication.  The desktop adapter
always returns an authenticated admin user; the enterprise adapter
delegates to the existing JWT/Cognito auth flow.
"""

from abc import ABC, abstractmethod
from typing import Optional


class AuthAdapter(ABC):
    """Abstract base class for authentication."""

    @abstractmethod
    async def authenticate(self, credentials: dict) -> Optional[dict]:
        """Authenticate with the given credentials. Returns user dict or ``None``."""
        ...

    @abstractmethod
    async def get_current_user(self, token: str = None) -> dict:
        """Return the currently authenticated user."""
        ...

    @abstractmethod
    async def is_authenticated(self, token: str = None) -> bool:
        """Return whether the current request is authenticated."""
        ...


class DesktopAuthAdapter(AuthAdapter):
    """Always returns an authenticated single-user admin for desktop mode."""

    DESKTOP_USER = {
        "id": "local-user",
        "email": "user@desktop.local",
        "name": "Solo User",
        "role": "admin",
        "organization": "local",
    }

    async def authenticate(self, credentials: dict) -> Optional[dict]:
        return self.DESKTOP_USER

    async def get_current_user(self, token: str = None) -> dict:
        return self.DESKTOP_USER

    async def is_authenticated(self, token: str = None) -> bool:
        return True


class EnterpriseAuthAdapter(AuthAdapter):
    """Wraps existing JWT / Cognito authentication for enterprise mode.

    This adapter is intentionally thin — the real authentication logic
    lives in the existing ``services/auth_service.py`` and middleware.
    These methods are stubs that signal callers to use the existing flow.
    """

    async def authenticate(self, credentials: dict) -> Optional[dict]:
        raise NotImplementedError("Use existing auth flow (POST /api/v1/auth/login)")

    async def get_current_user(self, token: str = None) -> dict:
        raise NotImplementedError("Use existing auth flow (JWT middleware)")

    async def is_authenticated(self, token: str = None) -> bool:
        raise NotImplementedError("Use existing auth flow (JWT middleware)")
