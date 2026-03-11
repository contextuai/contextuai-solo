"""
File Storage Service for ContextuAI

Handles file uploads, storage, and cleanup for user-attached files.
Currently uses local /tmp storage; S3 integration planned for future.
"""

import os
import uuid
import shutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import asyncio
from threading import Lock

logger = logging.getLogger(__name__)

# Configuration
UPLOAD_BASE_DIR = "/tmp/contextuai/uploads"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {
    # Text files
    '.txt', '.md', '.json', '.xml', '.csv', '.yaml', '.yml',
    # Code files
    '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.sql',
    # Documents
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    # Images (for vision models)
    '.png', '.jpg', '.jpeg', '.gif', '.webp',
    # Data files
    '.log', '.conf', '.ini', '.env'
}
FILE_RETENTION_HOURS = 24  # Files older than this will be cleaned up


class FileStorageService:
    """Service for managing file uploads and storage."""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Singleton pattern for file storage service."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize file storage service."""
        if self._initialized:
            return

        self.base_dir = Path(UPLOAD_BASE_DIR)
        self.metadata_file = self.base_dir / ".metadata.json"
        self._metadata_cache: Dict[str, Dict[str, Any]] = {}

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Load existing metadata
        self._load_metadata()

        self._initialized = True
        logger.info(f"FileStorageService initialized. Base dir: {self.base_dir}")

    def _load_metadata(self):
        """Load file metadata from disk."""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    self._metadata_cache = json.load(f)
                logger.info(f"Loaded metadata for {len(self._metadata_cache)} files")
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")
            self._metadata_cache = {}

    def _save_metadata(self):
        """Save file metadata to disk."""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self._metadata_cache, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")

    async def upload_file(
        self,
        user_id: str,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upload a file for a user.

        Args:
            user_id: User identifier
            filename: Original filename
            content: File content as bytes
            content_type: MIME type (optional)

        Returns:
            Dict with file_id, path, and metadata
        """
        # Validate file size
        if len(content) > MAX_FILE_SIZE:
            raise ValueError(f"File size {len(content)} exceeds maximum {MAX_FILE_SIZE} bytes")

        # Validate file extension
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"File type {ext} not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

        # Generate unique file ID
        file_id = str(uuid.uuid4())

        # Create user directory
        user_dir = self.base_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        # Safe filename: file_id + original extension
        safe_filename = f"{file_id}{ext}"
        file_path = user_dir / safe_filename

        # Write file
        try:
            with open(file_path, 'wb') as f:
                f.write(content)
        except Exception as e:
            logger.error(f"Error writing file: {e}")
            raise IOError(f"Failed to save file: {e}")

        # Create metadata
        metadata = {
            "file_id": file_id,
            "user_id": user_id,
            "original_filename": filename,
            "stored_filename": safe_filename,
            "path": str(file_path),
            "size": len(content),
            "content_type": content_type or self._guess_content_type(ext),
            "extension": ext,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
            "expires_at": (datetime.utcnow() + timedelta(hours=FILE_RETENTION_HOURS)).isoformat() + "Z"
        }

        # Store metadata
        self._metadata_cache[file_id] = metadata
        self._save_metadata()

        logger.info(f"Uploaded file: {file_id} ({filename}, {len(content)} bytes)")

        return metadata

    def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a file by ID."""
        return self._metadata_cache.get(file_id)

    def get_file_path(self, file_id: str) -> Optional[str]:
        """Get the file path for a file ID."""
        metadata = self.get_file_metadata(file_id)
        if metadata:
            path = metadata.get("path")
            if path and os.path.exists(path):
                return path
        return None

    async def get_file_content(self, file_id: str) -> Optional[bytes]:
        """Get file content by ID."""
        path = self.get_file_path(file_id)
        if path:
            try:
                with open(path, 'rb') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading file {file_id}: {e}")
        return None

    def get_user_files(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all files for a user."""
        return [
            meta for meta in self._metadata_cache.values()
            if meta.get("user_id") == user_id
        ]

    async def delete_file(self, file_id: str) -> bool:
        """Delete a file by ID."""
        metadata = self._metadata_cache.get(file_id)
        if not metadata:
            return False

        path = metadata.get("path")
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"Deleted file: {file_id}")
            except Exception as e:
                logger.error(f"Error deleting file {file_id}: {e}")
                return False

        # Remove from metadata
        del self._metadata_cache[file_id]
        self._save_metadata()

        return True

    async def cleanup_expired_files(self) -> int:
        """
        Clean up files older than retention period.

        Returns:
            Number of files cleaned up
        """
        now = datetime.utcnow()
        expired_files = []

        for file_id, metadata in self._metadata_cache.items():
            expires_at = metadata.get("expires_at")
            if expires_at:
                try:
                    expire_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00").replace("+00:00", ""))
                    if now > expire_time:
                        expired_files.append(file_id)
                except Exception as e:
                    logger.warning(f"Error parsing expiry for {file_id}: {e}")

        # Delete expired files
        deleted = 0
        for file_id in expired_files:
            if await self.delete_file(file_id):
                deleted += 1

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired files")

        return deleted

    def _guess_content_type(self, ext: str) -> str:
        """Guess MIME type from extension."""
        content_types = {
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.csv': 'text/csv',
            '.yaml': 'text/yaml',
            '.yml': 'text/yaml',
            '.py': 'text/x-python',
            '.js': 'application/javascript',
            '.ts': 'application/typescript',
            '.html': 'text/html',
            '.css': 'text/css',
            '.sql': 'application/sql',
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }
        return content_types.get(ext, 'application/octet-stream')

    def get_upload_directory(self) -> str:
        """Get the base upload directory path."""
        return str(self.base_dir)


# Global instance
file_storage_service = FileStorageService()
