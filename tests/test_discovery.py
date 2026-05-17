from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from md_for_human.discovery import DiscoveryError, discover_site


def test_discover_site_returns_sorted_documents_and_normalized_index_pages(
    sample_site_copy: Path,
    tmp_path: Path,
):
    manifest = discover_site(sample_site_copy, tmp_path / "output")

    assert [document.relative_source_path for document in manifest.documents] == [
        PurePosixPath("README.md"),
        PurePosixPath("guide/intro.md"),
        PurePosixPath("guide/setup.md"),
        PurePosixPath("misc/no-title.md"),
        PurePosixPath("reference/README.md"),
    ]
    assert [document.output_path for document in manifest.documents] == [
        PurePosixPath("index.html"),
        PurePosixPath("guide/intro.html"),
        PurePosixPath("guide/setup.html"),
        PurePosixPath("misc/no-title.html"),
        PurePosixPath("reference/index.html"),
    ]
    assert manifest.entry_document is not None
    assert manifest.entry_document.output_path == PurePosixPath("index.html")
    assert manifest.warnings == []


def test_discover_site_includes_markdown_case_insensitively(
    sample_site_copy: Path,
    tmp_path: Path,
):
    uppercase_file = sample_site_copy / "guide" / "appendix.MD"
    uppercase_file.write_text("# Appendix\n", encoding="utf-8")

    manifest = discover_site(sample_site_copy, tmp_path / "output")

    assert PurePosixPath("guide/appendix.MD") in [
        document.relative_source_path for document in manifest.documents
    ]


def test_discover_site_detects_output_collisions(tmp_path: Path):
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "README.md").write_text("# Readme\n", encoding="utf-8")
    (input_dir / "index.md").write_text("# Index\n", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="collision"):
        discover_site(input_dir, tmp_path / "output")


def test_discover_site_skips_symlinks_with_warnings(tmp_path: Path):
    input_dir = tmp_path / "docs"
    nested_dir = input_dir / "nested"
    nested_dir.mkdir(parents=True)
    real_file = input_dir / "page.md"
    real_file.write_text("# Real page\n", encoding="utf-8")
    (nested_dir / "inside.md").write_text("# Nested page\n", encoding="utf-8")
    (input_dir / "link.md").symlink_to(real_file)
    (input_dir / "linked-dir").symlink_to(nested_dir, target_is_directory=True)

    manifest = discover_site(input_dir, tmp_path / "output")

    assert [document.relative_source_path for document in manifest.documents] == [
        PurePosixPath("nested/inside.md"),
        PurePosixPath("page.md"),
    ]
    assert len(manifest.warnings) == 2
    assert all("symlink" in warning.lower() for warning in manifest.warnings)


def test_discover_site_raises_for_empty_input(tmp_path: Path):
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "notes.txt").write_text("not markdown", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="No Markdown files"):
        discover_site(input_dir, tmp_path / "output")


def test_discover_site_accepts_a_single_markdown_file_input(tmp_path: Path):
    input_file = tmp_path / "notes.md"
    input_file.write_text("# Notes\n", encoding="utf-8")

    manifest = discover_site(input_file, tmp_path / "output")

    assert manifest.input_dir == tmp_path
    assert [document.relative_source_path for document in manifest.documents] == [
        PurePosixPath("notes.md"),
    ]
    assert [document.output_path for document in manifest.documents] == [
        PurePosixPath("notes.html"),
    ]
    assert manifest.entry_document is not None
    assert manifest.entry_document.output_path == PurePosixPath("notes.html")
