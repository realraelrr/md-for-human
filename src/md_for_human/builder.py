from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path, PurePosixPath
from shutil import copy2

from md_for_human.discovery import discover_site
from md_for_human.models import Document, RenderedPage
from md_for_human.navigation import build_navigation
from md_for_human.render_markdown import render_document
from md_for_human.template import render_page_html


@dataclass(slots=True)
class BuildResult:
    output_dir: Path
    entry_page: Path
    warnings: list[str]


def build_site(input_dir: Path, output_dir: Path) -> BuildResult:
    manifest = discover_site(Path(input_dir), Path(output_dir))
    rendered_pages = {
        document.output_path: render_document(document, manifest) for document in manifest.documents
    }
    nav_tree, ordered_pages = build_navigation(manifest, rendered_pages)

    warnings = list(manifest.warnings)
    for page in ordered_pages:
        warnings.extend(page.warnings)

    manifest.output_dir.mkdir(parents=True, exist_ok=True)
    for page in ordered_pages:
        page.full_html = render_page_html(
            page,
            nav_tree,
            rendered_pages,
            manifest.entry_output_path,
        )
        write_output_file(manifest.output_dir / page.document.output_path, page.full_html)

    referenced_assets = {
        asset_path for page in ordered_pages for asset_path in page.referenced_assets
    }
    for asset_path in referenced_assets:
        source_asset = manifest.input_dir / asset_path
        if not source_asset.exists():
            continue
        destination_asset = manifest.output_dir / asset_path
        destination_asset.parent.mkdir(parents=True, exist_ok=True)
        copy2(source_asset, destination_asset)

    entry_output_path = manifest.entry_output_path
    if manifest.entry_document is None:
        synthetic_page = build_synthetic_landing_page(manifest, ordered_pages)
        synthetic_page.full_html = render_page_html(
            synthetic_page,
            nav_tree,
            rendered_pages,
            manifest.entry_output_path,
        )
        write_output_file(manifest.output_dir / entry_output_path, synthetic_page.full_html)

    return BuildResult(
        output_dir=manifest.output_dir,
        entry_page=manifest.output_dir / entry_output_path,
        warnings=warnings,
    )


def build_synthetic_landing_page(manifest, ordered_pages: list[RenderedPage]) -> RenderedPage:
    links = "".join(
        f'<li><a href="{escape(page.document.output_path.as_posix(), quote=True)}">{escape(page.title)}</a></li>'
        for page in ordered_pages
    )
    content_html = (
        "<h1>Document Index</h1>"
        f"<p>Generated overview for <strong>{escape(manifest.input_dir.name)}</strong>.</p>"
        f"<ul>{links}</ul>"
    )
    document = Document(
        source_path=manifest.input_dir / "__synthetic_index__.md",
        relative_source_path=PurePosixPath("index.html"),
        output_path=PurePosixPath("index.html"),
    )
    return RenderedPage(
        document=document,
        title="Document Index",
        content_html=content_html,
    )


def write_output_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
