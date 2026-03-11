"""
Artifact Service for AI Team Workspace Feature

Provides file management for workspace project artifacts,
including file storage, retrieval, and ZIP packaging.
"""

import os
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class ArtifactService:
    """
    Service for managing workspace artifacts.

    Provides methods for saving, retrieving, and packaging
    project artifacts (generated code, documents, etc.).
    """

    # Default artifacts path (can be overridden by environment variable)
    ARTIFACTS_PATH = os.getenv("WORKSPACE_ARTIFACTS_PATH", "/app/artifacts")

    # Maximum file size (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024

    # Allowed file extensions
    ALLOWED_EXTENSIONS = {
        # Code files
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb", ".php",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala",
        # Web files
        ".html", ".css", ".scss", ".sass", ".less", ".vue", ".svelte",
        # Config files
        ".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".env", ".conf",
        # Documentation
        ".md", ".txt", ".rst", ".adoc",
        # Document exports
        ".pdf", ".pptx", ".docx",
        # Data files
        ".csv", ".sql",
        # Shell scripts
        ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
        # Other
        ".dockerfile", ".gitignore", ".editorconfig"
    }

    def __init__(self):
        """Initialize the artifact service."""
        # Per-project path overrides (e.g. git clone directories)
        self._path_overrides: dict = {}
        # Ensure base artifacts directory exists
        self._ensure_base_directory()

    def _ensure_base_directory(self) -> None:
        """Ensure the base artifacts directory exists."""
        try:
            Path(self.ARTIFACTS_PATH).mkdir(parents=True, exist_ok=True)
            logger.debug(f"Artifacts directory ready: {self.ARTIFACTS_PATH}")
        except Exception as e:
            logger.error(f"Failed to create artifacts directory: {e}")

    def get_project_path(self, project_id: str) -> str:
        """
        Get artifacts directory path for a project.

        Args:
            project_id: ID of the project

        Returns:
            Absolute path to project's artifacts directory
        """
        if project_id in self._path_overrides:
            return self._path_overrides[project_id]
        return os.path.join(self.ARTIFACTS_PATH, project_id)

    async def initialize_directory(
        self, project_id: str, base_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initialize (or override) the artifacts directory for a project.

        When *base_path* is provided the artifact service will read/write to
        that directory instead of the default ``ARTIFACTS_PATH/project_id``.
        This is used by the git integration so that agents write directly into
        the cloned repository.

        Args:
            project_id: ID of the project
            base_path: Optional override path

        Returns:
            Dictionary with 'success' boolean and 'path'
        """
        if base_path:
            self._path_overrides[project_id] = base_path
            Path(base_path).mkdir(parents=True, exist_ok=True)
            logger.info(
                f"Artifact path override for {project_id}: {base_path}"
            )
            return {"success": True, "path": base_path}
        return await self.create_project_directory(project_id)

    async def create_project_directory(self, project_id: str) -> Dict[str, Any]:
        """
        Create artifacts directory for a project.

        Args:
            project_id: ID of the project

        Returns:
            Dictionary with 'success' boolean and 'path' or 'error'
        """
        try:
            project_path = self.get_project_path(project_id)
            Path(project_path).mkdir(parents=True, exist_ok=True)

            logger.info(f"Created artifacts directory for project {project_id}")

            return {
                "success": True,
                "path": project_path
            }

        except Exception as e:
            logger.error(f"Error creating project directory: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def save_file(
        self,
        project_id: str,
        filename: str,
        content: str
    ) -> Dict[str, Any]:
        """
        Save file to project artifacts directory.

        Args:
            project_id: ID of the project
            filename: Name of the file (can include subdirectories)
            content: File content as string

        Returns:
            Dictionary with 'success' boolean, 'path', 'size', or 'error'
        """
        try:
            # Validate filename
            if not filename or filename.startswith("..") or filename.startswith("/"):
                return {
                    "success": False,
                    "error": "Invalid filename"
                }

            # Check file extension
            ext = Path(filename).suffix.lower()
            if ext and ext not in self.ALLOWED_EXTENSIONS:
                # Allow files without extension (like Dockerfile, Makefile)
                base_name = Path(filename).name.lower()
                allowed_no_ext = {"dockerfile", "makefile", "procfile", "gemfile", "rakefile"}
                if base_name not in allowed_no_ext:
                    return {
                        "success": False,
                        "error": f"File extension '{ext}' not allowed"
                    }

            # Check content size
            content_bytes = content.encode("utf-8")
            if len(content_bytes) > self.MAX_FILE_SIZE:
                return {
                    "success": False,
                    "error": f"File exceeds maximum size of {self.MAX_FILE_SIZE} bytes"
                }

            # Ensure project directory exists
            project_path = self.get_project_path(project_id)
            await self.create_project_directory(project_id)

            # Create subdirectories if needed
            file_path = os.path.join(project_path, filename)
            file_dir = os.path.dirname(file_path)
            if file_dir:
                Path(file_dir).mkdir(parents=True, exist_ok=True)

            # Write the file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            file_size = os.path.getsize(file_path)

            logger.debug(f"Saved file {filename} ({file_size} bytes) for project {project_id}")

            return {
                "success": True,
                "path": file_path,
                "filename": filename,
                "size": file_size
            }

        except Exception as e:
            logger.error(f"Error saving file: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def read_file(
        self,
        project_id: str,
        filename: str
    ) -> Dict[str, Any]:
        """
        Read file from project artifacts directory.

        Args:
            project_id: ID of the project
            filename: Name of the file

        Returns:
            Dictionary with 'success', 'content', 'size', or 'error'
        """
        try:
            file_path = os.path.join(self.get_project_path(project_id), filename)

            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": "File not found"
                }

            if not os.path.isfile(file_path):
                return {
                    "success": False,
                    "error": "Path is not a file"
                }

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            return {
                "success": True,
                "content": content,
                "filename": filename,
                "size": len(content)
            }

        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def list_files(self, project_id: str) -> List[Dict[str, Any]]:
        """
        List all files in project artifacts directory.

        Args:
            project_id: ID of the project

        Returns:
            List of file information dictionaries
        """
        try:
            project_path = self.get_project_path(project_id)

            if not os.path.exists(project_path):
                return []

            files = []

            for root, dirs, filenames in os.walk(project_path):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, project_path)

                    # Get file stats
                    stats = os.stat(file_path)

                    files.append({
                        "filename": relative_path,
                        "size": stats.st_size,
                        "modified_at": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                        "created_at": datetime.fromtimestamp(stats.st_ctime).isoformat()
                    })

            # Sort by filename
            files.sort(key=lambda f: f["filename"])

            logger.debug(f"Listed {len(files)} files for project {project_id}")

            return files

        except Exception as e:
            logger.error(f"Error listing files: {e}")
            return []

    async def create_zip(self, project_id: str) -> Dict[str, Any]:
        """
        Create ZIP archive of all project artifacts.

        Args:
            project_id: ID of the project

        Returns:
            Dictionary with 'success', 'path', 'size', or 'error'
        """
        try:
            project_path = self.get_project_path(project_id)

            if not os.path.exists(project_path):
                return {
                    "success": False,
                    "error": "Project directory not found"
                }

            # List files first
            files = await self.list_files(project_id)
            if not files:
                return {
                    "success": False,
                    "error": "No files to archive"
                }

            # Create ZIP file
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"{project_id}_{timestamp}.zip"
            zip_path = os.path.join(self.ARTIFACTS_PATH, zip_filename)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, filenames in os.walk(project_path):
                    for filename in filenames:
                        file_path = os.path.join(root, filename)
                        arcname = os.path.relpath(file_path, project_path)
                        zipf.write(file_path, arcname)

            zip_size = os.path.getsize(zip_path)

            logger.info(
                f"Created ZIP archive for project {project_id}: "
                f"{zip_filename} ({zip_size} bytes, {len(files)} files)"
            )

            return {
                "success": True,
                "path": zip_path,
                "filename": zip_filename,
                "size": zip_size,
                "file_count": len(files)
            }

        except Exception as e:
            logger.error(f"Error creating ZIP: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def cleanup(self, project_id: str) -> Dict[str, Any]:
        """
        Delete all project artifacts.

        Args:
            project_id: ID of the project

        Returns:
            Dictionary with 'success' boolean and details or 'error'
        """
        try:
            project_path = self.get_project_path(project_id)

            if not os.path.exists(project_path):
                return {
                    "success": True,
                    "message": "Project directory does not exist"
                }

            # Count files before deletion
            files = await self.list_files(project_id)
            file_count = len(files)

            # Delete the directory
            shutil.rmtree(project_path)

            logger.info(f"Cleaned up {file_count} files for project {project_id}")

            return {
                "success": True,
                "files_deleted": file_count,
                "path": project_path
            }

        except Exception as e:
            logger.error(f"Error cleaning up project: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def delete_file(
        self,
        project_id: str,
        filename: str
    ) -> Dict[str, Any]:
        """
        Delete a specific file from project artifacts.

        Args:
            project_id: ID of the project
            filename: Name of the file to delete

        Returns:
            Dictionary with 'success' boolean or 'error'
        """
        try:
            file_path = os.path.join(self.get_project_path(project_id), filename)

            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": "File not found"
                }

            if not os.path.isfile(file_path):
                return {
                    "success": False,
                    "error": "Path is not a file"
                }

            os.remove(file_path)

            logger.debug(f"Deleted file {filename} from project {project_id}")

            return {
                "success": True,
                "filename": filename
            }

        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_directory_size(self, project_id: str) -> int:
        """
        Get total size of project artifacts directory.

        Args:
            project_id: ID of the project

        Returns:
            Total size in bytes
        """
        try:
            project_path = self.get_project_path(project_id)

            if not os.path.exists(project_path):
                return 0

            total_size = 0
            for root, dirs, filenames in os.walk(project_path):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    total_size += os.path.getsize(file_path)

            return total_size

        except Exception as e:
            logger.error(f"Error getting directory size: {e}")
            return 0


# Create singleton instance
artifact_service = ArtifactService()
