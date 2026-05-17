from pathlib import Path, PurePosixPath

from md_for_human.models import Document, NavNode, RenderedPage, SiteManifest


def test_document_tracks_paths_and_url():
    document = Document(
        source_path=Path("/tmp/sample_site/guide/intro.md"),
        relative_source_path=PurePosixPath("guide/intro.md"),
        output_path=PurePosixPath("guide/intro.html"),
    )

    assert document.source_path.name == "intro.md"
    assert document.relative_source_path == PurePosixPath("guide/intro.md")
    assert document.output_path == PurePosixPath("guide/intro.html")
    assert document.url == "guide/intro.html"
    assert document.source_stem == "intro"
    assert document.is_directory_index is False


def test_nav_node_supports_directory_and_file_shapes():
    file_document = Document(
        source_path=Path("/tmp/sample_site/reference/README.md"),
        relative_source_path=PurePosixPath("reference/README.md"),
        output_path=PurePosixPath("reference/index.html"),
        is_directory_index=True,
    )
    file_node = NavNode(
        name="Reference",
        relative_path=PurePosixPath("reference"),
        is_dir=False,
        document=file_document,
    )
    directory_node = NavNode(
        name="guide",
        relative_path=PurePosixPath("guide"),
        is_dir=True,
        children=[file_node],
    )

    assert file_node.document is file_document
    assert file_node.url == "reference/index.html"
    assert directory_node.children == [file_node]
    assert directory_node.url is None


def test_rendered_page_prev_next_are_optional():
    document = Document(
        source_path=Path("/tmp/sample_site/guide/setup.md"),
        relative_source_path=PurePosixPath("guide/setup.md"),
        output_path=PurePosixPath("guide/setup.html"),
    )
    previous = Document(
        source_path=Path("/tmp/sample_site/guide/intro.md"),
        relative_source_path=PurePosixPath("guide/intro.md"),
        output_path=PurePosixPath("guide/intro.html"),
    )
    page = RenderedPage(
        document=document,
        title="Setup",
        content_html="<p>Setup</p>",
        previous_document=previous,
    )

    assert page.previous_document is previous
    assert page.next_document is None
    assert page.toc_html == ""
    assert page.referenced_assets == set()
    assert page.warnings == []


def test_manifest_tracks_entry_document_or_synthetic_landing_page():
    root_index = Document(
        source_path=Path("/tmp/sample_site/README.md"),
        relative_source_path=PurePosixPath("README.md"),
        output_path=PurePosixPath("index.html"),
        is_directory_index=True,
    )

    manifest = SiteManifest(
        input_dir=Path("/tmp/sample_site"),
        output_dir=Path("/tmp/output"),
        documents=[root_index],
        entry_document=root_index,
    )
    landing_manifest = SiteManifest(
        input_dir=Path("/tmp/sample_site"),
        output_dir=Path("/tmp/output"),
        documents=[],
        synthetic_entry_output_path=PurePosixPath("index.html"),
    )

    assert manifest.entry_output_path == PurePosixPath("index.html")
    assert manifest.has_synthetic_landing_page is False
    assert landing_manifest.entry_output_path == PurePosixPath("index.html")
    assert landing_manifest.has_synthetic_landing_page is True
