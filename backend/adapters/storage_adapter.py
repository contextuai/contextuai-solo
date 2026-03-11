"""
Abstract Storage Adapter

Defines the interface for file storage operations. Implementations provide
S3 (enterprise) or local filesystem (desktop) backends.
"""

from abc import ABC, abstractmethod
from typing import List


class StorageAdapter(ABC):
    """Abstract base class for file storage."""

    @abstractmethod
    async def upload_file(
        self, file_path: str, content: bytes, content_type: str = None
    ) -> str:
        """Upload *content* to *file_path*. Returns a URI or key for the stored file."""
        ...

    @abstractmethod
    async def download_file(self, file_path: str) -> bytes:
        """Download the contents of *file_path*."""
        ...

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete the file at *file_path*. Returns ``True`` if deleted."""
        ...

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """Check whether *file_path* exists."""
        ...

    @abstractmethod
    async def list_files(self, prefix: str = "") -> List[str]:
        """List files whose paths start with *prefix*."""
        ...

    @abstractmethod
    async def get_file_url(self, file_path: str) -> str:
        """Return a URL (or URI) from which the file can be accessed."""
        ...
