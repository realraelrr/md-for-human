from __future__ import annotations

from pathlib import Path, PurePosixPath

from md_for_human.discovery import discover_site
from md_for_human.navigation import build_navigation
from md_for_human.render_markdown import render_document


def test_build_navigation_creates_tree_uses_titles_and_omits_empty_directories(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "empty").mkdir()
    manifest = discover_site(sample_site_copy, tmp_path / "output")
    rendered_pages = {
        document.output_path: render_document(document, manifest) for document in manifest.documents
    }

    nav_tree, ordered_pages = build_navigation(manifest, rendered_pages)
    guide_node = next(node for node in nav_tree if node.name == "guide")
    misc_node = next(node for node in nav_tree if node.name == "misc")
    reference_node = next(node for node in nav_tree if node.name == "reference")

    assert [node.name for node in nav_tree] == ["Sample Site", "guide", "misc", "reference"]
    assert [child.name for child in guide_node.children] == ["Intro", "Setup"]
    assert [child.name for child in misc_node.children] == ["no-title"]
    assert [child.name for child in reference_node.children] == ["Reference"]
    assert "empty" not in [node.name for node in nav_tree]
    assert [page.title for page in ordered_pages] == [
        "Sample Site",
        "Intro",
        "Setup",
        "no-title",
        "Reference",
    ]


def test_build_navigation_assigns_depth_first_prev_next_links(
    sample_site_copy: Path,
    tmp_path: Path,
):
    manifest = discover_site(sample_site_copy, tmp_path / "output")
    rendered_pages = {
        document.output_path: render_document(document, manifest) for document in manifest.documents
    }

    nav_tree, ordered_pages = build_navigation(manifest, rendered_pages)

    assert nav_tree
    assert [page.document.output_path for page in ordered_pages] == [
        PurePosixPath("index.html"),
        PurePosixPath("guide/intro.html"),
        PurePosixPath("guide/setup.html"),
        PurePosixPath("misc/no-title.html"),
        PurePosixPath("reference/index.html"),
    ]
    assert ordered_pages[0].previous_document is None
    assert ordered_pages[0].next_document == ordered_pages[1].document
    assert ordered_pages[2].previous_document == ordered_pages[1].document
    assert ordered_pages[2].next_document == ordered_pages[3].document
    assert ordered_pages[-1].previous_document == ordered_pages[-2].document
    assert ordered_pages[-1].next_document is None


def test_build_navigation_excludes_synthetic_landing_page_from_page_sequence(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "README.md").unlink()
    manifest = discover_site(sample_site_copy, tmp_path / "output")
    rendered_pages = {
        document.output_path: render_document(document, manifest) for document in manifest.documents
    }

    nav_tree, ordered_pages = build_navigation(manifest, rendered_pages)

    assert manifest.has_synthetic_landing_page is True
    assert nav_tree[0].name == "guide"
    assert [page.document.output_path for page in ordered_pages] == [
        PurePosixPath("guide/intro.html"),
        PurePosixPath("guide/setup.html"),
        PurePosixPath("misc/no-title.html"),
        PurePosixPath("reference/index.html"),
    ]
    assert ordered_pages[0].previous_document is None
    assert ordered_pages[-1].next_document is None
