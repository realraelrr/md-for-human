from __future__ import annotations

from pathlib import Path
from shutil import copytree

import pytest


@pytest.fixture
def sample_site_path() -> Path:
    return Path(__file__).parent / "fixtures" / "sample_site"


@pytest.fixture
def sample_site_copy(tmp_path: Path, sample_site_path: Path) -> Path:
    destination = tmp_path / "sample_site"
    copytree(sample_site_path, destination)
    return destination


@pytest.fixture
def sample_site_output_dir(tmp_path: Path) -> Path:
    return tmp_path / "sample-site-output"
