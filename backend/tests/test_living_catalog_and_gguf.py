"""SPEC-34: GGUF Binary Header Inspector, OTA Catalog Sync & Live HF Discovery tests."""
import json
import struct
import pytest

from services.gguf_inspector import inspect_gguf_bytes, inspect_gguf_file
from services.local_model_seeder import _unknown_gguf_to_model_doc
from services import hf_hub_discovery


def _pack_str(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack("<Q", len(raw)) + raw


def _build_synthetic_gguf(
    arch: str = "qwen2",
    ctx_len: int = 32768,
    chat_template: str = "{% if tools %}<tool_call>{% endif %}",
    name: str = "Qwen2.5-7B-Instruct",
    file_type: int = 15,
) -> bytes:
    buf = bytearray()
    buf.extend(b"GGUF")
    buf.extend(struct.pack("<I", 3))  # version 3
    buf.extend(struct.pack("<Q", 290))  # tensor_count
    buf.extend(struct.pack("<Q", 5))  # kv_count

    # 1. general.architecture (STRING = 8)
    buf.extend(_pack_str("general.architecture"))
    buf.extend(struct.pack("<I", 8))
    buf.extend(_pack_str(arch))

    # 2. general.name (STRING = 8)
    buf.extend(_pack_str("general.name"))
    buf.extend(struct.pack("<I", 8))
    buf.extend(_pack_str(name))

    # 3. qwen2.context_length (UINT32 = 4)
    buf.extend(_pack_str(f"{arch}.context_length"))
    buf.extend(struct.pack("<I", 4))
    buf.extend(struct.pack("<I", ctx_len))

    # 4. general.file_type (UINT32 = 4)
    buf.extend(_pack_str("general.file_type"))
    buf.extend(struct.pack("<I", 4))
    buf.extend(struct.pack("<I", file_type))

    # 5. tokenizer.chat_template (STRING = 8)
    buf.extend(_pack_str("tokenizer.chat_template"))
    buf.extend(struct.pack("<I", 8))
    buf.extend(_pack_str(chat_template))

    return bytes(buf)


def test_gguf_inspector_extracts_metadata_and_seeder_wires_it(tmp_path):
    raw = _build_synthetic_gguf(
        arch="qwen2",
        ctx_len=65536,
        chat_template="{% for tool in tools %}<tool_call>{{ tool }}</tool_call>{% endfor %}",
        name="Qwen2.5-Coder-14B",
    )
    meta = inspect_gguf_bytes(raw, filename="Qwen2.5-Coder-14B-Q4_K_M.gguf")
    assert meta["valid"] is True
    assert meta["architecture"] == "qwen2"
    assert meta["context_length"] == 65536
    assert meta["supports_tools"] is True
    assert meta["name"] == "Qwen2.5-Coder-14B"

    gguf_file = tmp_path / "Qwen2.5-Coder-14B-Q4_K_M.gguf"
    gguf_file.write_bytes(raw)
    file_meta = inspect_gguf_file(str(gguf_file))
    assert file_meta["context_length"] == 65536
    assert file_meta["supports_tools"] is True

    # Verify _unknown_gguf_to_model_doc uses the GGUF header metadata
    doc = _unknown_gguf_to_model_doc(gguf_file)
    assert doc["context_window"] == 65536
    assert doc["supports_function_calling"] is True
    assert doc["model_metadata"]["family"] == "qwen2"


@pytest.mark.asyncio
async def test_hf_repo_gguf_files_and_ota_catalog_merge(tmp_path):
    from services import model_catalog

    cache_path = tmp_path / "catalog_cache.json"
    ota_models = [
        {
            "id": "qwen3-5-9b-instruct-ota-test",
            "name": "Qwen 3.5 9B Instruct",
            "family": "qwen",
            "provider": "Alibaba",
            "parameter_size": "9B",
            "parameter_count": 9.0,
            "size_gb": 5.5,
            "ram_required_gb": 8,
            "ram_recommended_gb": 12,
            "categories": ["general", "coding"],
            "description": "OTA synced model",
            "quantization": "Q4_K_M",
            "context_window": 131072,
            "supports_vision": False,
            "supports_tools": True,
            "quality_tier": "best",
            "speed_tier": "fast",
            "hf_repo": "bartowski/Qwen3.5-9B-Instruct-GGUF",
            "hf_filename": "Qwen3.5-9B-Instruct-Q4_K_M.gguf",
            "chat_template": "chatml",
        }
    ]
    cache_path.write_text(json.dumps({"models": ota_models}), encoding="utf-8")
    res = await hf_hub_discovery.refresh_ota_catalog(cache_path=str(cache_path))
    assert res["merged_count"] == 1
    assert any(
        m["id"] == "qwen3-5-9b-instruct-ota-test" and m.get("is_new")
        for m in model_catalog.LOCAL_MODEL_CATALOG
    )
