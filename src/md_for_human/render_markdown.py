from __future__ import annotations

import html
import posixpath
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from md_for_human.models import Document, RenderedPage, SiteManifest
from md_for_human.urls import decode_url_path, relative_output_link


def render_document(document: Document, manifest: SiteManifest) -> RenderedPage:
    parser = MarkdownIt("commonmark").enable("table")
    parser.add_render_rule("fence", _render_fence)

    source_text = document.source_path.read_text(encoding="utf-8")
    tokens = parser.parse(source_text)
    document_lookup = {
        item.relative_source_path.as_posix().lower(): item for item in manifest.documents
    }
    warnings: list[str] = []
    referenced_assets: set[PurePosixPath] = set()
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

        if token.type != "inline" or not token.children:
            continue

        for child in token.children:
            if child.type == "link_open":
                href = child.attrGet("href")
                if isinstance(href, str) and href:
                    child.attrSet(
                        "href",
                        _rewrite_local_target(
                            raw_url=href,
                            document=document,
                            document_lookup=document_lookup,
                            referenced_assets=referenced_assets,
                            warnings=warnings,
                        ),
                    )
            elif child.type == "image":
                src = child.attrGet("src")
                if isinstance(src, str) and src:
                    child.attrSet(
                        "src",
                        _rewrite_local_target(
                            raw_url=src,
                            document=document,
                            document_lookup=document_lookup,
                            referenced_assets=referenced_assets,
                            warnings=warnings,
                        ),
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
        referenced_assets=referenced_assets,
        warnings=warnings,
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
        '<nav class="page-toc" aria-label="On this page">'
        "<h2>On this page</h2>"
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
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
    count = slug_counts.get(base, 0)
    slug_counts[base] = count + 1
    if count == 0:
        return base
    return f"{base}-{count + 1}"


def _rewrite_local_target(
    raw_url: str,
    document: Document,
    document_lookup: dict[str, Document],
    referenced_assets: set[PurePosixPath],
    warnings: list[str],
) -> str:
    if raw_url.startswith("#"):
        return raw_url

    parsed = urlsplit(raw_url)
    if parsed.scheme or parsed.netloc:
        return raw_url

    if not parsed.path:
        return raw_url

    if parsed.path.startswith("/"):
        warnings.append(f"Local link points outside the input tree: {raw_url}")
        return raw_url

    decoded_path = decode_url_path(parsed.path)
    resolved_path = _resolve_relative_path(document.relative_source_path.parent, decoded_path)
    if _points_outside_tree(resolved_path):
        warnings.append(f"Local link points outside the input tree: {raw_url}")
        return raw_url

    if resolved_path.suffix.lower() == ".md":
        target_document = document_lookup.get(resolved_path.as_posix().lower())
        if target_document is None:
            return raw_url
        rewritten_path = relative_output_link(document.output_path, target_document.output_path)
        return urlunsplit(("", "", rewritten_path, parsed.query, parsed.fragment))

    referenced_assets.add(resolved_path)
    return raw_url


def _resolve_relative_path(base_dir: PurePosixPath, raw_path: str) -> PurePosixPath:
    joined = posixpath.normpath(posixpath.join(base_dir.as_posix(), raw_path))
    return PurePosixPath(joined)


def _points_outside_tree(relative_path: PurePosixPath) -> bool:
    normalized = relative_path.as_posix()
    return normalized == ".." or normalized.startswith(("../", "/"))


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
    return highlight(token.content, lexer, formatter)
