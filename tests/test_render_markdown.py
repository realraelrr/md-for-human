from __future__ import annotations

from pathlib import Path, PurePosixPath

from md_for_human.discovery import discover_site
from md_for_human.render_markdown import render_document


def test_render_document_extracts_title_generates_toc_heading_ids_and_highlights_code(
    sample_site_copy: Path,
    tmp_path: Path,
):
    manifest = discover_site(sample_site_copy, tmp_path / "output")
    intro = next(
        document
        for document in manifest.documents
        if document.relative_source_path == PurePosixPath("guide/intro.md")
    )

    page = render_document(intro, manifest)

    assert page.title == "Intro"
    assert 'id="intro"' in page.content_html
    assert 'id="example"' in page.content_html
    assert "On this page" in page.toc_html
    assert 'href="#example"' in page.toc_html
    assert 'class="highlight"' in page.content_html


def test_render_document_rewrites_in_tree_markdown_links_and_preserves_fragments(
    sample_site_copy: Path,
    tmp_path: Path,
):
    manifest = discover_site(sample_site_copy, tmp_path / "output")
    intro = next(
        document
        for document in manifest.documents
        if document.relative_source_path == PurePosixPath("guide/intro.md")
    )

    page = render_document(intro, manifest)

    assert 'href="setup.html#install"' in page.content_html
    assert 'href="../reference/index.html"' in page.content_html


def test_render_document_preserves_external_links_warns_for_out_of_tree_paths_and_captures_assets(
    tmp_path: Path,
):
    input_dir = tmp_path / "docs"
    assets_dir = input_dir / "images"
    assets_dir.mkdir(parents=True)
    (assets_dir / "diagram.png").write_bytes(b"png-data")
    (input_dir / "page.md").write_text(
        "\n".join(
            [
                "# Page",
                "",
                "[External](https://example.com)",
                "[Outside](../outside.md)",
                "[Asset](images/diagram.png)",
                "![Diagram](images/diagram.png)",
            ]
        ),
        encoding="utf-8",
    )

    manifest = discover_site(input_dir, tmp_path / "output")
    page = render_document(manifest.documents[0], manifest)

    assert 'href="https://example.com"' in page.content_html
    assert 'href="../outside.md"' in page.content_html
    assert any("outside the input tree" in warning for warning in page.warnings)
    assert page.referenced_assets == {PurePosixPath("images/diagram.png")}
    assert 'src="images/diagram.png"' in page.content_html


def test_render_document_falls_back_to_file_stem_without_toc(sample_site_copy: Path, tmp_path: Path):
    manifest = discover_site(sample_site_copy, tmp_path / "output")
    page_without_h1 = next(
        document
        for document in manifest.documents
        if document.relative_source_path == PurePosixPath("misc/no-title.md")
    )

    page = render_document(page_without_h1, manifest)

    assert page.title == "no-title"
    assert page.toc_html == ""
