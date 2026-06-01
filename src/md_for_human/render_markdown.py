from __future__ import annotations

import html
import unicodedata
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from md_for_human.link_targets import LinkTargetRewriter
from md_for_human.models import Document, RenderedPage, SiteManifest


def render_document(document: Document, manifest: SiteManifest) -> RenderedPage:
    parser = MarkdownIt("commonmark").enable("table")
    parser.add_render_rule("fence", _render_fence)

    source_text = document.source_path.read_text(encoding="utf-8")
    tokens = parser.parse(source_text)
    add_source_line_attrs(tokens)
    link_rewriter = LinkTargetRewriter(document, manifest)
    headings: list[tuple[int, str, str]] = []
    slug_counts: dict[str, int] = {}

    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            inline_token = tokens[index + 1] if index + 1 < len(tokens) else None
            heading_text = _extract_heading_text(inline_token)
            heading_id = _build_heading_id(heading_text, slug_counts)
            token.attrSet("id", heading_id)
            level = int(token.tag[1:])
            headings.append((level, heading_text, heading_id))
            continue

        if token.type == "html_block":
            token.content = link_rewriter.rewrite_raw_html_targets(token.content)
            continue

        if token.type != "inline" or not token.children:
            continue

        for child in token.children:
            if child.type == "link_open":
                href = child.attrGet("href")
                if isinstance(href, str) and href:
                    child.attrSet(
                        "href",
                        link_rewriter.rewrite_local_target(href),
                    )
            elif child.type == "html_inline":
                child.content = link_rewriter.rewrite_raw_html_targets(child.content)
            elif child.type == "image":
                src = child.attrGet("src")
                if isinstance(src, str) and src:
                    child.attrSet(
                        "src",
                        link_rewriter.rewrite_local_target(src),
                    )

    content_html = parser.renderer.render(tokens, parser.options, {})
    title = next((text for level, text, _ in headings if level == 1), document.source_stem)
    toc_entries = headings
    if headings and headings[0][0] == 1:
        toc_entries = headings[1:]
    toc_html = build_toc_html(toc_entries)
    return RenderedPage(
        document=document,
        title=title,
        content_html=content_html,
        toc_html=toc_html,
        referenced_assets=link_rewriter.referenced_assets,
        warnings=link_rewriter.warnings,
    )


def build_toc_html(headings: list[tuple[int, str, str]]) -> str:
    if not headings:
        return ""

    items = []
    for level, title, heading_id in headings:
        items.append(
            '<li class="toc-level-{level}"><a href="#{heading_id}">{title}</a></li>'.format(
                level=level,
                heading_id=html.escape(heading_id, quote=True),
                title=html.escape(title),
            )
        )
    return (
        '<nav class="page-toc" aria-label="On this page" data-i18n-aria-label="onThisPage">'
        '<h2 data-i18n="onThisPage">On this page</h2>'
        "<ul>"
        + "".join(items)
        + "</ul>"
        "</nav>"
    )


def _extract_heading_text(token: Token | None) -> str:
    if token is None or not token.children:
        return "section"
    parts: list[str] = []
    for child in token.children:
        if child.children:
            parts.append(_extract_heading_text(child))
            continue
        if child.content:
            parts.append(child.content)
    heading_text = "".join(parts).strip()
    return heading_text or "section"


def _build_heading_id(text: str, slug_counts: dict[str, int]) -> str:
    base = _slugify_heading(text) or "section"
    count = slug_counts.get(base, 0)
    slug_counts[base] = count + 1
    if count == 0:
        return base
    return f"{base}-{count + 1}"


def add_source_line_attrs(tokens: list[Token]) -> None:
    for token in tokens:
        if token.map is None:
            continue
        if token.nesting != 1 and token.type != "fence":
            continue
        if token.type == "inline":
            continue
        source_lines = source_line_attr(token.map)
        if source_lines:
            token.attrSet("data-mdfh-source-lines", source_lines)


def source_line_attr(line_map: list[int]) -> str:
    if len(line_map) < 2:
        return ""
    start_line = line_map[0] + 1
    end_line = max(start_line, line_map[1])
    return f"{start_line}:{end_line}"


def _slugify_heading(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text.casefold())
    parts: list[str] = []
    last_was_separator = False
    for character in normalized:
        if character.isalnum():
            parts.append(character)
            last_was_separator = False
            continue
        if unicodedata.category(character).startswith("M") and parts and not last_was_separator:
            parts.append(character)
            continue
        if parts and not last_was_separator:
            parts.append("-")
            last_was_separator = True
    return "".join(parts).strip("-")


def _render_fence(
    renderer: Any,  # noqa: ARG001
    tokens: list[Token],
    index: int,
    options: Any,  # noqa: ARG001
    env: Any,  # noqa: ARG001
) -> str:
    token = tokens[index]
    language = token.info.strip().split(maxsplit=1)[0] if token.info.strip() else ""
    try:
        lexer = get_lexer_by_name(language) if language else TextLexer(stripnl=False)
    except ClassNotFound:
        lexer = TextLexer(stripnl=False)
    formatter = HtmlFormatter(cssclass="highlight")
    highlighted = highlight(token.content, lexer, formatter)
    attrs = renderer.renderAttrs(token) if hasattr(renderer, "renderAttrs") else ""
    if not attrs:
        return highlighted
    if highlighted.startswith("<div "):
        return highlighted.replace("<div ", f"<div{attrs} ", 1)
    if highlighted.startswith("<div>"):
        return highlighted.replace("<div>", f"<div{attrs}>", 1)
    return f"<div{attrs}>{highlighted}</div>"
