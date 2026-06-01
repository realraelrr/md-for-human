from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path, PurePosixPath
from shutil import copy2

from md_for_human.discovery import discover_site
from md_for_human.models import Document, NavNode, RenderedPage, SiteManifest
from md_for_human.navigation import build_navigation
from md_for_human.protocol import MANIFEST_SCHEMA_VERSION, TOOL_NAME, TOOL_VERSION
from md_for_human.render_markdown import render_document
from md_for_human.template import render_page_html
from md_for_human.urls import encode_url_path


@dataclass(slots=True)
class BuildResult:
    output_dir: Path
    entry_page: Path
    warnings: list[str]
    pages: list[str]
    copied_assets: list[str]
    manifest_path: Path


def build_site(input_dir: Path, output_dir: Path) -> BuildResult:
    manifest = discover_site(Path(input_dir), Path(output_dir))
    rendered_pages = render_documents(manifest)
    nav_tree, ordered_pages = build_navigation(manifest, rendered_pages)
    warnings = collect_warnings(manifest, ordered_pages)

    manifest.output_dir.mkdir(parents=True, exist_ok=True)
    pages = write_rendered_pages(manifest, ordered_pages, nav_tree, rendered_pages)
    copied_assets = copy_referenced_assets(manifest, ordered_pages, warnings)

    entry_output_path = manifest.entry_output_path
    if manifest.entry_document is None:
        write_synthetic_landing_page(manifest, ordered_pages, nav_tree, rendered_pages)
        pages.insert(0, entry_output_path.as_posix())

    manifest_path = write_agent_manifest(
        manifest.output_dir,
        entry_output_path.as_posix(),
        pages,
        copied_assets,
        warnings,
        manifest.documents,
    )

    return BuildResult(
        output_dir=manifest.output_dir,
        entry_page=manifest.output_dir / entry_output_path,
        warnings=warnings,
        pages=pages,
        copied_assets=copied_assets,
        manifest_path=manifest_path,
    )


def render_documents(manifest: SiteManifest) -> dict[PurePosixPath, RenderedPage]:
    return {
        document.output_path: render_document(document, manifest)
        for document in manifest.documents
    }


def collect_warnings(manifest: SiteManifest, ordered_pages: list[RenderedPage]) -> list[str]:
    warnings = list(manifest.warnings)
    for page in ordered_pages:
        warnings.extend(page.warnings)
    return warnings


def write_rendered_pages(
    manifest: SiteManifest,
    ordered_pages: list[RenderedPage],
    nav_tree: list[NavNode],
    rendered_pages: dict[PurePosixPath, RenderedPage],
) -> list[str]:
    pages: list[str] = []
    for page in ordered_pages:
        page.full_html = render_page_html(page, nav_tree, rendered_pages)
        write_output_file(manifest.output_dir / page.document.output_path, page.full_html)
        pages.append(page.document.output_path.as_posix())
    return pages


def copy_referenced_assets(
    manifest: SiteManifest,
    ordered_pages: list[RenderedPage],
    warnings: list[str],
) -> list[str]:
    referenced_assets = {
        asset_path for page in ordered_pages for asset_path in page.referenced_assets
    }
    copied_assets: list[str] = []
    for asset_path in sorted(referenced_assets, key=lambda path: path.as_posix()):
        source_asset = manifest.input_dir / asset_path
        asset_label = asset_path.as_posix()
        if not source_asset.exists():
            warnings.append(f"Missing referenced asset: {asset_label}")
            continue
        if source_asset.is_symlink():
            warnings.append(f"Skipping symlinked asset: {asset_label}")
            continue
        if not asset_stays_inside_root(source_asset, manifest.input_dir):
            warnings.append(f"Skipping asset outside input tree after resolving: {asset_label}")
            continue
        if not source_asset.is_file():
            warnings.append(f"Skipping referenced asset that is not a file: {asset_label}")
            continue
        destination_asset = manifest.output_dir / asset_path
        destination_asset.parent.mkdir(parents=True, exist_ok=True)
        copy2(source_asset, destination_asset)
        copied_assets.append(asset_label)
    return copied_assets


def write_synthetic_landing_page(
    manifest: SiteManifest,
    ordered_pages: list[RenderedPage],
    nav_tree: list[NavNode],
    rendered_pages: dict[PurePosixPath, RenderedPage],
) -> None:
    synthetic_page = build_synthetic_landing_page(manifest, ordered_pages)
    synthetic_page.full_html = render_page_html(synthetic_page, nav_tree, rendered_pages)
    write_output_file(
        manifest.output_dir / manifest.entry_output_path,
        synthetic_page.full_html,
    )


def build_site_preserving_review(input_dir: Path, output_dir: Path) -> BuildResult:
    """Rebuild a site atomically enough for review mode while keeping review artifacts."""
    output_dir = Path(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.rebuild-", dir=output_dir.parent)
    )
    try:
        staging_result = build_site(Path(input_dir), staging_dir)
        entry_relative = staging_result.entry_page.relative_to(staging_dir)
        replace_output_preserving_review(staging_dir, output_dir)
        return BuildResult(
            output_dir=output_dir,
            entry_page=output_dir / entry_relative,
            warnings=staging_result.warnings,
            pages=staging_result.pages,
            copied_assets=staging_result.copied_assets,
            manifest_path=output_dir / ".md-for-human" / "manifest.json",
        )
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def replace_output_preserving_review(staging_dir: Path, output_dir: Path) -> None:
    review_dir = output_dir / ".md-for-human" / "review"
    review_backup_root: Path | None = None
    if review_dir.exists():
        review_backup_root = Path(
            tempfile.mkdtemp(prefix=".mdfh-review-preserve-", dir=output_dir.parent)
        )
        shutil.copytree(review_dir, review_backup_root / "review")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.move(str(staging_dir), str(output_dir))

    if review_backup_root is not None:
        restored_review_dir = output_dir / ".md-for-human" / "review"
        if restored_review_dir.exists():
            shutil.rmtree(restored_review_dir)
        restored_review_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(review_backup_root / "review", restored_review_dir)
        shutil.rmtree(review_backup_root, ignore_errors=True)


def build_synthetic_landing_page(
    manifest: SiteManifest, ordered_pages: list[RenderedPage]
) -> RenderedPage:
    links = "".join(
        f'<li><a href="{escape(encode_url_path(page.document.output_path.as_posix()), quote=True)}">'
        f"{escape(page.title)}</a></li>"
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


def asset_stays_inside_root(path: Path, root: Path) -> bool:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def write_agent_manifest(
    output_dir: Path,
    entry_page: str,
    pages: list[str],
    copied_assets: list[str],
    warnings: list[str],
    documents: list[Document],
) -> Path:
    manifest_path = output_dir / ".md-for-human" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
                "tool_name": TOOL_NAME,
                "tool_version": TOOL_VERSION,
                "entry_page": entry_page,
                "pages": pages,
                "documents": [
                    {
                        "page": document.output_path.as_posix(),
                        "source_path": document.relative_source_path.as_posix(),
                        "source_line_count": source_line_count(document.source_path),
                        "source_sha256": hashlib.sha256(
                            document.source_path.read_bytes()
                        ).hexdigest(),
                    }
                    for document in documents
                ],
                "copied_assets": copied_assets,
                "warnings": warnings,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def source_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())
