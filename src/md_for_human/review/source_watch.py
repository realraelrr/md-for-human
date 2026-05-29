from __future__ import annotations

from pathlib import Path
from typing import Any

from md_for_human.review.archive import archive_annotation_status


def snapshot_source_tree(source_input: Path) -> dict[str, tuple[int, int]]:
    source_input = Path(source_input)
    if source_input.is_file() or source_input.is_symlink():
        return {source_input.name: stat_signature(source_input)}
    if not source_input.exists():
        return {}
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sorted(source_input.rglob("*")):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(source_input).as_posix()
        snapshot[relative] = stat_signature(path)
    return snapshot


def stat_signature(path: Path) -> tuple[int, int]:
    stat_result = path.lstat()
    return stat_result.st_mtime_ns, stat_result.st_size


def stale_annotation_reason(
    annotation: dict[str, Any],
    documents: dict[str, Any],
) -> str | None:
    archive_reason, _current_source_sha256 = archive_annotation_status(annotation, documents)
    if archive_reason == "source_removed":
        page = annotation.get("page")
        return f'page "{page}" is no longer listed in manifest documents'
    if archive_reason == "source_path_changed":
        page = annotation.get("page")
        source_path = annotation.get("source_path")
        document = documents.get(page) if isinstance(page, str) else None
        expected_source_path = document.source_path if document is not None else ""
        return (
            f'source_path "{source_path}" no longer matches manifest source_path '
            f'"{expected_source_path}" for page "{page}"'
        )
    return None
