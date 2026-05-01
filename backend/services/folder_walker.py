"""Pure functions: walk a folder, apply globs, classify diffs against
existing kb_documents.

These are synchronous so callers must dispatch them via `asyncio.to_thread`.
Keeping them pure (no DB, no IO state) makes them easy to unit-test on
temp directories.
"""
import fnmatch
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Tuple

from models.personal_docs_models import SUPPORTED_FOLDER_EXTS


@dataclass
class FileCandidate:
    abs_path: str
    size: int
    mtime: float
    ext: str


@dataclass
class DiffPlan:
    new: List[FileCandidate] = field(default_factory=list)
    updated: List[FileCandidate] = field(default_factory=list)
    removed_doc_ids: List[str] = field(default_factory=list)
    unchanged_count: int = 0


def _normalise(path: str) -> str:
    return path.replace(os.sep, "/")


def _matches_any(rel: str, patterns: Iterable[str]) -> bool:
    """Match a POSIX-style relative path against fnmatch globs.

    fnmatch doesn't natively expand `**` so we also try a collapsed variant
    (drop `**/` prefix) to make `**/node_modules/**` match
    `node_modules/foo`.
    """
    posix = _normalise(rel)
    for p in patterns:
        if fnmatch.fnmatch(posix, p):
            return True
        if "**" in p:
            collapsed = p.replace("**/", "")
            if fnmatch.fnmatch(posix, collapsed):
                return True
    return False


def walk_folder(
    root: str,
    *,
    include_globs: List[str],
    exclude_globs: List[str],
    max_file_bytes: int,
    max_files: int,
    max_depth: int,
) -> Tuple[List[FileCandidate], bool]:
    """Walk `root` and return (candidates, capped).

    `capped` is True if the walk stopped because `max_files` was reached.
    Files with unsupported extensions, oversized files, hidden files, and
    paths matching `exclude_globs` are silently skipped.
    """
    root_p = os.path.abspath(root)
    out: List[FileCandidate] = []

    for dirpath, dirnames, filenames in os.walk(root_p, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root_p)
        depth = 0 if rel_dir in (".", "") else rel_dir.count(os.sep) + 1
        if depth > max_depth:
            dirnames[:] = []
            continue

        # Filter directories in-place: drop hidden + excluded subtrees
        kept_dirs: List[str] = []
        for d in dirnames:
            if d.startswith("."):
                continue
            sub_rel = os.path.normpath(
                os.path.join(rel_dir, d) if rel_dir not in (".", "") else d
            )
            if _matches_any(sub_rel + "/", exclude_globs):
                continue
            if _matches_any(sub_rel, exclude_globs):
                continue
            kept_dirs.append(d)
        dirnames[:] = kept_dirs

        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED_FOLDER_EXTS:
                continue
            rel = (
                os.path.normpath(os.path.join(rel_dir, name))
                if rel_dir not in (".", "")
                else name
            )
            if include_globs and not _matches_any(rel, include_globs):
                continue
            if _matches_any(rel, exclude_globs):
                continue
            abs_path = os.path.join(dirpath, name)
            try:
                st = os.stat(abs_path)
            except OSError:
                continue
            if st.st_size > max_file_bytes:
                continue
            out.append(
                FileCandidate(
                    abs_path=abs_path,
                    size=st.st_size,
                    mtime=st.st_mtime,
                    ext=ext,
                )
            )
            if len(out) >= max_files:
                return out, True
    return out, False


def classify_diffs(
    candidates: List[FileCandidate],
    existing_by_path: Dict[str, Dict],
) -> DiffPlan:
    """Compare a fresh walk vs. existing kb_documents (keyed by abs_path).

    A file is considered unchanged when both `size_bytes` and `mtime` match
    the previous record. Anything else counts as updated.
    """
    plan = DiffPlan()
    seen: set = set()
    for c in candidates:
        seen.add(c.abs_path)
        prev = existing_by_path.get(c.abs_path)
        if prev is None:
            plan.new.append(c)
            continue
        prev_size = int(prev.get("size_bytes", 0) or 0)
        prev_mtime = float(prev.get("mtime", 0.0) or 0.0)
        if prev_size != int(c.size) or prev_mtime != float(c.mtime):
            plan.updated.append(c)
        else:
            plan.unchanged_count += 1
    for path, doc in existing_by_path.items():
        if path not in seen:
            plan.removed_doc_ids.append(doc["_id"])
    return plan
