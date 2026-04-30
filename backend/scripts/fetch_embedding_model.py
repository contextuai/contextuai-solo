"""
Download the all-MiniLM-L6-v2 ONNX embedding model into the local dev
location used by `services/embedding_service.py`.

Usage (from the backend/ directory):

    python scripts/fetch_embedding_model.py

In production the model is bundled by PyInstaller. In local dev it has to
be fetched from Hugging Face once. The destination is:

    ~/.contextuai-solo/models/embedding/all-MiniLM-L6-v2/
        ├── model.onnx
        └── tokenizer.json
"""
import os
import shutil
import sys
from pathlib import Path

HF_REPO = "Xenova/all-MiniLM-L6-v2"
TARGET_FILES = [
    ("onnx/model.onnx", "model.onnx"),
    ("tokenizer.json", "tokenizer.json"),
]


def main() -> int:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("huggingface_hub is not installed. Run: pip install huggingface-hub")
        return 1

    base = os.environ.get(
        "MODELS_DIR",
        os.path.join(Path.home(), ".contextuai-solo", "models"),
    )
    target = Path(base) / "embedding" / "all-MiniLM-L6-v2"
    target.mkdir(parents=True, exist_ok=True)

    print(f"Target: {target}")
    print(f"Source: hf://{HF_REPO}")

    for hf_path, local_name in TARGET_FILES:
        local_path = target / local_name
        if local_path.exists():
            print(f"  exists  {local_name}")
            continue
        print(f"  fetch   {hf_path} ...", end=" ", flush=True)
        try:
            cached = hf_hub_download(repo_id=HF_REPO, filename=hf_path)
            shutil.copy(cached, local_path)
            size_mb = local_path.stat().st_size / 1_048_576
            print(f"ok ({size_mb:.1f} MB)")
        except Exception as e:
            print(f"FAILED: {e}")
            return 2

    print("\nEmbedding model ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
