from __future__ import annotations

from pathlib import Path

import pytest

from md_for_human.builder import build_site
from md_for_human.discovery import DiscoveryError


def test_build_site_generates_html_and_copies_only_referenced_assets(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"

    result = build_site(sample_site_copy, output_dir)

    assert result.entry_page == output_dir / "index.html"
    assert result.entry_page.exists()
    assert (output_dir / "guide" / "intro.html").exists()
    assert (output_dir / "guide" / "setup.html").exists()
    assert (output_dir / "reference" / "index.html").exists()
    assert (output_dir / "images" / "diagram.png").exists()
    assert not (output_dir / "images" / "unused.png").exists()
    intro_html = (output_dir / "guide" / "intro.html").read_text(encoding="utf-8")
    assert 'class="article-close"' in intro_html
    assert 'href="../index.html"' in intro_html
    assert result.warnings == []


def test_build_site_generates_synthetic_root_landing_page_when_needed(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "README.md").unlink()
    output_dir = tmp_path / "output"

    result = build_site(sample_site_copy, output_dir)
    landing_html = result.entry_page.read_text(encoding="utf-8")

    assert result.entry_page == output_dir / "index.html"
    assert "Document Index" in landing_html
    assert 'href="guide/intro.html"' in landing_html
    assert (output_dir / "guide" / "intro.html").exists()


def test_build_site_does_not_create_output_when_discovery_fails(
    tmp_path: Path,
):
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "README.md").write_text("# Readme\n", encoding="utf-8")
    (input_dir / "index.md").write_text("# Index\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    with pytest.raises(DiscoveryError):
        build_site(input_dir, output_dir)

    assert not output_dir.exists()


def test_build_site_accepts_single_file_input_and_generates_one_html_page(tmp_path: Path):
    input_file = tmp_path / "notes.md"
    input_file.write_text("# Notes\n\nJust one page.\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    result = build_site(input_file, output_dir)

    assert result.entry_page == output_dir / "notes.html"
    assert result.entry_page.exists()
    assert list(output_dir.rglob("*.html")) == [output_dir / "notes.html"]
