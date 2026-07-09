"""Pydantic v2 models for the Unified Memory Layer (SPEC-14 PR-A).

PR-A scope: the memory store + manual facts + semantic search + export +
settings/kill-switch. No automatic extraction (PR-C) and no prompt-injection
wiring (PR-B) yet — the models here exist to support the manual-fact CRUD
and the recall/search primitives that PR-B will reuse.
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# A memory scope is intentionally kept as a plain string — "global" or
# "crew:<id>" today, forward-compatible with future scope kinds (e.g.
# "worker:<id>" per SPEC-18) without a model change. See design doc §3.
MemoryScope = str


def _validate_scope(value: str) -> str:
    if not (value.startswith("global") or value.startswith("crew:")):
        raise ValueError('scope must be "global" or start with "crew:"')
    return value


class MemoryFact(BaseModel):
    """Full read model for a memory fact (embedding vector never exposed)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., alias="_id")
    scope: MemoryScope = "global"
    subject: str
    predicate: str
    value: str
    text: str
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    status: str = "active"
    pinned: bool = False
    source_kind: str = "user"
    source_id: Optional[str] = None
    source_label: Optional[str] = None
    origin: str = "user"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_used_at: Optional[str] = None


class MemoryFactCreate(BaseModel):
    """Manual fact creation — origin is always forced to "user" server-side."""

    subject: str = Field(..., min_length=1, max_length=300)
    predicate: str = Field(..., min_length=1, max_length=300)
    value: str = Field(..., min_length=1, max_length=2000)
    text: Optional[str] = Field(None, max_length=4000)
    scope: MemoryScope = Field("global", max_length=200)

    @field_validator("scope")
    @classmethod
    def _check_scope(cls, v: str) -> str:
        return _validate_scope(v)


class MemoryFactUpdate(BaseModel):
    subject: Optional[str] = Field(None, min_length=1, max_length=300)
    predicate: Optional[str] = Field(None, min_length=1, max_length=300)
    value: Optional[str] = Field(None, min_length=1, max_length=2000)
    text: Optional[str] = Field(None, max_length=4000)
    pinned: Optional[bool] = None
    status: Optional[str] = None
    scope: Optional[MemoryScope] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    @field_validator("scope")
    @classmethod
    def _check_scope(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_scope(v)

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in ("active", "review"):
            raise ValueError('status must be "active" or "review"')
        return v


class MemoryFactPin(BaseModel):
    pinned: bool


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(8, ge=1, le=50)
    scopes: Optional[List[str]] = None


class MemorySettings(BaseModel):
    """Master kill switch + per-surface toggles. Channels default OFF (privacy posture)."""

    enabled: bool = True
    chat_enabled: bool = True
    crews_enabled: bool = True
    channels_enabled: bool = False
    confidence_threshold: float = Field(0.6, ge=0.0, le=1.0)


class MemorySettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    chat_enabled: Optional[bool] = None
    crews_enabled: Optional[bool] = None
    channels_enabled: Optional[bool] = None
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
