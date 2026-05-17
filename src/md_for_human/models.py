from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


@dataclass(slots=True)
class Document:
    source_path: Path
    relative_source_path: PurePosixPath
    output_path: PurePosixPath
    title: str | None = None

    @property
    def url(self) -> str:
        return self.output_path.as_posix()

    @property
    def source_stem(self) -> str:
        return self.relative_source_path.stem

    @property
    def display_title(self) -> str:
        return self.title or self.source_stem


@dataclass(slots=True)
class NavNode:
    name: str
    relative_path: PurePosixPath
    is_dir: bool
    document: Document | None = None
    children: list["NavNode"] = field(default_factory=list)

    @property
    def url(self) -> str | None:
        if self.document is None:
            return None
        return self.document.url


@dataclass(slots=True)
class RenderedPage:
    document: Document
    title: str
    content_html: str
    toc_html: str = ""
    referenced_assets: set[PurePosixPath] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    previous_document: Document | None = None
    next_document: Document | None = None
    full_html: str = ""


@dataclass(slots=True)
class SiteManifest:
    input_dir: Path
    output_dir: Path
    documents: list[Document]
    warnings: list[str] = field(default_factory=list)
    entry_document: Document | None = None

    @property
    def entry_output_path(self) -> PurePosixPath:
        if self.entry_document is not None:
            return self.entry_document.output_path
        return PurePosixPath("index.html")

    @property
    def has_synthetic_landing_page(self) -> bool:
        return self.entry_document is None
