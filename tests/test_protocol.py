from __future__ import annotations

import tomllib
from pathlib import Path

from md_for_human.protocol import TOOL_VERSION


def test_tool_version_matches_project_version():
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert TOOL_VERSION == pyproject["project"]["version"]
