from __future__ import annotations

from pathlib import Path


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
