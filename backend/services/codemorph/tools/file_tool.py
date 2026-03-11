"""File operations for CodeMorph AI agent."""
import os
import logging
from strands import tool

logger = logging.getLogger(__name__)


@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file.

    Args:
        file_path: Absolute path to the file to read
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 50000:
            return content[:50000] + "\n... [truncated]"
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file, creating directories if needed.

    Args:
        file_path: Absolute path to write to
        content: Content to write to the file
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


@tool
def list_files(directory: str, pattern: str = "*") -> str:
    """List files in a directory, optionally filtering by pattern.

    Args:
        directory: Directory to list files in
        pattern: Glob pattern to filter files (default: *)
    """
    try:
        import glob
        files = glob.glob(os.path.join(directory, "**", pattern), recursive=True)
        # Limit to 200 files
        if len(files) > 200:
            return "\n".join(files[:200]) + f"\n... and {len(files) - 200} more files"
        return "\n".join(files) if files else "No files found"
    except Exception as e:
        return f"Error listing files: {str(e)}"
