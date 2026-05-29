from __future__ import annotations

from importlib.resources import files


def load_asset_text(name: str) -> str:
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"Asset name must be a simple filename: {name}")
    return files(__package__).joinpath(name).read_text(encoding="utf-8")
