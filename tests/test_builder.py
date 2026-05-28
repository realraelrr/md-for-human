from __future__ import annotations

from pathlib import Path
import json

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
    assert result.pages == [
        "index.html",
        "guide/intro.html",
        "guide/setup.html",
        "misc/no-title.html",
        "reference/index.html",
    ]
    assert result.copied_assets == ["images/diagram.png"]
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
    assert result.pages[0] == "index.html"
    assert (output_dir / ".md-for-human" / "manifest.json").exists()


def test_build_site_url_encodes_synthetic_landing_page_links(tmp_path: Path):
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "space file.md").write_text("# Space File\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    result = build_site(input_dir, output_dir)
    landing_html = result.entry_page.read_text(encoding="utf-8")

    assert 'href="space%20file.html"' in landing_html
    assert 'href="space file.html"' not in landing_html


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
    assert result.pages == ["notes.html"]
    assert list(output_dir.rglob("*.html")) == [output_dir / "notes.html"]


def test_build_site_writes_manifest_for_agent_audit(sample_site_copy: Path, tmp_path: Path):
    output_dir = tmp_path / "output"

    result = build_site(sample_site_copy, output_dir)
    manifest_path = output_dir / ".md-for-human" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result.manifest_path == manifest_path
    assert manifest["entry_page"] == "index.html"
    assert manifest["pages"] == result.pages
    assert manifest["copied_assets"] == ["images/diagram.png"]
    assert manifest["warnings"] == []


def test_build_site_warns_for_missing_and_symlinked_assets(tmp_path: Path):
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    outside_asset = tmp_path / "outside.png"
    outside_asset.write_bytes(b"png")
    (input_dir / "linked.png").symlink_to(outside_asset)
    (input_dir / "page.md").write_text(
        "# Page\n\n![Missing](missing.png)\n\n![Linked](linked.png)\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    result = build_site(input_dir, output_dir)

    assert any("Missing referenced asset: missing.png" in warning for warning in result.warnings)
    assert any("Skipping symlinked asset: linked.png" in warning for warning in result.warnings)
    assert not (output_dir / "missing.png").exists()
    assert not (output_dir / "linked.png").exists()


def test_build_site_warns_for_assets_resolving_outside_root(tmp_path: Path):
    input_dir = tmp_path / "docs"
    outside_dir = tmp_path / "outside-assets"
    input_dir.mkdir()
    outside_dir.mkdir()
    (outside_dir / "diagram.png").write_bytes(b"png")
    (input_dir / "assets").symlink_to(outside_dir, target_is_directory=True)
    (input_dir / "page.md").write_text("# Page\n\n![Diagram](assets/diagram.png)\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    result = build_site(input_dir, output_dir)

    assert any(
        "Skipping asset outside input tree after resolving: assets/diagram.png" in warning
        for warning in result.warnings
    )
    assert not (output_dir / "assets" / "diagram.png").exists()


def test_build_site_warns_for_referenced_asset_directory(tmp_path: Path):
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "asset-dir").mkdir()
    (input_dir / "page.md").write_text("# Page\n\n[Directory](asset-dir)\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    result = build_site(input_dir, output_dir)

    assert any(
        "Skipping referenced asset that is not a file: asset-dir" in warning
        for warning in result.warnings
    )
    assert not (output_dir / "asset-dir").exists()
