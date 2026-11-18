"""
Pure-Python GGUF Binary Header Inspector (SPEC-34).

Reads GGUF v2/v3 binary headers to extract model metadata without loading tensor
weights into memory:
- ``general.architecture`` (e.g. ``"llama"``, ``"qwen2"``, ``"gemma3"``)
- ``general.name``
- ``general.file_type``
- ``<arch>.context_length`` (e.g. 32768, 131072, 262144)
- ``tokenizer.chat_template``
- ``supports_tools`` (auto-detected from chat_template mentioning ``tool_call`` or ``tools``)
- ``quantization`` (inferred from ``file_type`` or filename)
"""

from __future__ import annotations

import io
import logging
import re
import struct
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional, Union

logger = logging.getLogger(__name__)

GGUF_MAGIC = b"GGUF"

# GGUF metadata value types
GGUF_TYPE_UINT8 = 0
GGUF_TYPE_INT8 = 1
GGUF_TYPE_UINT16 = 2
GGUF_TYPE_INT16 = 3
GGUF_TYPE_UINT32 = 4
GGUF_TYPE_INT32 = 5
GGUF_TYPE_FLOAT32 = 6
GGUF_TYPE_BOOL = 7
GGUF_TYPE_STRING = 8
GGUF_TYPE_ARRAY = 9
GGUF_TYPE_UINT64 = 10
GGUF_TYPE_INT64 = 11
GGUF_TYPE_FLOAT64 = 12

_SCALAR_FORMATS = {
    GGUF_TYPE_UINT8: ("<B", 1),
    GGUF_TYPE_INT8: ("<b", 1),
    GGUF_TYPE_UINT16: ("<H", 2),
    GGUF_TYPE_INT16: ("<h", 2),
    GGUF_TYPE_UINT32: ("<I", 4),
    GGUF_TYPE_INT32: ("<i", 4),
    GGUF_TYPE_FLOAT32: ("<f", 4),
    GGUF_TYPE_BOOL: ("<B", 1),
    GGUF_TYPE_UINT64: ("<Q", 8),
    GGUF_TYPE_INT64: ("<q", 8),
    GGUF_TYPE_FLOAT64: ("<d", 8),
}

_FILE_TYPE_TO_QUANT = {
    0: "F32",
    1: "F16",
    2: "Q4_0",
    3: "Q4_1",
    7: "Q8_0",
    8: "Q5_0",
    9: "Q5_1",
    10: "Q2_K",
    11: "Q3_K_S",
    12: "Q3_K_M",
    13: "Q3_K_L",
    14: "Q4_K_S",
    15: "Q4_K_M",
    16: "Q5_K_S",
    17: "Q5_K_M",
    18: "Q6_K",
}

_QUANT_REGEX = re.compile(
    r"(IQ[1-4]_[A-Z0-9_]+|Q[2-8]_[A-Z0-9_]+|BF16|F16|F32)",
    re.IGNORECASE,
)


def infer_quantization_from_filename(filename: str) -> str:
    """Extract quantization tag (e.g. ``Q4_K_M``, ``Q8_0``) from a filename."""
    m = _QUANT_REGEX.search(filename or "")
    if m:
        return m.group(1).upper()
    return "Unknown"


def _read_exact(stream: BinaryIO, n: int) -> bytes:
    data = stream.read(n)
    if len(data) < n:
        raise EOFError("Unexpected EOF while reading GGUF header")
    return data


def _read_string(stream: BinaryIO, max_len: int = 256 * 1024) -> str:
    (length,) = struct.unpack("<Q", _read_exact(stream, 8))
    if length > max_len:
        # Skip overly large string
        stream.seek(length, io.SEEK_CUR)
        return ""
    raw = _read_exact(stream, length)
    return raw.decode("utf-8", errors="replace")


def _read_value(stream: BinaryIO, val_type: int) -> Any:
    if val_type in _SCALAR_FORMATS:
        fmt, size = _SCALAR_FORMATS[val_type]
        (val,) = struct.unpack(fmt, _read_exact(stream, size))
        if val_type == GGUF_TYPE_BOOL:
            return bool(val)
        return val

    if val_type == GGUF_TYPE_STRING:
        return _read_string(stream)

    if val_type == GGUF_TYPE_ARRAY:
        elem_type, count = struct.unpack("<IQ", _read_exact(stream, 12))
        # Skip huge arrays (e.g. tokenizer token tables) to keep inspection instantaneous
        if elem_type in _SCALAR_FORMATS:
            _, elem_size = _SCALAR_FORMATS[elem_type]
            if count > 64:
                stream.seek(count * elem_size, io.SEEK_CUR)
                return f"<array[{count}]>"
            return [_read_value(stream, elem_type) for _ in range(count)]
        elif elem_type == GGUF_TYPE_STRING:
            if count > 32:
                for _ in range(count):
                    (slen,) = struct.unpack("<Q", _read_exact(stream, 8))
                    stream.seek(slen, io.SEEK_CUR)
                return f"<string_array[{count}]>"
            return [_read_string(stream) for _ in range(count)]
        else:
            raise ValueError(f"Unsupported nested array type: {elem_type}")

    raise ValueError(f"Unknown GGUF value type: {val_type}")


def inspect_gguf_stream(
    stream: BinaryIO,
    filename: Optional[str] = None,
    max_kv_pairs: int = 512,
) -> Dict[str, Any]:
    """Parse GGUF header metadata from a binary stream."""
    magic = stream.read(4)
    if magic != GGUF_MAGIC:
        raise ValueError(f"Not a valid GGUF file (magic={magic!r})")

    (version,) = struct.unpack("<I", _read_exact(stream, 4))
    if version not in (1, 2, 3):
        raise ValueError(f"Unsupported GGUF version: {version}")

    if version == 1:
        tensor_count, kv_count = struct.unpack("<II", _read_exact(stream, 8))
    else:
        tensor_count, kv_count = struct.unpack("<QQ", _read_exact(stream, 16))

    kv: Dict[str, Any] = {}
    limit = min(int(kv_count), max_kv_pairs)
    for _ in range(limit):
        try:
            key = _read_string(stream, max_len=4096)
            (vtype,) = struct.unpack("<I", _read_exact(stream, 4))
            val = _read_value(stream, vtype)
            if key:
                kv[key] = val
        except (EOFError, ValueError, struct.error):
            break

    arch = str(kv.get("general.architecture") or "unknown").strip()
    name = str(kv.get("general.name") or "").strip()
    file_type = kv.get("general.file_type")

    # Find context length: check <arch>.context_length or any *.context_length key
    context_length = kv.get(f"{arch}.context_length")
    if context_length is None:
        for k, v in kv.items():
            if k.endswith(".context_length") and isinstance(v, int) and v > 0:
                context_length = v
                break
    context_length = int(context_length) if isinstance(context_length, int) and context_length > 0 else 4096

    chat_template = str(kv.get("tokenizer.chat_template") or "")
    tmpl_lower = chat_template.lower()
    supports_tools = bool(
        "tool_call" in tmpl_lower
        or "tools" in tmpl_lower
        or "<|python_tag|>" in tmpl_lower
        or "[available_tools]" in tmpl_lower
    )

    supports_thinking = bool(
        "<think>" in tmpl_lower
        or "thinking" in tmpl_lower
        or "reasoning" in (filename or "").lower()
        or "r1" in (filename or "").lower()
    )

    quantization = _FILE_TYPE_TO_QUANT.get(file_type) if isinstance(file_type, int) else None
    if not quantization or quantization == "Unknown":
        quantization = infer_quantization_from_filename(filename or name)

    return {
        "valid": True,
        "version": version,
        "tensor_count": int(tensor_count),
        "kv_count": int(kv_count),
        "architecture": arch,
        "name": name or (Path(filename).stem if filename else "Custom GGUF"),
        "file_type": file_type,
        "quantization": quantization,
        "context_length": context_length,
        "chat_template": chat_template,
        "supports_tools": supports_tools,
        "supports_thinking": supports_thinking,
        "raw_kv": kv,
    }


def inspect_gguf_bytes(data: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
    """Inspect a GGUF header from an in-memory bytes buffer."""
    return inspect_gguf_stream(io.BytesIO(data), filename=filename)


def inspect_gguf_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Inspect a local ``.gguf`` file on disk and return its extracted metadata."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"GGUF file not found: {file_path}")
    with open(p, "rb") as fh:
        info = inspect_gguf_stream(fh, filename=p.name)
    # Check if a companion mmproj file is present in the same directory
    mmproj_candidates = list(p.parent.glob("*mmproj*.gguf"))
    info["has_mmproj"] = bool(mmproj_candidates)
    info["mmproj_path"] = str(mmproj_candidates[0]) if mmproj_candidates else None
    return info
