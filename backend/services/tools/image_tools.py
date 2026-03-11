"""
Image Tools for image analysis using Strands image_reader.
Provides on-demand image processing for AI chat context with vision models.
"""

import logging
import os
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Supported image extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}


class ImageTools:
    """Tools for image analysis using Strands image_reader."""

    def __init__(self):
        """Initialize ImageTools."""
        self._image_reader = None
        logger.info("ImageTools initialized")

    def _get_image_reader(self):
        """
        Lazy load the strands image_reader tool.

        Returns:
            The image_reader tool function or None if not available
        """
        if self._image_reader is None:
            try:
                from strands_tools import image_reader
                self._image_reader = image_reader
                logger.info("Strands image_reader loaded successfully")
            except ImportError:
                logger.warning("strands_tools.image_reader not available")
                self._image_reader = False  # Mark as unavailable

        return self._image_reader if self._image_reader else None

    def get_tools(self) -> List:
        """
        Return list of image tool methods for Strands Agent.

        Returns:
            List containing the image_reader tool if available
        """
        reader = self._get_image_reader()
        if reader:
            return [reader]
        return []

    def is_available(self) -> bool:
        """Check if image processing is available."""
        return self._get_image_reader() is not None


def is_image_file(file_path: str) -> bool:
    """
    Check if a file is a supported image format.

    Args:
        file_path: Path to the file

    Returns:
        True if file has a supported image extension
    """
    ext = os.path.splitext(file_path)[1].lower()
    return ext in IMAGE_EXTENSIONS


def get_image_reader_tool():
    """
    Get the strands image_reader tool for direct use.

    Returns:
        The image_reader tool function or None if not available
    """
    try:
        from strands_tools import image_reader
        return image_reader
    except ImportError:
        logger.warning("strands_tools.image_reader not available")
        return None


def prepare_image_for_bedrock(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Prepare an image file for Bedrock Converse API.
    This is an alternative to using image_reader when direct content blocks are needed.

    Args:
        file_path: Path to the image file

    Returns:
        Dictionary with image data in Bedrock format, or None on failure
    """
    try:
        import base64
        from PIL import Image

        # Get media type from extension
        ext = os.path.splitext(file_path)[1].lower()
        media_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }

        media_type = media_type_map.get(ext)
        if not media_type:
            logger.error(f"Unsupported image format: {ext}")
            return None

        # Read and encode image
        with open(file_path, 'rb') as f:
            image_bytes = f.read()

        # Verify it's a valid image
        try:
            img = Image.open(file_path)
            img.verify()
        except Exception as e:
            logger.error(f"Invalid image file: {e}")
            return None

        # Return in Bedrock Converse API format
        return {
            "image": {
                "format": ext[1:],  # Remove the dot
                "source": {
                    "bytes": image_bytes
                }
            }
        }

    except ImportError:
        logger.error("PIL/Pillow not installed for image validation")
        return None
    except Exception as e:
        logger.error(f"Failed to prepare image: {e}")
        return None


def get_image_metadata(file_path: str) -> Dict[str, Any]:
    """
    Get metadata about an image file.

    Args:
        file_path: Path to the image file

    Returns:
        Dictionary with image metadata (dimensions, format, size)
    """
    try:
        from PIL import Image

        with Image.open(file_path) as img:
            return {
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "mode": img.mode,
                "file_size": os.path.getsize(file_path)
            }
    except Exception as e:
        logger.error(f"Failed to get image metadata: {e}")
        return {
            "error": str(e),
            "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0
        }
