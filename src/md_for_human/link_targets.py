from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from md_for_human.html_targets import rewrite_local_targets
from md_for_human.models import Document, SiteManifest
from md_for_human.urls import decode_url_path, relative_output_link


@dataclass(slots=True)
class LinkTargetRewriter:
    document: Document
    manifest: SiteManifest
    referenced_assets: set[PurePosixPath] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    _document_lookup: dict[str, Document] = field(init=False)
    _document_output_lookup: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self._document_lookup = {
            item.relative_source_path.as_posix().lower(): item
            for item in self.manifest.documents
        }
        self._document_output_lookup = {
            item.output_path.as_posix().lower() for item in self.manifest.documents
        }
        self._document_output_lookup.add(self.manifest.entry_output_path.as_posix().lower())

    def rewrite_raw_html_targets(self, content: str) -> str:
        def rewrite_target(target: str) -> str:
            if self._target_points_to_generated_page(target):
                return target
            return self.rewrite_local_target(target)

        return rewrite_local_targets(content, rewrite_target)

    def rewrite_local_target(self, raw_url: str) -> str:
        if raw_url.startswith("#"):
            return raw_url

        parsed = urlsplit(raw_url)
        if parsed.scheme or parsed.netloc:
            return raw_url

        if not parsed.path:
            return raw_url

        if parsed.path.startswith("/"):
            self.warnings.append(f"Local link points outside the input tree: {raw_url}")
            return raw_url

        decoded_path = decode_url_path(parsed.path)
        resolved_path = resolve_relative_path(
            self.document.relative_source_path.parent,
            decoded_path,
        )
        if points_outside_tree(resolved_path):
            self.warnings.append(f"Local link points outside the input tree: {raw_url}")
            return raw_url

        if resolved_path.suffix.lower() == ".md":
            target_document = self._document_lookup.get(resolved_path.as_posix().lower())
            if target_document is None:
                return raw_url
            rewritten_path = relative_output_link(
                self.document.output_path,
                target_document.output_path,
            )
            return urlunsplit(("", "", rewritten_path, parsed.query, parsed.fragment))

        self.referenced_assets.add(resolved_path)
        return raw_url

    def _target_points_to_generated_page(self, raw_url: str) -> bool:
        parsed = urlsplit(raw_url)
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
            return False
        decoded_path = decode_url_path(parsed.path)
        output_path = resolve_relative_path(self.document.output_path.parent, decoded_path)
        if points_outside_tree(output_path):
            return False
        output_label = output_path.as_posix().lower()
        if output_label in self._document_output_lookup:
            return True
        return (output_path / "index.html").as_posix().lower() in self._document_output_lookup


def resolve_relative_path(base_dir: PurePosixPath, raw_path: str) -> PurePosixPath:
    joined = posixpath.normpath(posixpath.join(base_dir.as_posix(), raw_path))
    return PurePosixPath(joined)


def points_outside_tree(relative_path: PurePosixPath) -> bool:
    normalized = relative_path.as_posix()
    return normalized == ".." or normalized.startswith(("../", "/"))
