from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from md_for_human.models import Document, SiteManifest


class DiscoveryError(ValueError):
    """Raised when the source tree cannot be converted into a stable manifest."""


def discover_site(input_dir: Path, output_dir: Path) -> SiteManifest:
    source_path = Path(input_dir).resolve()
    destination = Path(output_dir)
    documents: list[Document] = []
    warnings: list[str] = []
    seen_outputs: dict[str, PurePosixPath] = {}

    if not source_path.exists():
        raise DiscoveryError(f"Input path does not exist: {input_dir}")

    if source_path.is_file():
        if source_path.suffix.lower() != ".md":
            raise DiscoveryError(f"Input file is not Markdown: {input_dir}")
        root = source_path.parent
        document = register_document(source_path, root, documents, seen_outputs)
        return SiteManifest(
            input_dir=root,
            output_dir=destination,
            documents=documents,
            warnings=warnings,
            entry_document=document,
        )

    root = source_path

    for current_root, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current_root)

        kept_dirnames: list[str] = []
        for dirname in sorted(dirnames):
            dir_path = current_path / dirname
            if dir_path.is_symlink():
                warnings.append(f"Skipping symlinked directory: {dir_path.relative_to(root)}")
                continue
            kept_dirnames.append(dirname)
        dirnames[:] = kept_dirnames

        for filename in sorted(filenames):
            file_path = current_path / filename
            if file_path.is_symlink():
                warnings.append(f"Skipping symlinked file: {file_path.relative_to(root)}")
                continue
            if file_path.suffix.lower() != ".md":
                continue

            register_document(file_path, root, documents, seen_outputs)

    if not documents:
        raise DiscoveryError("No Markdown files found in input directory.")

    documents.sort(key=lambda document: document.relative_source_path.as_posix())
    entry_document = next(
        (document for document in documents if document.output_path == PurePosixPath("index.html")),
        None,
    )
    return SiteManifest(
        input_dir=root,
        output_dir=destination,
        documents=documents,
        warnings=warnings,
        entry_document=entry_document,
    )


def map_output_path(relative_source_path: PurePosixPath) -> tuple[PurePosixPath, bool]:
    if relative_source_path.name.lower() in {"readme.md", "index.md"}:
        return relative_source_path.parent / "index.html", True
    return relative_source_path.with_suffix(".html"), False


def register_document(
    file_path: Path,
    root: Path,
    documents: list[Document],
    seen_outputs: dict[str, PurePosixPath],
) -> Document:
    relative_source_path = PurePosixPath(file_path.relative_to(root).as_posix())
    output_path, is_directory_index = map_output_path(relative_source_path)
    collision_key = output_path.as_posix().lower()
    previous_path = seen_outputs.get(collision_key)
    if previous_path is not None:
        raise DiscoveryError(
            f"Output collision detected for {output_path.as_posix()} from "
            f"{previous_path.as_posix()} and {relative_source_path.as_posix()}"
        )

    seen_outputs[collision_key] = relative_source_path
    document = Document(
        source_path=file_path,
        relative_source_path=relative_source_path,
        output_path=output_path,
        is_directory_index=is_directory_index,
    )
    documents.append(document)
    return document
