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
    assert "color-scheme: light dark" in html
    assert "--canvas: #ffffff;" in html
    assert "--surface: #f7f7f7;" in html
    assert "--hairline: #e5e5e5;" in html
    assert ':root[data-theme="dark"]' in html
    assert "@media (prefers-color-scheme: dark)" in html
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


def test_render_page_html_includes_document_code_block_and_table_styles(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert "--code-bg: #1c1c1e;" in html
    assert ".article .highlight" in html
    assert "color: var(--code-text)" in html
    assert "overflow-x: auto" in html
    assert ".article table" in html
    assert "border-collapse: collapse" in html
    assert ".article th," in html
    assert ".article td" in html
    assert "border: 1px solid var(--hairline);" in html


def test_render_page_html_includes_theme_and_locale_controls(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert 'class="toolbar-actions"' in html
    assert 'data-theme-toggle' in html
    assert 'data-locale-select' in html
    assert '<option value="en">English</option>' in html
    assert '<option value="zh-CN">简体中文</option>' in html
    assert '<option value="zh-TW">繁體中文</option>' in html
    assert 'const THEME_STORAGE_KEY = "mdfh-theme";' in html
    assert 'const LOCALE_STORAGE_KEY = "mdfh-locale";' in html
    assert 'document.documentElement.dataset.theme = normalizedTheme;' in html
    assert 'window.matchMedia("(prefers-color-scheme: dark)")' in html


def test_render_page_html_marks_shell_text_for_i18n(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert 'data-i18n="contents">Contents</h1>' in html
    assert 'data-i18n="siteNavigation">Site navigation</h2>' in html
    assert 'data-i18n="onThisPage">On this page</h2>' in html
    assert 'data-i18n="previous">Previous</strong>' in html
    assert 'data-i18n="next">Next</strong>' in html
    assert 'data-i18n-aria-label="siteNavigation"' in html
    assert '"zh-CN": {' in html
    assert '"zh-TW": {' in html
    assert 'reviewComments: "审查评论"' in html
    assert 'reviewComments: "審查評論"' in html


def test_render_page_html_scopes_i18n_away_from_markdown_body() -> None:
    document = Document(
        source_path=Path("/tmp/standalone.md"),
        relative_source_path=PurePosixPath("standalone.md"),
        output_path=PurePosixPath("standalone.html"),
    )
    page = RenderedPage(
        document=document,
        title="Standalone",
        content_html='<div data-i18n="next">Authored body marker</div>',
    )

    html = render_page_html(page, [], {document.output_path: page})

    assert '<div data-i18n="next">Authored body marker</div>' in html
    assert "function isUiTranslationElement(element)" in html
    assert 'element.closest("[data-mdfh-content=\'1\']")' in html
    assert 'element.closest("[data-mdfh-ui]")' in html
    assert "document.documentElement.lang = normalizedLocale" not in html


def test_render_page_html_uses_theme_selection_tokens(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert "--selection-bg" in html
    assert "--selection-text" in html
    assert "::selection" in html
    assert "::-moz-selection" in html


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
    assert "transition: padding-left 220ms ease;" in html
    assert "padding-left: 0;" in html
    assert "transition: transform 220ms ease;" in html
    assert "transform: translateX(calc(-1 * var(--sidebar-width)));" in html
    assert (
        '<button type="button" class="sidebar-edge-toggle" data-sidebar-toggle '
        'data-sidebar-edge-toggle aria-controls="site-sidebar" aria-expanded="true" '
        'aria-label="Collapse sidebar" title="Collapse sidebar" '
        'data-i18n-aria-label="collapseSidebar" data-i18n-title="collapseSidebar">‹</button>'
    ) in html
    assert "right: 1rem;" in html
    assert "width: 1.9rem;" in html
    assert "height: 1.9rem;" in html
    assert "min-width: 0;" in html
    assert "z-index: 2;" in html
    assert ".layout.is-sidebar-collapsed .sidebar-edge-toggle" in html
    assert 'class="page-toolbar-toggle"' in html
    toolbar_start = html.index(".page-toolbar-toggle {\n  display: none;")
    toolbar_end = html.index(".layout.is-sidebar-collapsed .page-toolbar-toggle")
    toolbar_css = html[toolbar_start:toolbar_end]

    assert "position: fixed;" not in toolbar_css
    assert "top: 1rem;" not in toolbar_css
    assert "left: 1rem;" not in toolbar_css
    assert ".layout.is-sidebar-collapsed .page-toolbar-toggle" in html
    assert 'const isEdgeToggle = toggle.hasAttribute("data-sidebar-edge-toggle");' in html
    assert 'toggle.textContent = expanded ? "‹" : ">";' in html
    assert 'toggle.textContent = t("menu");' in html
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


def test_render_page_html_omits_doc_close_link(
    sample_site_copy: Path,
    tmp_path: Path,
):
    _, rendered_pages, nav_tree, ordered_pages = _build_site_context(sample_site_copy, tmp_path)
    intro_page = ordered_pages[1]

    html = render_page_html(intro_page, nav_tree, rendered_pages)

    assert 'class="article" data-doc-card' in html
    assert 'class="article-close"' not in html
    assert 'aria-label="Close document"' not in html
    assert "&times;" not in html


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
    assert html.count('data-mdfh-content="1"') == 1
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

    assert 'data-i18n="onThisPage">On this page</h2>' not in sidebar_html
    assert "data-site-nav-toggle" in html
    assert "data-site-nav-content" in html
    assert "data-toc-content" not in sidebar_html
    assert 'class="page-pager"' not in html
    assert "<title>Standalone</title>" in html
