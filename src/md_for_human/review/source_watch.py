from __future__ import annotations

from pathlib import Path
from typing import Any

from md_for_human.review.validate import is_safe_relative_posix_path


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
    page = annotation.get("page")
    source_path = annotation.get("source_path")
    if not isinstance(page, str) or not is_safe_relative_posix_path(page):
        return None
    if source_path is not None and (
        not isinstance(source_path, str) or not is_safe_relative_posix_path(source_path)
    ):
        return None
    document = documents.get(page)
    if document is None:
        return f'page "{page}" is no longer listed in manifest documents'
    if isinstance(source_path, str) and source_path != document.source_path:
        return (
            f'source_path "{source_path}" no longer matches manifest source_path '
            f'"{document.source_path}" for page "{page}"'
        )
    return None
