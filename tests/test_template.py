from __future__ import annotations

from pathlib import Path, PurePosixPath

from md_for_human.discovery import discover_site
from md_for_human.models import Document, RenderedPage
from md_for_human.navigation import build_navigation
from md_for_human.render_markdown import render_document
from md_for_human.template import render_page_html


def _build_site_context(sample_site_copy: Path, tmp_path: Path):
    manifest = discover_site(sample_site_copy, tmp_path / "output")
    rendered_pages = {
        document.output_path: render_document(document, manifest) for document in manifest.documents
    }
    nav_tree, ordered_pages = build_navigation(manifest, rendered_pages)
    return manifest, rendered_pages, nav_tree, ordered_pages


def test_render_page_html_builds_full_shell_with_inline_assets_and_active_nav(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert html.startswith("<!DOCTYPE html>")
    assert '<style data-mdfh-base-style>' in html
    assert '<script data-mdfh-base-script>' in html
    assert "prefers-color-scheme: light" in html
    assert "data-sidebar-toggle" in html
    assert 'aria-current="page"' in html
    assert "<title>Intro</title>" in html
    assert intro_page.content_html in html


def test_render_page_html_renders_toc_and_prev_next_links_when_available(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert "On this page" in html
    assert "Previous" in html
    assert "Next" in html
    assert 'href="../index.html"' in html
    assert 'href="setup.html"' in html


def test_render_page_html_merges_site_navigation_and_toc_into_collapsible_sidebar(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)
    sidebar_start = html.index('<aside class="sidebar"')
    sidebar_end = html.index("</aside>")
    sidebar_html = html[sidebar_start:sidebar_end]

    assert "data-layout" in html
    assert "data-sidebar-toggle" in html
    assert "is-sidebar-collapsed" in html
    assert "data-site-nav-toggle" in sidebar_html
    assert "data-site-nav-content" in sidebar_html
    assert "data-toc-toggle" in html
    assert "data-toc-content" in html
    assert "On this page" in sidebar_html
    assert "Site navigation" in sidebar_html
    assert "const hasPageToc = Boolean(tocContent);" not in html
    assert "syncSiteNavState(true);" in html


def test_render_page_html_includes_dark_code_block_and_table_styles(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert "--code-bg" in html
    assert ".article .highlight" in html
    assert "color: var(--code-text)" in html
    assert "overflow-x: auto" in html
    assert ".article table" in html
    assert "border-collapse: collapse" in html
    assert ".article th," in html
    assert ".article td" in html
    assert "border: 1px solid var(--border);" in html


def test_render_page_html_does_not_override_native_selection_styling(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert "::selection" not in html
    assert "::-moz-selection" not in html
    assert "--selection-bg" not in html
    assert "--selection-text" not in html


def test_render_page_html_uses_left_sliding_sidebar_and_distinguishes_nav_hierarchy(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)
    sidebar_start = html.index('<aside class="sidebar"')
    sidebar_end = html.index("</aside>")
    sidebar_html = html[sidebar_start:sidebar_end]

    assert "--sidebar-peek-width" not in html
    assert "padding-left: var(--sidebar-width);" in html
    assert "transition: padding-left 300ms ease;" in html
    assert "padding-left: 0;" in html
    assert "transition: transform 300ms ease;" in html
    assert "transform: translateX(calc(-1 * var(--sidebar-width)));" in html
    assert (
        '<button type="button" class="sidebar-edge-toggle" data-sidebar-toggle '
        'data-sidebar-edge-toggle aria-controls="site-sidebar" aria-expanded="true" '
        'aria-label="Collapse sidebar" title="Collapse sidebar">‹</button>'
    ) in html
    assert "right: 1rem;" in html
    assert "width: 2rem;" in html
    assert "height: 2rem;" in html
    assert "min-width: 0;" in html
    assert "z-index: 2;" in html
    assert ".layout.is-sidebar-collapsed .sidebar-edge-toggle" in html
    assert 'class="page-toolbar-toggle"' in html
    assert "position: fixed;" in html
    assert ".layout.is-sidebar-collapsed .page-toolbar-toggle" in html
    assert 'const isEdgeToggle = toggle.hasAttribute("data-sidebar-edge-toggle");' in html
    assert 'toggle.textContent = expanded ? "‹" : ">";' in html
    assert 'toggle.textContent = expanded ? "Menu" : ">";' in html
    assert 'class="nav-item nav-item-folder" data-nav-kind="folder"' in sidebar_html
    assert 'class="nav-item nav-item-file" data-nav-kind="file"' in sidebar_html
    assert 'data-nav-kind="folder"' in sidebar_html
    assert 'data-nav-kind="file"' in sidebar_html
    assert 'class="nav-kind nav-kind-folder"' in sidebar_html
    assert 'class="nav-kind nav-kind-file"' in sidebar_html


def test_render_page_html_includes_toc_click_highlight_feedback(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert ".page-toc a.is-toc-highlighted" in html
    assert ".article .is-heading-highlighted" in html
    assert "@keyframes heading-highlight" in html
    assert "const clearHighlight = (element, className) => {" in html
    assert 'document.querySelectorAll("[data-toc-content] a[href^=\'#\']")' in html
    assert "document.getElementById(targetId)" in html
    assert 'clearHighlight(link, "is-toc-highlighted");' in html
    assert 'clearHighlight(target, "is-heading-highlighted");' in html


def test_render_page_html_styles_toc_hierarchy_and_shared_sidebar_active_states(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert "--sidebar-item-hover-bg" in html
    assert "--sidebar-item-active-bg" in html
    assert "--sidebar-item-active-border" in html
    assert "--sidebar-item-active-text" in html
    assert "--sidebar-item-inactive-text: var(--muted);" in html
    assert ".page-toc .toc-level-1" in html
    assert ".page-toc .toc-level-2" in html
    assert ".page-toc .toc-level-3" in html
    assert "--toc-indent: 0.55rem;" in html
    assert "--toc-indent: 1.25rem;" in html
    assert "--toc-indent: 2rem;" in html
    assert "padding: 0.35rem 0.55rem 0.35rem var(--toc-indent);" in html
    assert (
        ".nav-link[aria-current=\"page\"],\n"
        ".page-toc a.is-toc-highlighted,\n"
        ".page-toc a.is-active"
    ) in html
    assert "background: var(--sidebar-item-active-bg);" in html
    assert "border-color: var(--sidebar-item-active-border);" in html
    assert "color: var(--sidebar-item-active-text);" in html
    assert ".page-toc.is-scroll-spy-active a" in html
    assert "color: var(--sidebar-item-inactive-text);" in html


def test_render_page_html_constrains_long_sidebar_titles(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    html = render_page_html(ordered_pages[1], nav_tree, rendered_pages)

    assert "overflow-x: hidden;" in html
    assert ".sidebar-scroll" in html
    assert "max-width: 100%;" in html
    assert ".sidebar-section" in html
    assert ".nav-label" in html
    assert "text-overflow: ellipsis;" in html
    assert "white-space: nowrap;" in html
    assert ".page-toc a" in html


def test_render_page_html_adds_doc_close_link_to_entry_page(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(
        intro_page,
        nav_tree,
        rendered_pages,
        PurePosixPath("index.html"),
    )

    assert 'class="article" data-doc-card' in html
    assert 'class="article-close"' in html
    assert 'href="../index.html"' in html
    assert 'aria-label="Close document"' in html
    assert "&times;" in html


def test_render_page_html_adds_review_metadata_without_new_content_wrapper(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert (
        '<body data-mdfh-page="guide/intro.html" '
        'data-mdfh-source-path="guide/intro.md">'
    ) in html
    assert '<div class="article-content" data-mdfh-content="1">' in html
    assert html.count("data-mdfh-content=") == 1
    assert '<article class="article" data-doc-card>' in html


def test_render_page_html_includes_toc_scroll_spy(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert "const tocLinks = Array.from" in html
    assert "const tocTargets = tocLinks" in html
    assert "const setActiveTocLink = (activeLink) => {" in html
    assert 'link.classList.toggle("is-active", link === activeLink);' in html
    assert 'tocNav.classList.toggle("is-scroll-spy-active", Boolean(activeLink));' in html
    assert 'activeLink.scrollIntoView({ block: "nearest" });' in html
    assert '"IntersectionObserver" in window' in html
    assert "const findCurrentTocTarget = () => {" in html
    assert "const tocObserver = new IntersectionObserver(scheduleSpyUpdate" in html
    assert "tocObserver.observe(target);" in html
    assert "scheduleSpyUpdate();" in html


def test_render_page_html_omits_optional_sections_when_not_present():
    document = Document(
        source_path=Path("/tmp/standalone.md"),
        relative_source_path=PurePosixPath("standalone.md"),
        output_path=PurePosixPath("standalone.html"),
    )
    page = RenderedPage(
        document=document,
        title="Standalone",
        content_html="<p>Standalone</p>",
    )

    html = render_page_html(page, [], {document.output_path: page})
    sidebar_start = html.index('<aside class="sidebar"')
    sidebar_end = html.index("</aside>")
    sidebar_html = html[sidebar_start:sidebar_end]

    assert "On this page" not in html
    assert "data-site-nav-toggle" in html
    assert "data-site-nav-content" in html
    assert "data-toc-content" not in sidebar_html
    assert 'class="page-pager"' not in html
    assert "<title>Standalone</title>" in html
