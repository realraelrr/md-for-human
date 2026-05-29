from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from md_for_human.cli import main


def _write_review_artifact(output_dir: Path, *, quote: str) -> None:
    review_dir = output_dir / ".md-for-human" / "review"
    review_dir.mkdir(parents=True)
    (review_dir / "annotations.json").write_text(
        json.dumps(
            {
                "schema_version": "mdfh-review-v1",
                "created_by": {"kind": "agent", "name": "codex"},
                "source_manifest": ".md-for-human/manifest.json",
                "annotations": [
                    {
                        "id": "ann_cli",
                        "type": "comment",
                        "page": "guide/setup.html",
                        "source_path": "guide/setup.md",
                        "quote": quote,
                        "note": "CLI validation should report this review artifact.",
                        "created_at": "2026-05-28T12:00:00Z",
                        "updated_at": "2026-05-28T12:00:00Z",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_python_m_md_for_human_help_displays_expected_options():
    result = subprocess.run(
        [sys.executable, "-m", "md_for_human", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "md-for-human" in result.stdout
    assert "--output" in result.stdout
    assert "--no-open" in result.stdout
    assert "--overwrite" in result.stdout
    assert "--verify" in result.stdout
    assert "--fail-on-warning" in result.stdout
    assert "--strict" in result.stdout
    assert "--validate-review" in result.stdout
    assert "--review" in result.stdout


def test_main_builds_site_without_opening_browser_when_no_open(
    sample_site_copy: Path,
    tmp_path: Path,
):
    opener_calls: list[str] = []
    stdout = io.StringIO()
    stderr = io.StringIO()
    output_dir = tmp_path / "output"

    result = main(
        [str(sample_site_copy), "--output", str(output_dir), "--no-open"],
        opener=opener_calls.append,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert opener_calls == []
    assert (output_dir / "index.html").exists()
    assert "Built site at:" in stdout.getvalue()
    assert "Output directory:" in stdout.getvalue()
    assert "Pages: 5" in stdout.getvalue()
    assert "Assets copied: 1" in stdout.getvalue()
    assert "Warnings: 0" in stdout.getvalue()
    assert "Browser opened: no" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_main_opens_browser_once_on_success(sample_site_copy: Path, tmp_path: Path):
    opener_calls: list[str] = []
    stdout = io.StringIO()
    output_dir = tmp_path / "output"

    result = main(
        [str(sample_site_copy), "--output", str(output_dir)],
        opener=opener_calls.append,
        stdout=stdout,
        stderr=io.StringIO(),
    )

    assert result == 0
    assert opener_calls == [(output_dir / "index.html").resolve().as_uri()]
    assert "Browser opened: yes" in stdout.getvalue()


def test_main_reports_browser_not_opened_when_opener_returns_false(
    sample_site_copy: Path,
    tmp_path: Path,
):
    opener_calls: list[str] = []
    stdout = io.StringIO()
    output_dir = tmp_path / "output"

    def opener(url: str) -> bool:
        opener_calls.append(url)
        return False

    result = main(
        [str(sample_site_copy), "--output", str(output_dir)],
        opener=opener,
        stdout=stdout,
        stderr=io.StringIO(),
    )

    assert result == 0
    assert opener_calls == [(output_dir / "index.html").resolve().as_uri()]
    assert "Browser opened: no" in stdout.getvalue()


def test_main_does_not_open_browser_on_failure(tmp_path: Path):
    opener_calls: list[str] = []
    stderr = io.StringIO()

    result = main(
        [str(tmp_path / "missing-site")],
        opener=opener_calls.append,
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert result != 0
    assert opener_calls == []
    assert "does not exist" in stderr.getvalue()


def test_main_rejects_invalid_output_path(sample_site_copy: Path):
    stderr = io.StringIO()

    result = main(
        [str(sample_site_copy), "--output", str(sample_site_copy), "--no-open"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert result != 0
    assert "same as the input directory" in stderr.getvalue()


def test_main_rejects_file_output_that_would_delete_input_parent(tmp_path: Path):
    stderr = io.StringIO()
    input_file = tmp_path / "notes.md"
    sibling_file = tmp_path / "keep.txt"
    input_file.write_text("# Notes\n", encoding="utf-8")
    sibling_file.write_text("keep", encoding="utf-8")

    result = main(
        [str(input_file), "--output", str(tmp_path), "--overwrite", "--no-open"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert result != 0
    assert "ancestor of the input Markdown file" in stderr.getvalue()
    assert input_file.exists()
    assert sibling_file.exists()


def test_main_rejects_file_output_parent_alias_with_dotdot(tmp_path: Path):
    stderr = io.StringIO()
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    input_file = docs_dir / "notes.md"
    sibling_file = docs_dir / "keep.txt"
    input_file.write_text("# Notes\n", encoding="utf-8")
    sibling_file.write_text("keep", encoding="utf-8")
    output_alias = docs_dir / ".." / "docs"

    result = main(
        [str(input_file), "--output", str(output_alias), "--overwrite", "--no-open"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert result != 0
    assert "ancestor of the input Markdown file" in stderr.getvalue()
    assert input_file.exists()
    assert sibling_file.exists()


def test_main_rejects_output_inside_input_through_symlinked_parent(tmp_path: Path):
    stderr = io.StringIO()
    input_dir = tmp_path / "input"
    protected_dir = input_dir / "protected"
    protected_dir.mkdir(parents=True)
    input_file = protected_dir / "notes.md"
    sibling_file = protected_dir / "keep.txt"
    input_file.write_text("# Notes\n", encoding="utf-8")
    sibling_file.write_text("keep", encoding="utf-8")
    input_link = tmp_path / "input-link"
    input_link.symlink_to(input_dir, target_is_directory=True)
    output_alias = input_link / "protected"

    result = main(
        [str(input_dir), "--output", str(output_alias), "--overwrite", "--no-open"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert result != 0
    assert "inside the input directory" in stderr.getvalue()
    assert input_file.exists()
    assert sibling_file.exists()


def test_main_overwrites_existing_custom_output_when_requested(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    stale_file = output_dir / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    result = main(
        [str(sample_site_copy), "--output", str(output_dir), "--overwrite", "--no-open"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert result == 0
    assert not stale_file.exists()
    assert (output_dir / "index.html").exists()


def test_main_overwrites_output_symlink_without_deleting_target(
    sample_site_copy: Path,
    tmp_path: Path,
):
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    sentinel = target_dir / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    output_link = tmp_path / "output-link"
    output_link.symlink_to(target_dir, target_is_directory=True)

    result = main(
        [str(sample_site_copy), "--output", str(output_link), "--overwrite", "--no-open"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert result == 0
    assert sentinel.exists()
    assert not output_link.is_symlink()
    assert (output_link / "index.html").exists()


def test_main_overwrites_broken_output_symlink(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_link = tmp_path / "broken-output-link"
    output_link.symlink_to(tmp_path / "missing-target", target_is_directory=True)

    result = main(
        [str(sample_site_copy), "--output", str(output_link), "--overwrite", "--no-open"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert result == 0
    assert not output_link.is_symlink()
    assert (output_link / "index.html").exists()


def test_main_reports_output_symlink_loop_as_cli_error(
    sample_site_copy: Path,
    tmp_path: Path,
):
    stderr = io.StringIO()
    loop = tmp_path / "loop"
    loop.symlink_to(loop, target_is_directory=True)

    result = main(
        [str(sample_site_copy), "--output", str(loop / "output"), "--no-open"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert result != 0
    assert "Could not resolve output directory" in stderr.getvalue()


def test_main_accepts_single_markdown_file_input(
    tmp_path: Path,
):
    opener_calls: list[str] = []
    stdout = io.StringIO()
    stderr = io.StringIO()
    input_file = tmp_path / "notes.md"
    input_file.write_text("# Notes\n\nSingle file input.\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    result = main(
        [str(input_file), "--output", str(output_dir), "--no-open"],
        opener=opener_calls.append,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert opener_calls == []
    assert (output_dir / "notes.html").exists()
    assert stderr.getvalue() == ""


def test_main_writes_manifest_and_verify_passes(sample_site_copy: Path, tmp_path: Path):
    stdout = io.StringIO()
    stderr = io.StringIO()
    output_dir = tmp_path / "output"

    result = main(
        [str(sample_site_copy), "--output", str(output_dir), "--verify", "--no-open"],
        opener=lambda *_: None,
        stdout=stdout,
        stderr=stderr,
    )
    manifest = json.loads(
        (output_dir / ".md-for-human" / "manifest.json").read_text(encoding="utf-8")
    )

    assert result == 0
    assert "Verification: passed" in stdout.getvalue()
    assert manifest["entry_page"] == "index.html"
    assert manifest["pages"][0] == "index.html"
    assert manifest["copied_assets"] == ["images/diagram.png"]
    assert stderr.getvalue() == ""


def test_main_verify_accepts_single_file_entry_page(tmp_path: Path):
    stdout = io.StringIO()
    stderr = io.StringIO()
    input_file = tmp_path / "notes.md"
    input_file.write_text("# Notes\n\nOne file.\n", encoding="utf-8")
    output_dir = tmp_path / "output"

    result = main(
        [str(input_file), "--output", str(output_dir), "--verify", "--no-open"],
        opener=lambda *_: None,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert (output_dir / "notes.html").exists()
    assert "Verification: passed" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_main_verify_accepts_url_encoded_local_links_and_assets(tmp_path: Path):
    stdout = io.StringIO()
    stderr = io.StringIO()
    input_dir = tmp_path / "docs"
    images_dir = input_dir / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "diagram image.png").write_bytes(b"png")
    (input_dir / "space file.md").write_text("# Space File\n", encoding="utf-8")
    (input_dir / "index.md").write_text(
        "\n".join(
            [
                "# Index",
                "",
                "[Encoded](space%20file.md)",
                "",
                "![Diagram](images/diagram%20image.png)",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    result = main(
        [str(input_dir), "--output", str(output_dir), "--verify", "--no-open"],
        opener=lambda *_: None,
        stdout=stdout,
        stderr=stderr,
    )
    index_html = (output_dir / "index.html").read_text(encoding="utf-8")

    assert result == 0
    assert 'href="space%20file.html"' in index_html
    assert 'src="images/diagram%20image.png"' in index_html
    assert (output_dir / "images" / "diagram image.png").exists()
    assert "Verification: passed" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_main_verify_accepts_query_only_local_links(tmp_path: Path):
    stdout = io.StringIO()
    stderr = io.StringIO()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "index.md").write_text(
        "\n".join(
            [
                "# Index",
                "",
                "[Filtered](?view=full)",
                "",
                '<a href="?raw=1">Raw</a>',
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    result = main(
        [str(input_dir), "--output", str(output_dir), "--verify", "--no-open"],
        opener=lambda *_: None,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert 'href="?view=full"' in (output_dir / "index.html").read_text(encoding="utf-8")
    assert "Verification: passed" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_main_verify_ignores_javascript_scheme_links(tmp_path: Path):
    stdout = io.StringIO()
    stderr = io.StringIO()
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "index.md").write_text(
        "\n".join(
            [
                "# Index",
                "",
                '<a href="javascript:alert(1)">JS action</a>',
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"

    result = main(
        [str(input_dir), "--output", str(output_dir), "--verify", "--no-open"],
        opener=lambda *_: None,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert 'href="javascript:alert(1)"' in (
        output_dir / "index.html"
    ).read_text(encoding="utf-8")
    assert "Verification: passed" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_main_validate_review_reports_success_without_rebuilding(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_stdout = io.StringIO()
    assert (
        main(
            [str(sample_site_copy), "--output", str(output_dir), "--no-open"],
            opener=lambda *_: None,
            stdout=build_stdout,
            stderr=io.StringIO(),
        )
        == 0
    )
    _write_review_artifact(output_dir, quote="Run the setup steps here.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    opener_calls: list[str] = []

    result = main(
        ["--validate-review", str(output_dir)],
        opener=opener_calls.append,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert opener_calls == []
    assert "Review validation: passed" in stdout.getvalue()
    assert "Annotations: 1" in stdout.getvalue()
    assert "Pages touched: 1" in stdout.getvalue()
    assert "Warnings: 0" in stdout.getvalue()
    assert "Review summary: " in stdout.getvalue()
    assert (output_dir / ".md-for-human" / "review" / "review.md").exists()
    assert stderr.getvalue() == ""


def test_main_validate_review_fail_on_warning_returns_error(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    assert (
        main(
            [str(sample_site_copy), "--output", str(output_dir), "--no-open"],
            opener=lambda *_: None,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == 0
    )
    _write_review_artifact(output_dir, quote="Missing quote.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = main(
        ["--validate-review", str(output_dir), "--fail-on-warning"],
        opener=lambda *_: None,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert "Review validation: failed" in stdout.getvalue()
    assert "Warnings: 1" in stdout.getvalue()
    assert "ann_cli: quote not found in guide/setup.html" in stderr.getvalue()


def test_main_validate_review_strict_fails_on_warning(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    assert (
        main(
            [str(sample_site_copy), "--output", str(output_dir), "--no-open"],
            opener=lambda *_: None,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == 0
    )
    _write_review_artifact(output_dir, quote="Missing quote.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = main(
        ["--validate-review", str(output_dir), "--strict"],
        opener=lambda *_: None,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert "Review validation: failed" in stdout.getvalue()
    assert "Warnings: 1" in stdout.getvalue()
    assert "Failing because review warnings were emitted." in stderr.getvalue()


def test_main_review_serves_existing_output_without_rebuilding(
    sample_site_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output_dir = tmp_path / "output"
    assert (
        main(
            [str(sample_site_copy), "--output", str(output_dir), "--no-open"],
            opener=lambda *_: None,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == 0
    )
    html_path = output_dir / "guide" / "setup.html"
    original_html = html_path.read_text(encoding="utf-8")
    served: list[Path] = []

    def fail_build_site(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("--review must not rebuild input")

    def fake_serve_review(path: Path, *_args: object, **_kwargs: object) -> int:
        served.append(path)
        return 0

    monkeypatch.setattr("md_for_human.cli.build_site", fail_build_site)
    monkeypatch.setattr("md_for_human.cli.serve_review", fake_serve_review)

    result = main(
        ["--review", str(output_dir)],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert result == 0
    assert served == [output_dir]
    assert html_path.read_text(encoding="utf-8") == original_html


def test_main_build_integrated_review_builds_then_serves_with_source_watch(
    sample_site_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    built: list[tuple[Path, Path]] = []
    served: list[tuple[Path, Path | None]] = []

    def fake_build_site_preserving_review(input_path: Path, output_path: Path) -> object:
        built.append((input_path, output_path))
        (output_path / ".md-for-human").mkdir(parents=True)
        (output_path / ".md-for-human" / "manifest.json").write_text(
            '{"entry_page":"index.html","pages":["index.html"],"documents":[],"copied_assets":[],"warnings":[]}\n',
            encoding="utf-8",
        )
        return object()

    def fake_serve_review(
        path: Path,
        *_args: object,
        source_input: Path | None = None,
        **_kwargs: object,
    ) -> int:
        served.append((path, source_input))
        return 0

    monkeypatch.setattr(
        "md_for_human.cli.build_site_preserving_review",
        fake_build_site_preserving_review,
    )
    monkeypatch.setattr("md_for_human.cli.serve_review", fake_serve_review)

    result = main(
        [str(sample_site_copy), "--output", str(output_dir), "--review", "--overwrite"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert result == 0
    assert built == [(sample_site_copy.resolve(), output_dir)]
    assert served == [(output_dir.resolve(), sample_site_copy.resolve())]


def test_main_integrated_review_requires_overwrite_for_existing_custom_output(
    sample_site_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    sentinel = output_dir / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    stderr = io.StringIO()

    def fail_build_site_preserving_review(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("integrated review must reject before rebuilding")

    def fail_serve_review(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("integrated review must reject before serving")

    monkeypatch.setattr(
        "md_for_human.cli.build_site_preserving_review",
        fail_build_site_preserving_review,
    )
    monkeypatch.setattr("md_for_human.cli.serve_review", fail_serve_review)

    result = main(
        [str(sample_site_copy), "--output", str(output_dir), "--review"],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert result == 1
    assert "Use --overwrite to replace it" in stderr.getvalue()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_main_review_rejects_output_without_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    stderr = io.StringIO()

    def fail_serve_review(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("--review must not start without manifest")

    monkeypatch.setattr("md_for_human.cli.serve_review", fail_serve_review)

    result = main(
        ["--review", str(output_dir)],
        opener=lambda *_: None,
        stdout=io.StringIO(),
        stderr=stderr,
    )

    assert result == 1
    assert "manifest.json" in stderr.getvalue()


def test_main_fail_on_warning_returns_error_after_reporting_warnings(tmp_path: Path):
    stdout = io.StringIO()
    stderr = io.StringIO()
    opener_calls: list[str] = []
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "page.md").write_text("# Page\n\n![Missing](missing.png)\n", encoding="utf-8")

    result = main(
        [str(input_dir), "--output", str(tmp_path / "output"), "--fail-on-warning"],
        opener=opener_calls.append,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert opener_calls == []
    assert "Browser opened: no" in stdout.getvalue()
    assert "Warnings: 1" in stdout.getvalue()
    assert "Missing referenced asset: missing.png" in stderr.getvalue()
    assert "Failing because warnings were emitted." in stderr.getvalue()


def test_main_strict_combines_verify_fail_on_warning_and_no_open(tmp_path: Path):
    stdout = io.StringIO()
    stderr = io.StringIO()
    opener_calls: list[str] = []
    input_dir = tmp_path / "docs"
    input_dir.mkdir()
    (input_dir / "page.md").write_text("# Page\n\n![Missing](missing.png)\n", encoding="utf-8")

    result = main(
        [str(input_dir), "--output", str(tmp_path / "output"), "--strict"],
        opener=opener_calls.append,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert opener_calls == []
    assert "Browser opened: no" in stdout.getvalue()
    assert "Verification: failed" in stdout.getvalue()
    assert "Missing referenced asset: missing.png" in stderr.getvalue()
    assert "Local target missing from page.html: missing.png" in stderr.getvalue()
    assert "Failing because warnings were emitted." in stderr.getvalue()
