from __future__ import annotations

import io
from pathlib import Path

from md_for_human.cli import main


def test_cli_builds_sample_site_end_to_end(
    sample_site_path: Path,
    sample_site_output_dir: Path,
):
    opener_calls: list[str] = []
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = main(
        [str(sample_site_path), "--output", str(sample_site_output_dir)],
        opener=opener_calls.append,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert opener_calls == [(sample_site_output_dir / "index.html").resolve().as_uri()]
    assert (sample_site_output_dir / "index.html").exists()
    assert (sample_site_output_dir / "guide" / "intro.html").exists()
    assert (sample_site_output_dir / "guide" / "setup.html").exists()
    assert (sample_site_output_dir / "reference" / "index.html").exists()
    assert (sample_site_output_dir / "images" / "diagram.png").exists()
    assert not (sample_site_output_dir / "images" / "unused.png").exists()
    assert stderr.getvalue() == ""
