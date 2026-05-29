from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urlsplit


class LocalTargetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.targets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name not in {"href", "src"} or not value:
                continue
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc:
                continue
            self.targets.append(value.split("?", 1)[0].split("#", 1)[0] or value)


def extract_local_targets(html: str) -> list[str]:
    parser = LocalTargetParser()
    parser.feed(html)
    return parser.targets


class LocalTargetRewriteParser(HTMLParser):
    def __init__(self, rewrite_target: Callable[[str], str]) -> None:
        super().__init__(convert_charrefs=False)
        self.rewrite_target = rewrite_target
        self.parts: list[str] = []
        self.changed = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(self._render_start_tag(tag, attrs, self_closing=False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(self._render_start_tag(tag, attrs, self_closing=True))

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.parts.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self.parts.append(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        self.parts.append(f"<![{data}]>")

    def _render_start_tag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        self_closing: bool,
    ) -> str:
        attr_html: list[str] = []
        for name, value in attrs:
            if value is None:
                attr_html.append(f" {name}")
                continue
            rewritten_value = value
            if name in {"href", "src"} and value:
                rewritten_value = self.rewrite_target(value)
                if rewritten_value != value:
                    self.changed = True
            attr_html.append(f' {name}="{escape(rewritten_value, quote=True)}"')
        suffix = " /" if self_closing else ""
        return f"<{tag}{''.join(attr_html)}{suffix}>"


def rewrite_local_targets(html: str, rewrite_target: Callable[[str], str]) -> str:
    parser = LocalTargetRewriteParser(rewrite_target)
    parser.feed(html)
    if not parser.changed:
        return html
    return "".join(parser.parts)
