"""
File Upload API endpoints.
Provides endpoints for uploading, retrieving, and managing user files.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import logging
import os

from services.file_storage_service import (
    file_storage_service,
    MAX_FILE_SIZE,
    ALLOWED_EXTENSIONS
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/files", tags=["files"])


class FileUploadResponse(BaseModel):
    """Response model for file upload."""
    file_id: str = Field(..., description="Unique file identifier")
    original_filename: str = Field(..., description="Original filename")
    size: int = Field(..., description="File size in bytes")
    content_type: str = Field(..., description="MIME type")
    extension: str = Field(..., description="File extension")
    uploaded_at: str = Field(..., description="Upload timestamp")
    expires_at: str = Field(..., description="Expiration timestamp")


class FileListResponse(BaseModel):
    """Response model for listing user files."""
    files: List[Dict[str, Any]] = Field(..., description="List of file metadata")
    total: int = Field(..., description="Total number of files")


class FileDeleteResponse(BaseModel):
    """Response model for file deletion."""
    success: bool = Field(..., description="Whether deletion succeeded")
    file_id: str = Field(..., description="Deleted file ID")
    message: str = Field(..., description="Status message")


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    user_id: str = Form(..., description="User ID")
):
    """
    Upload a file for use in chat conversations.

    - **file**: The file to upload (max 10MB)
    - **user_id**: The user's ID

    Allowed file types: text, code, documents, images, data files.
    Files are stored for 24 hours before automatic cleanup.
    """
    try:
        # Validate file size via content-length header or read
        content = await file.read()

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
            )

        # Validate file extension
        filename = file.filename or "unknown"
        ext = os.path.splitext(filename)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{ext}' not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        # Upload file using storage service
        metadata = await file_storage_service.upload_file(
            user_id=user_id,
            filename=filename,
            content=content,
            content_type=file.content_type
        )

        logger.info(f"File uploaded: {metadata['file_id']} by user {user_id}")

        return FileUploadResponse(
            file_id=metadata["file_id"],
            original_filename=metadata["original_filename"],
            size=metadata["size"],
            content_type=metadata["content_type"],
            extension=metadata["extension"],
            uploaded_at=metadata["uploaded_at"],
            expires_at=metadata["expires_at"]
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IOError as e:
        logger.error(f"File upload IO error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")


@router.get("/", response_model=FileListResponse)
async def list_user_files(
    user_id: str = Query(..., description="User ID to list files for")
):
    """
    List all files for a user.

    Returns metadata for all files uploaded by the user that haven't expired.
    """
    try:
        files = file_storage_service.get_user_files(user_id)

        return FileListResponse(
            files=files,
            total=len(files)
        )

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")


@router.get("/{file_id}")
async def get_file_metadata(file_id: str):
    """
    Get metadata for a specific file.

    Returns file information without the actual content.
    """
    metadata = file_storage_service.get_file_metadata(file_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="File not found")

    return metadata


@router.get("/{file_id}/download")
async def download_file(file_id: str):
    """
    Download a file by ID.

    Returns the actual file content for download.
    """
    metadata = file_storage_service.get_file_metadata(file_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = file_storage_service.get_file_path(file_id)

    if not file_path:
        raise HTTPException(status_code=404, detail="File no longer exists")

    return FileResponse(
        path=file_path,
        filename=metadata["original_filename"],
        media_type=metadata["content_type"]
    )


@router.get("/{file_id}/content")
async def get_file_content(file_id: str):
    """
    Get file content as text (for text-based files).

    Returns the file content as a string. Only works for text-based files.
    """
    metadata = file_storage_service.get_file_metadata(file_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="File not found")

    # Check if it's a text-based file
    text_extensions = {'.txt', '.md', '.json', '.xml', '.csv', '.yaml', '.yml',
                       '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.sql',
                       '.log', '.conf', '.ini', '.env'}

    if metadata["extension"] not in text_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot read content of binary file type: {metadata['extension']}"
        )

    content = await file_storage_service.get_file_content(file_id)

    if content is None:
        raise HTTPException(status_code=404, detail="File content not available")

    try:
        text_content = content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text_content = content.decode('latin-1')
        except Exception:
            raise HTTPException(status_code=400, detail="Unable to decode file content as text")

    return {
        "file_id": file_id,
        "filename": metadata["original_filename"],
        "content": text_content,
        "size": len(content),
        "content_type": metadata["content_type"]
    }


@router.delete("/{file_id}", response_model=FileDeleteResponse)
async def delete_file(file_id: str):
    """
    Delete a file by ID.

    Permanently removes the file and its metadata.
    """
    metadata = file_storage_service.get_file_metadata(file_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="File not found")

    success = await file_storage_service.delete_file(file_id)

    if success:
        logger.info(f"File deleted: {file_id}")
        return FileDeleteResponse(
            success=True,
            file_id=file_id,
            message="File deleted successfully"
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to delete file")


@router.post("/cleanup")
async def cleanup_expired_files():
    """
    Manually trigger cleanup of expired files.

    This endpoint is primarily for administrative use. Expired files
    are also cleaned up automatically.
    """
    # Only allow in dev/staging
    environment = os.getenv("ENVIRONMENT", "dev")
    if environment == "prod":
        raise HTTPException(
            status_code=403,
            detail="Manual cleanup not available in production"
        )

    try:
        deleted_count = await file_storage_service.cleanup_expired_files()

        return {
            "success": True,
            "deleted_count": deleted_count,
            "message": f"Cleaned up {deleted_count} expired files"
        }

    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        raise HTTPException(status_code=500, detail="Cleanup failed")


@router.get("/info/limits")
async def get_upload_limits():
    """
    Get file upload limits and allowed types.

    Returns configuration information for the file upload system.
    """
    return {
        "max_file_size_bytes": MAX_FILE_SIZE,
        "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
        "allowed_extensions": sorted(list(ALLOWED_EXTENSIONS)),
        "retention_hours": 24,
        "upload_directory": file_storage_service.get_upload_directory()
    }
