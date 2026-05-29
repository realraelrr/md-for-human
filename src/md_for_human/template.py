from __future__ import annotations

import html
from pathlib import PurePosixPath

from md_for_human.models import NavNode, RenderedPage
from md_for_human.static_assets import BASE_CSS, BASE_JS
from md_for_human.urls import relative_output_link


def render_page_html(
    page: RenderedPage,
    nav_tree: list[NavNode],
    rendered_pages: dict[PurePosixPath, RenderedPage],
    entry_output_path: PurePosixPath = PurePosixPath("index.html"),
) -> str:
    navigation_html = render_navigation(nav_tree, page.document.output_path)
    pager_html = render_page_pager(page, rendered_pages)
    sidebar_toc_html = render_sidebar_toc(page.toc_html)
    page_meta = html.escape(page.document.relative_source_path.as_posix())
    page_attr = html.escape(page.document.output_path.as_posix(), quote=True)
    source_path_attr = html.escape(page.document.relative_source_path.as_posix(), quote=True)
    close_href = relative_output_link(page.document.output_path, entry_output_path)

    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"  <title>{html.escape(page.title)}</title>\n"
        f"  <style data-mdfh-base-style>{BASE_CSS}</style>\n"
        "</head>\n"
        f"<body data-mdfh-page=\"{page_attr}\" data-mdfh-source-path=\"{source_path_attr}\">\n"
        "  <div class=\"layout\" data-layout>\n"
        "    <aside class=\"sidebar\" data-sidebar id=\"site-sidebar\">\n"
        "      <button type=\"button\" class=\"sidebar-edge-toggle\" data-sidebar-toggle data-sidebar-edge-toggle aria-controls=\"site-sidebar\" aria-expanded=\"true\" aria-label=\"Collapse sidebar\" title=\"Collapse sidebar\">‹</button>\n"
        "      <div class=\"sidebar-header\">\n"
        "        <span class=\"sidebar-badge\" aria-hidden=\"true\">MD</span>\n"
        "        <h1>Contents</h1>\n"
        "      </div>\n"
        "      <div class=\"sidebar-scroll\">\n"
        "        <section class=\"sidebar-section\" data-site-nav-section>\n"
        "          <div class=\"sidebar-section-header\">\n"
        "            <h2>Site navigation</h2>\n"
        "            <button type=\"button\" class=\"sidebar-action\" data-site-nav-toggle aria-expanded=\"true\">Hide</button>\n"
        "          </div>\n"
        "          <div class=\"sidebar-section-content\" data-site-nav-content>\n"
        f"{navigation_html}\n"
        "          </div>\n"
        "        </section>\n"
        f"{sidebar_toc_html}\n"
        "      </div>\n"
        "    </aside>\n"
        "    <main class=\"main\">\n"
        "      <div class=\"main-inner\">\n"
        "        <div class=\"page-toolbar\">\n"
        "          <button type=\"button\" class=\"page-toolbar-toggle\" data-sidebar-toggle aria-controls=\"site-sidebar\" aria-expanded=\"true\">Menu</button>\n"
        f"          <p class=\"page-meta\">{page_meta}</p>\n"
        "        </div>\n"
        "        <article class=\"article\" data-doc-card>\n"
        f"          <a class=\"article-close\" href=\"{html.escape(close_href, quote=True)}\" aria-label=\"Close document\" title=\"Close document\">&times;</a>\n"
        f"          <div class=\"article-content\" data-mdfh-content=\"1\">{page.content_html}</div>\n"
        "        </article>\n"
        f"{pager_html}\n"
        "      </div>\n"
        "    </main>\n"
        "  </div>\n"
        f"  <script data-mdfh-base-script>{BASE_JS}</script>\n"
        "</body>\n"
        "</html>\n"
    )


def render_navigation(nav_tree: list[NavNode], current_output: PurePosixPath) -> str:
    if not nav_tree:
        return '<nav aria-label="Site navigation"><ul class="nav-tree"></ul></nav>'

    items = "".join(render_nav_node(node, current_output) for node in nav_tree)
    return f'<nav aria-label="Site navigation"><ul class="nav-tree">{items}</ul></nav>'


def render_sidebar_toc(toc_html: str) -> str:
    if not toc_html:
        return ""

    toc_nav_html = toc_html.replace("<h2>On this page</h2>", "", 1)
    return (
        '<section class="sidebar-section">'
        '<div class="sidebar-section-header">'
        "<h2>On this page</h2>"
        '<button type="button" class="sidebar-action" data-toc-toggle aria-expanded="true">Hide</button>'
        "</div>"
        f'<div class="sidebar-section-content" data-toc-content>{toc_nav_html}</div>'
        "</section>"
    )


def render_nav_node(node: NavNode, current_output: PurePosixPath) -> str:
    if not node.is_dir:
        assert node.document is not None
        href = relative_output_link(current_output, node.document.output_path)
        current_attr = ' aria-current="page"' if node.document.output_path == current_output else ""
        return (
            '<li class="nav-item nav-item-file" data-nav-kind="file">'
            f'<a class="nav-link" href="{html.escape(href, quote=True)}"{current_attr}>'
            '<span class="nav-kind nav-kind-file" aria-hidden="true">Doc</span>'
            f'<span class="nav-label">{html.escape(node.name)}</span></a>'
            "</li>"
        )

    branch_class = "nav-branch"
    if branch_contains_page(node, current_output):
        branch_class += " is-active-branch"

    children_html = "".join(render_nav_node(child, current_output) for child in node.children)
    return (
        f'<li class="nav-item nav-item-folder" data-nav-kind="folder"><details class="{branch_class}" data-nav-branch>'
        '<summary class="nav-summary">'
        '<span class="nav-kind nav-kind-folder" aria-hidden="true">Dir</span>'
        f'<span class="nav-label">{html.escape(node.name)}</span></summary>'
        f'<ul class="nav-children">{children_html}</ul>'
        "</details></li>"
    )


def render_page_pager(
    page: RenderedPage,
    rendered_pages: dict[PurePosixPath, RenderedPage],
) -> str:
    links: list[str] = []
    if page.previous_document is not None:
        previous_page = rendered_pages.get(page.previous_document.output_path)
        previous_title = previous_page.title if previous_page is not None else page.previous_document.display_title
        previous_href = relative_output_link(page.document.output_path, page.previous_document.output_path)
        links.append(
            f'<a href="{html.escape(previous_href, quote=True)}">'
            f"<strong>Previous</strong><br>{html.escape(previous_title)}</a>"
        )

    if page.next_document is not None:
        next_page = rendered_pages.get(page.next_document.output_path)
        next_title = next_page.title if next_page is not None else page.next_document.display_title
        next_href = relative_output_link(page.document.output_path, page.next_document.output_path)
        links.append(
            f'<a href="{html.escape(next_href, quote=True)}">'
            f"<strong>Next</strong><br>{html.escape(next_title)}</a>"
        )

    if not links:
        return ""

    return f'<nav class="page-pager" aria-label="Page navigation">{"".join(links)}</nav>'


def branch_contains_page(node: NavNode, current_output: PurePosixPath) -> bool:
    for child in node.children:
        if child.document is not None and child.document.output_path == current_output:
            return True
        if child.is_dir and branch_contains_page(child, current_output):
            return True
    return False
