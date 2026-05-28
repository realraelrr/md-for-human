from __future__ import annotations

from html.parser import HTMLParser


class LocalTargetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.targets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name not in {"href", "src"} or not value:
                continue
            if value.startswith(("http://", "https://", "mailto:", "tel:", "data:")):
                continue
            self.targets.append(value.split("?", 1)[0].split("#", 1)[0] or value)


def extract_local_targets(html: str) -> list[str]:
    parser = LocalTargetParser()
    parser.feed(html)
    return parser.targets
