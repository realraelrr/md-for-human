from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from md_for_human.builder import build_site, build_site_preserving_review
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
    assert 'class="article-close"' not in intro_html
    assert 'aria-label="Close document"' not in intro_html
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


def test_build_site_preserving_review_removes_stale_pages_and_keeps_artifact(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    review_dir = output_dir / ".md-for-human" / "review"
    review_dir.mkdir(parents=True)
    artifact_path = review_dir / "annotations.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "mdfh-review-v2",
                "source_manifest": ".md-for-human/manifest.json",
                "annotations": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (sample_site_copy / "misc" / "no-title.md").unlink()
    result = build_site_preserving_review(sample_site_copy, output_dir)
    manifest = json.loads((output_dir / ".md-for-human" / "manifest.json").read_text())

    assert "misc/no-title.html" not in result.pages
    assert not (output_dir / "misc" / "no-title.html").exists()
    assert artifact_path.exists()
    assert json.loads(artifact_path.read_text(encoding="utf-8"))["annotations"] == []
    assert "misc/no-title.html" not in manifest["pages"]


def test_build_site_writes_manifest_for_agent_audit(sample_site_copy: Path, tmp_path: Path):
    output_dir = tmp_path / "output"

    result = build_site(sample_site_copy, output_dir)
    manifest_path = output_dir / ".md-for-human" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result.manifest_path == manifest_path
    assert manifest["manifest_schema_version"] == "mdfh-manifest-v1"
    assert manifest["tool_name"] == "md-for-human"
    assert manifest["tool_version"] == "0.2.0"
    assert manifest["entry_page"] == "index.html"
    assert manifest["pages"] == result.pages
    assert manifest["copied_assets"] == ["images/diagram.png"]
    assert manifest["warnings"] == []
    assert manifest["documents"] == [
        {
            "page": "index.html",
            "source_path": "README.md",
            "source_line_count": 11,
            "source_sha256": hashlib.sha256(
                (sample_site_copy / "README.md").read_bytes()
            ).hexdigest(),
        },
        {
            "page": "guide/intro.html",
            "source_path": "guide/intro.md",
            "source_line_count": 9,
            "source_sha256": hashlib.sha256(
                (sample_site_copy / "guide" / "intro.md").read_bytes()
            ).hexdigest(),
        },
        {
            "page": "guide/setup.html",
            "source_path": "guide/setup.md",
            "source_line_count": 5,
            "source_sha256": hashlib.sha256(
                (sample_site_copy / "guide" / "setup.md").read_bytes()
            ).hexdigest(),
        },
        {
            "page": "misc/no-title.html",
            "source_path": "misc/no-title.md",
            "source_line_count": 3,
            "source_sha256": hashlib.sha256(
                (sample_site_copy / "misc" / "no-title.md").read_bytes()
            ).hexdigest(),
        },
        {
            "page": "reference/index.html",
            "source_path": "reference/README.md",
            "source_line_count": 3,
            "source_sha256": hashlib.sha256(
                (sample_site_copy / "reference" / "README.md").read_bytes()
            ).hexdigest(),
        },
    ]


def test_build_site_excludes_synthetic_landing_page_from_manifest_documents(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "README.md").unlink()
    output_dir = tmp_path / "output"

    result = build_site(sample_site_copy, output_dir)
    manifest = json.loads(
        (output_dir / ".md-for-human" / "manifest.json").read_text(encoding="utf-8")
    )

    assert result.pages[0] == "index.html"
    assert "index.html" in manifest["pages"]
    assert all(document["page"] != "index.html" for document in manifest["documents"])


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


def test_build_site_copies_assets_referenced_from_raw_html(tmp_path: Path):
    input_dir = tmp_path / "docs"
    image_dir = input_dir / "images"
    style_dir = input_dir / "styles"
    script_dir = input_dir / "scripts"
    image_dir.mkdir(parents=True)
    style_dir.mkdir()
    script_dir.mkdir()
    (image_dir / "raw diagram.png").write_bytes(b"png")
    (style_dir / "site.css").write_text("body { color: black; }\n", encoding="utf-8")
    (script_dir / "app.js").write_text("console.log('ok');\n", encoding="utf-8")
    (input_dir / "page.md").write_text(
        "\n".join(
            [
                "# Page",
                "",
                '<img src="images/raw%20diagram.png" alt="Raw">',
                '<link rel="stylesheet" href="styles/site.css">',
                '<script src="scripts/app.js"></script>',
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    result = build_site(input_dir, output_dir)

    assert sorted(result.copied_assets) == [
        "images/raw diagram.png",
        "scripts/app.js",
        "styles/site.css",
    ]
    assert (output_dir / "images" / "raw diagram.png").exists()
    assert (output_dir / "styles" / "site.css").exists()
    assert (output_dir / "scripts" / "app.js").exists()


def test_build_site_does_not_treat_raw_html_page_links_as_assets(tmp_path: Path):
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "index.md").write_text(
        '# Index\n\n<a href="guide.html">Guide</a>\n',
        encoding="utf-8",
    )
    (input_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    result = build_site(input_dir, output_dir)

    assert result.warnings == []
    assert result.copied_assets == []
    assert (output_dir / "guide.html").exists()


def test_build_site_does_not_treat_synthetic_index_link_as_asset(tmp_path: Path):
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "guide.md").write_text(
        '# Guide\n\n<a href="index.html">Home</a>\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    result = build_site(input_dir, output_dir)

    assert result.warnings == []
    assert result.copied_assets == []
    assert result.entry_page == output_dir / "index.html"


def test_build_site_does_not_treat_raw_html_directory_page_links_as_assets(tmp_path: Path):
    input_dir = tmp_path / "docs"
    guide_dir = input_dir / "guide"
    guide_dir.mkdir(parents=True)
    (input_dir / "index.md").write_text(
        '# Index\n\n<a href="guide/">Guide</a>\n',
        encoding="utf-8",
    )
    (guide_dir / "index.md").write_text("# Guide\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    result = build_site(input_dir, output_dir)

    assert result.warnings == []
    assert result.copied_assets == []
    assert (output_dir / "guide" / "index.html").exists()
