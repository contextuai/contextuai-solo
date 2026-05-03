"""Tests for the folder walker (pure functions)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.folder_walker import FileCandidate, classify_diffs, walk_folder


def _touch(p: Path, body: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_walk_respects_extension_filter(tmp_path):
    _touch(tmp_path / "doc.md", "# md")
    _touch(tmp_path / "image.png")
    _touch(tmp_path / "sub" / "note.txt", "n")
    out, capped = walk_folder(
        str(tmp_path),
        include_globs=["**/*"],
        exclude_globs=[],
        max_file_bytes=10_000,
        max_files=100,
        max_depth=10,
    )
    paths = sorted(c.abs_path for c in out)
    assert any(p.endswith("doc.md") for p in paths)
    assert any(p.endswith("note.txt") for p in paths)
    assert not any(p.endswith("image.png") for p in paths)
    assert not capped


def test_walk_respects_exclude_globs(tmp_path):
    _touch(tmp_path / "keep.md")
    _touch(tmp_path / "node_modules" / "lib" / "x.md")
    out, _ = walk_folder(
        str(tmp_path),
        include_globs=["**/*"],
        exclude_globs=["**/node_modules/**"],
        max_file_bytes=10_000,
        max_files=100,
        max_depth=10,
    )
    paths = [c.abs_path for c in out]
    assert any("keep.md" in p for p in paths)
    assert not any("node_modules" in p for p in paths)


def test_walk_respects_max_depth(tmp_path):
    _touch(tmp_path / "a.md")
    _touch(tmp_path / "x" / "y" / "z" / "deep.md")
    out, _ = walk_folder(
        str(tmp_path),
        include_globs=["**/*"],
        exclude_globs=[],
        max_file_bytes=10_000,
        max_files=100,
        max_depth=2,
    )
    paths = [c.abs_path for c in out]
    assert any("a.md" in p for p in paths)
    assert not any("deep.md" in p for p in paths)


def test_walk_skips_oversized_files(tmp_path):
    _touch(tmp_path / "big.txt", "x" * 5_000)
    _touch(tmp_path / "small.txt", "x")
    out, _ = walk_folder(
        str(tmp_path),
        include_globs=["**/*"],
        exclude_globs=[],
        max_file_bytes=1_000,
        max_files=100,
        max_depth=10,
    )
    paths = [c.abs_path for c in out]
    assert any("small.txt" in p for p in paths)
    assert not any("big.txt" in p for p in paths)


def test_walk_caps_at_max_files(tmp_path):
    for i in range(20):
        _touch(tmp_path / f"f{i}.txt", "y")
    out, capped = walk_folder(
        str(tmp_path),
        include_globs=["**/*"],
        exclude_globs=[],
        max_file_bytes=100,
        max_files=5,
        max_depth=10,
    )
    assert len(out) == 5
    assert capped is True


def test_walk_skips_hidden_dirs(tmp_path):
    _touch(tmp_path / "visible.md")
    _touch(tmp_path / ".secret" / "hidden.md")
    out, _ = walk_folder(
        str(tmp_path),
        include_globs=["**/*"],
        exclude_globs=[],
        max_file_bytes=10_000,
        max_files=100,
        max_depth=10,
    )
    paths = [c.abs_path for c in out]
    assert any("visible.md" in p for p in paths)
    assert not any("hidden.md" in p for p in paths)


def test_classify_diffs_new_updated_removed_unchanged():
    cands = [
        FileCandidate(abs_path="/a.md", size=10, mtime=1.0, ext=".md"),
        FileCandidate(abs_path="/b.md", size=20, mtime=2.0, ext=".md"),
        FileCandidate(abs_path="/c.md", size=30, mtime=3.0, ext=".md"),
    ]
    existing = {
        "/a.md": {"size_bytes": 10, "mtime": 1.0, "_id": "doc-a"},
        "/c.md": {"size_bytes": 999, "mtime": 3.0, "_id": "doc-c"},  # size diff
        "/d.md": {"size_bytes": 1, "mtime": 1.0, "_id": "doc-d"},  # gone
    }
    plan = classify_diffs(cands, existing)
    assert {c.abs_path for c in plan.new} == {"/b.md"}
    assert {c.abs_path for c in plan.updated} == {"/c.md"}
    assert plan.removed_doc_ids == ["doc-d"]
    assert plan.unchanged_count == 1
