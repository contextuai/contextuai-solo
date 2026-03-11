"""
Local Filesystem Storage Adapter

Stores files on the local filesystem for desktop mode.
Uses ``aiofiles`` for async I/O.
"""

import logging
import os
from pathlib import Path
from typing import List
from urllib.request import pathname2url

import aiofiles
import aiofiles.os

from adapters.storage_adapter import StorageAdapter

logger = logging.getLogger(__name__)

_DEFAULT_FILES_DIR = os.path.expanduser("~/.contextuai-solo/files")


class LocalStorageAdapter(StorageAdapter):
    """StorageAdapter backed by the local filesystem.

    Parameters
    ----------
    base_dir : str, optional
        Root directory for file storage.  Defaults to
        ``~/.contextuai-solo/files/``.
    """

    def __init__(self, base_dir: str = _DEFAULT_FILES_DIR) -> None:
        self.base_dir = base_dir

    def _resolve(self, file_path: str) -> str:
        """Resolve *file_path* relative to *base_dir* and ensure safety."""
        resolved = os.path.normpath(os.path.join(self.base_dir, file_path))
        # Prevent path-traversal attacks
        if not resolved.startswith(os.path.normpath(self.base_dir)):
            raise ValueError(f"Path traversal detected: {file_path}")
        return resolved

    async def upload_file(
        self, file_path: str, content: bytes, content_type: str = None
    ) -> str:
        full_path = self._resolve(file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)
        logger.debug("Stored file: %s (%d bytes)", full_path, len(content))
        return file_path

    async def download_file(self, file_path: str) -> bytes:
        full_path = self._resolve(file_path)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def delete_file(self, file_path: str) -> bool:
        full_path = self._resolve(file_path)
        if not os.path.isfile(full_path):
            return False
        await aiofiles.os.remove(full_path)
        logger.debug("Deleted file: %s", full_path)
        return True

    async def file_exists(self, file_path: str) -> bool:
        full_path = self._resolve(file_path)
        return os.path.isfile(full_path)

    async def list_files(self, prefix: str = "") -> List[str]:
        search_dir = self._resolve(prefix) if prefix else self.base_dir
        if not os.path.isdir(search_dir):
            return []
        results: List[str] = []
        for root, _dirs, files in os.walk(search_dir):
            for fname in files:
                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, self.base_dir)
                results.append(rel_path.replace("\\", "/"))
        return sorted(results)

    async def get_file_url(self, file_path: str) -> str:
        """Return a ``file:///`` URI for the file."""
        full_path = self._resolve(file_path)
        return "file:///" + pathname2url(os.path.abspath(full_path)).lstrip("/")
