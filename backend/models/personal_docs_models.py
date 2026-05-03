"""Pydantic v2 models for Personal Docs folder mappings + index jobs."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DEFAULT_EXCLUDE_GLOBS: List[str] = [
    "**/.git/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.venv/**",
    "**/venv/**",
    "**/dist/**",
    "**/build/**",
    "**/.next/**",
    "**/.turbo/**",
    "**/.cache/**",
    "**/.idea/**",
    "**/.vscode/**",
    "**/target/**",
    "**/out/**",
    "**/coverage/**",
    "**/Thumbs.db",
    "**/.DS_Store",
    "**/.*",
]

SUPPORTED_FOLDER_EXTS = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".html",
    ".htm",
    ".rtf",
    ".csv",
    ".json",
}

ScheduleLiteral = Literal["manual", "1h", "6h", "24h"]
JobStatusLiteral = Literal[
    "queued",
    "walking",
    "awaiting_confirmation",
    "running",
    "done",
    "error",
    "cancelled",
]
JobKindLiteral = Literal["full_sync", "incremental", "delete_source"]
SourceStatusLiteral = Literal["active", "paused", "error"]


class FolderSourceCreate(BaseModel):
    path: str
    label: Optional[str] = None
    include_globs: List[str] = Field(default_factory=lambda: ["**/*"])
    exclude_globs: List[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE_GLOBS))
    schedule: ScheduleLiteral = "manual"
    max_file_bytes: Optional[int] = None
    max_files: Optional[int] = None
    max_depth: Optional[int] = None


class FolderSourceUpdate(BaseModel):
    label: Optional[str] = None
    include_globs: Optional[List[str]] = None
    exclude_globs: Optional[List[str]] = None
    schedule: Optional[ScheduleLiteral] = None
    status: Optional[SourceStatusLiteral] = None
    max_file_bytes: Optional[int] = None
    max_files: Optional[int] = None
    max_depth: Optional[int] = None


class FolderSource(BaseModel):
    id: str
    kb_id: str
    path: str
    label: str
    include_globs: List[str]
    exclude_globs: List[str]
    schedule: ScheduleLiteral
    max_file_bytes: int
    max_files: int
    max_depth: int
    status: SourceStatusLiteral
    last_sync_at: Optional[str] = None
    last_sync_job_id: Optional[str] = None
    file_count: int = 0
    byte_count: int = 0
    error: Optional[str] = None
    created_at: str
    updated_at: str


class IndexJob(BaseModel):
    id: str
    kb_id: str
    source_id: str
    kind: JobKindLiteral
    status: JobStatusLiteral
    files_total: int = 0
    files_done: int = 0
    files_added: int = 0
    files_updated: int = 0
    files_removed: int = 0
    files_skipped: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    cancel_requested: bool = False
    created_at: str
