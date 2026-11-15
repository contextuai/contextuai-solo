"""SPEC-08 & SPEC-03: HuggingFace Token, Local `.gguf` Import, and `/v1` Custom Model Resolution."""
import struct
import pytest

from models.cloud_provider_models import (
    CloudProviderType,
    SENSITIVE_KEYS,
    CloudProviderCreate,
)
from services.model_manager import ModelManager
from routers import openai_compat


def _create_dummy_gguf(path):
    """Write a valid minimal GGUF v3 binary header."""
    data = bytearray()
    data.extend(b"GGUF")
    data.extend(struct.pack("<I", 3))  # version 3
    data.extend(struct.pack("<Q", 0))  # tensor_count = 0
    data.extend(struct.pack("<Q", 0))  # kv_count = 0
    data.extend(b"\x00" * 64)
    path.write_bytes(bytes(data))


def test_huggingface_provider_model_and_friendly_errors():
    assert CloudProviderType.HUGGINGFACE == "huggingface"
    assert "api_key" in SENSITIVE_KEYS["huggingface"]

    req = CloudProviderCreate(
        provider_type=CloudProviderType.HUGGINGFACE,
        config={"api_key": "hf_test_123456"},
    )
    assert req.provider_type == CloudProviderType.HUGGINGFACE

    msg_401 = ModelManager._friendly_http_error(401, "org/model")
    assert "Settings → AI Providers" in msg_401
    msg_429 = ModelManager._friendly_http_error(429, "org/model")
    assert "Settings → AI Providers" in msg_429


def test_import_local_gguf_and_v1_resolution(tmp_path, monkeypatch):
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    mgr = ModelManager(models_dir=str(models_dir))

    # Create an external .gguf file
    src_gguf = tmp_path / "my-custom-coder-q4_k_m.gguf"
    _create_dummy_gguf(src_gguf)

    imported = mgr.import_local_gguf(str(src_gguf), copy_file=True)
    assert imported["id"] == "local:custom-my-custom-coder-q4_k_m"
    assert (models_dir / "my-custom-coder-q4_k_m.gguf").is_file()

    # Reject non-.gguf file
    bad_file = tmp_path / "not_a_model.txt"
    bad_file.write_text("hello")
    with pytest.raises(ValueError):
        mgr.import_local_gguf(str(bad_file))

    # Verify /v1 _resolve_model resolves custom .gguf by id, stem, and local: prefix
    import services.model_manager as mm_mod
    monkeypatch.setattr(mm_mod, "model_manager", mgr)

    entry1 = openai_compat._resolve_model("local:custom-my-custom-coder-q4_k_m")
    assert entry1 is not None
    assert entry1["hf_filename"] == "my-custom-coder-q4_k_m.gguf"

    entry2 = openai_compat._resolve_model("my-custom-coder-q4_k_m")
    assert entry2 is not None
    assert "my-custom-coder-q4_k_m" in entry2["id"]
