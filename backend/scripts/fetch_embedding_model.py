"""
Download the all-MiniLM-L6-v2 ONNX embedding model used by
`services/embedding_service.py`.

Usage (from the backend/ directory):

    python scripts/fetch_embedding_model.py

The destination is ``$MODELS_DIR/embedding/all-MiniLM-L6-v2/`` (default
``~/.contextuai-solo/models``):

    embedding/all-MiniLM-L6-v2/
        ├── model.onnx
        └── tokenizer.json

For a packaged build, point MODELS_DIR at the backend tree so PyInstaller
can bundle it (the spec's ``datas`` reads ``models/embedding/...``):

    MODELS_DIR=backend/models python scripts/fetch_embedding_model.py

Downloads use a plain HTTPS GET against huggingface.co/resolve/main rather
than ``hf_hub_download`` — ranged GETs work through corporate proxies and
firewalls where the hub client (Xet/LFS pointers) stalls.
"""
import os
import sys
from pathlib import Path
from urllib.parse import quote

HF_REPO = "Xenova/all-MiniLM-L6-v2"
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
TARGET_FILES = [
    ("onnx/model.onnx", "model.onnx"),
    ("tokenizer.json", "tokenizer.json"),
]


def _download(url: str, dest: Path) -> None:
    """Stream ``url`` to ``dest`` via a plain ranged-capable HTTPS GET."""
    import requests

    part = dest.with_suffix(dest.suffix + ".part")
    with requests.get(
        url, stream=True, timeout=(15, 60), allow_redirects=True,
    ) as resp:
        resp.raise_for_status()
        with open(part, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    os.replace(part, dest)


def main() -> int:
    base = os.environ.get(
        "MODELS_DIR",
        os.path.join(Path.home(), ".contextuai-solo", "models"),
    )
    target = Path(base) / "embedding" / "all-MiniLM-L6-v2"
    target.mkdir(parents=True, exist_ok=True)

    print(f"Target: {target}")
    print(f"Source: {HF_ENDPOINT}/{HF_REPO}")

    for hf_path, local_name in TARGET_FILES:
        local_path = target / local_name
        if local_path.exists() and local_path.stat().st_size > 0:
            print(f"  exists  {local_name}")
            continue
        url = f"{HF_ENDPOINT}/{HF_REPO}/resolve/main/{quote(hf_path)}"
        print(f"  fetch   {hf_path} ...", end=" ", flush=True)
        try:
            _download(url, local_path)
            size_mb = local_path.stat().st_size / 1_048_576
            print(f"ok ({size_mb:.1f} MB)")
        except Exception as e:
            print(f"FAILED: {e}")
            return 2

    print("\nEmbedding model ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
