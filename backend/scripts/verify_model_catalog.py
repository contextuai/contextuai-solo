"""
Check every local-model catalog entry against the HuggingFace Hub.

Usage (from the backend/ directory):

    python scripts/verify_model_catalog.py              # every entry
    python scripts/verify_model_catalog.py --current    # skip legacy entries

For each entry in ``services/model_catalog.py`` this confirms the repo is
reachable, the pinned ``hf_filename`` (every shard, for split GGUFs) still
exists, and the real download size is close to the catalog's ``size_gb``.
Run it after editing the catalog — quantisers do rename and delete files.

Exits 1 if any file is missing, 0 otherwise (size drift is only a warning).
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.model_catalog import LOCAL_MODEL_CATALOG  # noqa: E402

SIZE_TOLERANCE = 0.15  # warn when the real size differs by more than 15%
_SHARD_RE = re.compile(r"-(\d{5})-of-(\d{5})\.gguf$")


def _expected_files(filename: str) -> list:
    """Return every file a catalog entry downloads (all shards if split)."""
    m = _SHARD_RE.search(filename)
    if not m:
        return [filename]
    base = filename[: m.start()]
    total = int(m.group(2))
    return [f"{base}-{i:05d}-of-{total:05d}.gguf" for i in range(1, total + 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--current", action="store_true", help="skip legacy entries")
    args = parser.parse_args()

    from huggingface_hub import HfApi

    api = HfApi()
    missing = 0
    for entry in LOCAL_MODEL_CATALOG:
        if args.current and entry.get("legacy"):
            continue
        repo, filename = entry["hf_repo"], entry["hf_filename"]
        try:
            info = api.model_info(repo, files_metadata=True)
        except Exception as exc:
            print(f"MISSING  {entry['id']:<28} repo {repo}: {exc}")
            missing += 1
            continue

        sizes = {s.rfilename: (s.size or 0) for s in info.siblings or []}
        absent = [f for f in _expected_files(filename) if f not in sizes]
        if absent:
            print(f"MISSING  {entry['id']:<28} {repo}: {', '.join(absent)}")
            missing += 1
            continue

        actual_gb = sum(sizes[f] for f in _expected_files(filename)) / 1e9
        drift = abs(actual_gb - entry["size_gb"]) / max(entry["size_gb"], 0.01)
        status = "SIZE?" if drift > SIZE_TOLERANCE else "OK"
        print(f"{status:<8} {entry['id']:<28} {actual_gb:6.2f} GB (catalog {entry['size_gb']} GB)")

    print(f"\n{missing} missing file(s)")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
