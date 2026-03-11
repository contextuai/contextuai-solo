"""
File operation tools for Strands Agent.
Provides file read, write, list, and processing capabilities.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from strands.tools import tool

# Import file storage service for user uploads
from services.file_storage_service import UPLOAD_BASE_DIR, file_storage_service

logger = logging.getLogger(__name__)


class FileTools:
    """File operation tools for personas with file processing capabilities."""

    def __init__(self):
        """Initialize file tools with safety configurations."""
        self.environment = os.getenv("ENVIRONMENT", "dev")

        # Define safe base directories based on environment
        # Always include user upload directory for file attachments
        if self.environment == "prod":
            # In production, restrict to specific safe directories
            self.allowed_dirs = [
                "/tmp",  # Temporary files
                "/var/contextuai/data",  # Application data directory
                UPLOAD_BASE_DIR,  # User uploaded files
            ]
        else:
            # In dev/staging, allow more flexibility but still restrict system dirs
            self.allowed_dirs = [
                "/tmp",
                "/var/contextuai",
                os.path.expanduser("~"),  # User home directory
                UPLOAD_BASE_DIR,  # User uploaded files
            ]

        # File size limits (in bytes)
        self.max_file_size = 10 * 1024 * 1024  # 10 MB
        self.max_list_count = 1000  # Maximum files to list

        logger.info(f"FileTools initialized for environment: {self.environment}")

    def _is_safe_path(self, path: str) -> bool:
        """
        Check if a path is safe to access.

        Args:
            path: The file path to check

        Returns:
            True if the path is safe, False otherwise
        """
        try:
            # Resolve to absolute path
            abs_path = os.path.abspath(path)

            # Check if path is within allowed directories
            for allowed_dir in self.allowed_dirs:
                allowed_abs = os.path.abspath(allowed_dir)
                if abs_path.startswith(allowed_abs):
                    return True

            logger.warning(f"Path outside allowed directories: {abs_path}")
            return False

        except Exception as e:
            logger.error(f"Error checking path safety: {e}")
            return False

    def get_tools(self):
        """Return all file operation tools as a list for Strands Agent."""
        # Return the tool methods directly - they're already decorated with @tool
        return [
            self.read_file,
            self.read_uploaded_file,
            self.write_file,
            self.list_files,
            self.file_info,
            self.delete_file,
            self.create_directory
        ]

    @tool
    async def read_file(self, file_path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Read contents of a file.

        Args:
            file_path: Path to the file to read
            encoding: File encoding (default: utf-8)

        Returns:
            Dictionary with file contents or error message
        """
        try:
            # Safety check
            if not self._is_safe_path(file_path):
                return {
                    "success": False,
                    "error": "Access denied: Path outside allowed directories"
                }

            # Check if file exists
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }

            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > self.max_file_size:
                return {
                    "success": False,
                    "error": f"File too large: {file_size} bytes (max: {self.max_file_size})"
                }

            # Read file
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()

            logger.info(f"Successfully read file: {file_path} ({file_size} bytes)")

            return {
                "success": True,
                "file_path": file_path,
                "content": content,
                "size_bytes": file_size,
                "encoding": encoding
            }

        except UnicodeDecodeError:
            # Try reading as binary if text decode fails
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()

                return {
                    "success": True,
                    "file_path": file_path,
                    "content": content.hex(),  # Return as hex string
                    "size_bytes": len(content),
                    "encoding": "binary",
                    "note": "File read as binary and returned as hex string"
                }
            except Exception as e:
                logger.error(f"Error reading file as binary: {e}")
                return {
                    "success": False,
                    "error": f"Failed to read file: {str(e)}"
                }

        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return {
                "success": False,
                "error": f"Failed to read file: {str(e)}"
            }

    @tool
    async def read_uploaded_file(self, file_id: str) -> Dict[str, Any]:
        """
        Read contents of a user-uploaded file by its file ID.

        Args:
            file_id: The unique identifier of the uploaded file

        Returns:
            Dictionary with file contents and metadata
        """
        try:
            # Get file metadata
            metadata = file_storage_service.get_file_metadata(file_id)
            if not metadata:
                return {
                    "success": False,
                    "error": f"File not found: {file_id}"
                }

            # Get file content
            content = await file_storage_service.get_file_content(file_id)
            if content is None:
                return {
                    "success": False,
                    "error": f"File content not available: {file_id}"
                }

            # Check if text-based file
            text_extensions = {'.txt', '.md', '.json', '.xml', '.csv', '.yaml', '.yml',
                              '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.sql',
                              '.log', '.conf', '.ini', '.env'}

            if metadata["extension"] in text_extensions:
                try:
                    text_content = content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        text_content = content.decode('latin-1')
                    except Exception:
                        text_content = content.hex()
                        return {
                            "success": True,
                            "file_id": file_id,
                            "filename": metadata["original_filename"],
                            "content": text_content,
                            "encoding": "binary-hex",
                            "size_bytes": metadata["size"],
                            "content_type": metadata["content_type"]
                        }

                logger.info(f"Successfully read uploaded file: {file_id}")
                return {
                    "success": True,
                    "file_id": file_id,
                    "filename": metadata["original_filename"],
                    "content": text_content,
                    "encoding": "utf-8",
                    "size_bytes": metadata["size"],
                    "content_type": metadata["content_type"]
                }
            else:
                # Binary file - return metadata only, content as base64 hint
                logger.info(f"Binary file detected: {file_id}")
                return {
                    "success": True,
                    "file_id": file_id,
                    "filename": metadata["original_filename"],
                    "content": f"[Binary file: {metadata['original_filename']} ({metadata['size']} bytes)]",
                    "encoding": "binary",
                    "size_bytes": metadata["size"],
                    "content_type": metadata["content_type"],
                    "note": "Binary files cannot be displayed as text. Use the file for image analysis or document processing."
                }

        except Exception as e:
            logger.error(f"Error reading uploaded file {file_id}: {e}")
            return {
                "success": False,
                "error": f"Failed to read uploaded file: {str(e)}"
            }

    @tool
    async def write_file(self, file_path: str, content: str, encoding: str = "utf-8", overwrite: bool = False) -> Dict[str, Any]:
        """
        Write content to a file.

        Args:
            file_path: Path to the file to write
            content: Content to write to the file
            encoding: File encoding (default: utf-8)
            overwrite: Whether to overwrite existing file (default: False)

        Returns:
            Dictionary with write status
        """
        try:
            # Safety check
            if not self._is_safe_path(file_path):
                return {
                    "success": False,
                    "error": "Access denied: Path outside allowed directories"
                }

            # Check if file exists and overwrite is False
            if os.path.exists(file_path) and not overwrite:
                return {
                    "success": False,
                    "error": f"File already exists: {file_path}. Set overwrite=True to replace."
                }

            # Ensure parent directory exists
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
                logger.info(f"Created directory: {parent_dir}")

            # Write file
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(content)

            file_size = len(content.encode(encoding))
            logger.info(f"Successfully wrote file: {file_path} ({file_size} bytes)")

            return {
                "success": True,
                "file_path": file_path,
                "size_bytes": file_size,
                "encoding": encoding,
                "overwritten": os.path.exists(file_path) and overwrite
            }

        except Exception as e:
            logger.error(f"Error writing file {file_path}: {e}")
            return {
                "success": False,
                "error": f"Failed to write file: {str(e)}"
            }

    @tool
    async def list_files(self, directory: str, pattern: str = "*", recursive: bool = False) -> Dict[str, Any]:
        """
        List files in a directory.

        Args:
            directory: Directory path to list
            pattern: File pattern to match (default: *)
            recursive: Whether to list recursively (default: False)

        Returns:
            Dictionary with list of files
        """
        try:
            # Safety check
            if not self._is_safe_path(directory):
                return {
                    "success": False,
                    "error": "Access denied: Path outside allowed directories"
                }

            # Check if directory exists
            if not os.path.exists(directory):
                return {
                    "success": False,
                    "error": f"Directory not found: {directory}"
                }

            if not os.path.isdir(directory):
                return {
                    "success": False,
                    "error": f"Path is not a directory: {directory}"
                }

            # List files
            path = Path(directory)
            if recursive:
                files = list(path.rglob(pattern))
            else:
                files = list(path.glob(pattern))

            # Limit number of files
            if len(files) > self.max_list_count:
                logger.warning(f"Too many files ({len(files)}), limiting to {self.max_list_count}")
                files = files[:self.max_list_count]
                truncated = True
            else:
                truncated = False

            # Format file information
            file_list = []
            for file_path in files:
                try:
                    stat = file_path.stat()
                    file_list.append({
                        "path": str(file_path),
                        "name": file_path.name,
                        "is_directory": file_path.is_dir(),
                        "size_bytes": stat.st_size if file_path.is_file() else None,
                        "modified": stat.st_mtime
                    })
                except Exception as e:
                    logger.warning(f"Could not stat file {file_path}: {e}")

            logger.info(f"Listed {len(file_list)} files in {directory}")

            return {
                "success": True,
                "directory": directory,
                "pattern": pattern,
                "recursive": recursive,
                "files": file_list,
                "count": len(file_list),
                "truncated": truncated
            }

        except Exception as e:
            logger.error(f"Error listing files in {directory}: {e}")
            return {
                "success": False,
                "error": f"Failed to list files: {str(e)}"
            }

    @tool
    async def file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get detailed information about a file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with file information
        """
        try:
            # Safety check
            if not self._is_safe_path(file_path):
                return {
                    "success": False,
                    "error": "Access denied: Path outside allowed directories"
                }

            # Check if file exists
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }

            # Get file stats
            stat = os.stat(file_path)
            path = Path(file_path)

            info = {
                "success": True,
                "path": file_path,
                "name": path.name,
                "extension": path.suffix,
                "is_file": path.is_file(),
                "is_directory": path.is_dir(),
                "is_symlink": path.is_symlink(),
                "size_bytes": stat.st_size if path.is_file() else None,
                "created": stat.st_ctime,
                "modified": stat.st_mtime,
                "accessed": stat.st_atime,
                "permissions": oct(stat.st_mode),
                "owner_uid": stat.st_uid,
                "group_gid": stat.st_gid
            }

            # Add parent directory
            if path.parent:
                info["parent_directory"] = str(path.parent)

            logger.info(f"Retrieved info for: {file_path}")
            return info

        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {e}")
            return {
                "success": False,
                "error": f"Failed to get file info: {str(e)}"
            }

    @tool
    async def delete_file(self, file_path: str) -> Dict[str, Any]:
        """
        Delete a file (with safety restrictions).

        Args:
            file_path: Path to the file to delete

        Returns:
            Dictionary with deletion status
        """
        try:
            # Safety check
            if not self._is_safe_path(file_path):
                return {
                    "success": False,
                    "error": "Access denied: Path outside allowed directories"
                }

            # Check if file exists
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }

            # Don't delete directories with this method
            if os.path.isdir(file_path):
                return {
                    "success": False,
                    "error": "Cannot delete directory with delete_file. Use appropriate directory operations."
                }

            # Delete the file
            os.remove(file_path)
            logger.info(f"Successfully deleted file: {file_path}")

            return {
                "success": True,
                "file_path": file_path,
                "message": "File deleted successfully"
            }

        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
            return {
                "success": False,
                "error": f"Failed to delete file: {str(e)}"
            }

    @tool
    async def create_directory(self, directory_path: str, create_parents: bool = True) -> Dict[str, Any]:
        """
        Create a directory.

        Args:
            directory_path: Path to the directory to create
            create_parents: Whether to create parent directories if they don't exist (default: True)

        Returns:
            Dictionary with creation status
        """
        try:
            # Safety check
            if not self._is_safe_path(directory_path):
                return {
                    "success": False,
                    "error": "Access denied: Path outside allowed directories"
                }

            # Check if already exists
            if os.path.exists(directory_path):
                if os.path.isdir(directory_path):
                    return {
                        "success": True,
                        "directory_path": directory_path,
                        "message": "Directory already exists",
                        "created": False
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Path exists but is not a directory: {directory_path}"
                    }

            # Create directory
            os.makedirs(directory_path, exist_ok=create_parents)
            logger.info(f"Successfully created directory: {directory_path}")

            return {
                "success": True,
                "directory_path": directory_path,
                "message": "Directory created successfully",
                "created": True
            }

        except Exception as e:
            logger.error(f"Error creating directory {directory_path}: {e}")
            return {
                "success": False,
                "error": f"Failed to create directory: {str(e)}"
            }