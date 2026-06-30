"""Cloud LLM provider onboarding models (Phase 4 PR 4.5).

Solo's cloud LLM access is moving from hardcoded env-var Bedrock to first-class
user-facing onboarding. Each provider has its own credential shape — Anthropic /
OpenAI / Google use a single API key; Bedrock uses an AWS access-key triple.

Credentials are stored verbatim in SQLite under the user's home dir — Solo is
single-user desktop and there is no encryption layer in v1. API responses mask
sensitive fields (`api_key`, `aws_secret_access_key`) to ``"***"``.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# =============================================================================
# Provider catalog
# =============================================================================

class CloudProviderType(str, Enum):
    """All supported cloud LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    BEDROCK = "bedrock"
    OLLAMA = "ollama"


# Sensitive keys per provider type — these are masked in responses.
# Ollama is local and key-less, so it has no sensitive fields.
SENSITIVE_KEYS = {
    CloudProviderType.ANTHROPIC.value: {"api_key"},
    CloudProviderType.OPENAI.value: {"api_key"},
    CloudProviderType.GOOGLE.value: {"api_key"},
    CloudProviderType.BEDROCK.value: {"aws_secret_access_key"},
    CloudProviderType.OLLAMA.value: set(),
}

MASK = "***"


def mask_config(provider_type: str, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a copy of ``config`` with sensitive keys replaced by ``"***"``.

    Non-empty sensitive values are masked; empty / missing values stay as-is so
    the UI can tell "not set" apart from "set, hidden".
    """
    if not config:
        return {}
    out = dict(config)
    for key in SENSITIVE_KEYS.get(provider_type, set()):
        if out.get(key):
            out[key] = MASK
    return out


# =============================================================================
# Document shape
# =============================================================================

class CloudProviderConfig(BaseModel):
    """Persisted shape of one cloud provider configuration."""

    provider_id: str
    provider_type: CloudProviderType
    display_name: str
    connected: bool = False
    last_tested_at: Optional[str] = None
    last_test_status: Optional[Literal["ok", "failed"]] = None
    last_test_error: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


# =============================================================================
# Request models
# =============================================================================

class CloudProviderCreate(BaseModel):
    """Create or upsert a cloud provider configuration."""

    provider_type: CloudProviderType
    display_name: Optional[str] = Field(None, max_length=200)
    config: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_required(self):
        cfg = self.config or {}
        ptype = self.provider_type.value if isinstance(self.provider_type, CloudProviderType) else str(self.provider_type)
        if ptype in ("anthropic", "openai", "google"):
            if not cfg.get("api_key"):
                raise ValueError(f"{ptype} config requires api_key")
        elif ptype == "bedrock":
            for key in ("aws_access_key_id", "aws_secret_access_key", "aws_region"):
                if not cfg.get(key):
                    raise ValueError(f"bedrock config requires {key}")
        return self


class CloudProviderUpdate(BaseModel):
    """Partial update of an existing cloud provider configuration."""

    display_name: Optional[str] = Field(None, max_length=200)
    config: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.display_name is None and self.config is None:
            raise ValueError("Specify display_name and/or config")
        return self


class CloudProviderTestRequest(BaseModel):
    """Probe a config without saving it."""

    provider_type: CloudProviderType
    config: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Response models
# =============================================================================

class CloudProviderResponse(BaseModel):
    """Public view of a cloud provider — sensitive fields masked."""

    provider_id: str
    provider_type: CloudProviderType
    display_name: str
    connected: bool = False
    last_tested_at: Optional[str] = None
    last_test_status: Optional[Literal["ok", "failed"]] = None
    last_test_error: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "CloudProviderResponse":
        ptype = row.get("provider_type")
        return cls(
            provider_id=row.get("provider_id") or row.get("id") or row.get("_id") or "",
            provider_type=CloudProviderType(ptype) if ptype else CloudProviderType.ANTHROPIC,
            display_name=row.get("display_name") or "",
            connected=bool(row.get("connected", False)),
            last_tested_at=row.get("last_tested_at"),
            last_test_status=row.get("last_test_status"),
            last_test_error=row.get("last_test_error"),
            config=mask_config(ptype, row.get("config") or {}),
            created_at=row.get("created_at") or "",
            updated_at=row.get("updated_at") or "",
        )


class CloudProviderListResponse(BaseModel):
    success: bool = True
    providers: List[CloudProviderResponse]
    total_count: int


class CloudProviderTestResponse(BaseModel):
    ok: bool
    latency_ms: int
    error: Optional[str] = None
