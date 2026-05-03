"""Pydantic models for the Knowledge Base / RAG feature."""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)


class KnowledgeBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: Optional[str] = None
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    doc_count: int = 0
    chunk_count: int = 0
    created_at: str
    updated_at: str


class KbDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    kb_id: str
    filename: str
    mime_type: str
    size_bytes: int
    page_count: int = 0
    chunk_count: int = 0
    status: str = "pending"
    error: Optional[str] = None
    created_at: str
    updated_at: str


class Citation(BaseModel):
    doc_id: str
    filename: str
    page: Optional[int] = None
    chunk_index: int
    score: float
    excerpt: str


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)


class QueryResponse(BaseModel):
    query: str
    citations: List[Citation]
