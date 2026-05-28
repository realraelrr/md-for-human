from __future__ import annotations

import posixpath
from pathlib import PurePosixPath
from urllib.parse import quote, unquote


def decode_url_path(path: str) -> str:
    return unquote(path)


def encode_url_path(path: str) -> str:
    return quote(path, safe="/")


def relative_output_link(source_output: PurePosixPath, target_output: PurePosixPath) -> str:
    source_dir = source_output.parent.as_posix() or "."
    relative_path = posixpath.relpath(target_output.as_posix(), start=source_dir)
    if relative_path == ".":
        relative_path = target_output.name
    return encode_url_path(relative_path)
