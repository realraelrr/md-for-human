from __future__ import annotations

import argparse
import os
import shutil
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Sequence, TextIO
from urllib.parse import urlsplit

from md_for_human.builder import BuildResult, build_site, build_site_preserving_review
from md_for_human.discovery import DiscoveryError
from md_for_human.html_targets import extract_local_targets
from md_for_human.review.server import ReviewServerError, serve_review
from md_for_human.review.validate import ReviewValidationResult, validate_review
from md_for_human.urls import decode_url_path

BUILD_REVIEW_SENTINEL = "__mdfh_build_review__"


class CliError(ValueError):
    """Raised when CLI inputs are invalid before build execution starts."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-for-human",
        description=(
            "Turn agent-generated Markdown files into a human-friendly, navigable HTML reading site."
        ),
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        help="Markdown directory or single Markdown file to humanize",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory for the generated site",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Generate the site without opening it in a browser",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete an existing custom output directory before rebuilding",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run structural checks on the generated site after building",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return a non-zero status if the build emits warnings",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Run strict agent handoff checks: --verify --fail-on-warning --no-open",
    )
    parser.add_argument(
        "--validate-review",
        metavar="OUTPUT_DIR",
        help="Validate review annotations for an existing generated site output directory",
    )
    parser.add_argument(
        "--review",
        nargs="?",
        const=BUILD_REVIEW_SENTINEL,
        metavar="OUTPUT_DIR",
        help=(
            "Start a local browser review UI. With INPUT_PATH, build to --output first "
            "and enable source hot reload; without INPUT_PATH, review an existing output directory."
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    opener: Callable[[str], object] = webbrowser.open,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.validate_review:
        return validate_review_output(
            Path(args.validate_review),
            fail_on_warning=args.fail_on_warning or args.strict,
            stdout=stdout,
            stderr=stderr,
        )

    if args.review and args.input_path is None:
        if args.review == BUILD_REVIEW_SENTINEL:
            print("Error: --review needs INPUT_PATH or OUTPUT_DIR.", file=stderr)
            return 1
        return serve_review_output(
            Path(args.review),
            opener=opener,
            stdout=stdout,
            stderr=stderr,
        )

    if args.input_path is None:
        print(
            "Error: input_path is required unless --validate-review or --review is used.",
            file=stderr,
        )
        return 1

    if args.review:
        review_output_arg = args.output
        if args.review != BUILD_REVIEW_SENTINEL:
            review_output_arg = args.review
        return build_and_serve_review_output(
            Path(args.input_path),
            output_arg=review_output_arg,
            overwrite=args.overwrite,
            opener=opener,
            stdout=stdout,
            stderr=stderr,
        )

    try:
        input_path = validate_input_path(Path(args.input_path))
        output_dir, custom_output = determine_output_dir(input_path, args.output)
        prepare_output_dir(input_path, output_dir, custom_output=custom_output, overwrite=args.overwrite)
        result = build_site(input_path, output_dir)
    except (CliError, DiscoveryError, OSError) as exc:
        print(f"Error: {exc}", file=stderr)
        return 1

    verification_errors: list[str] = []
    should_verify = args.verify or args.strict
    fail_on_warning = args.fail_on_warning or args.strict
    no_open = args.no_open or args.strict

    if should_verify:
        verification_errors = verify_build_result(result)

    should_fail_on_warning = fail_on_warning and bool(result.warnings)
    browser_opened = False
    if not no_open and not should_fail_on_warning and not verification_errors:
        open_result = opener(result.entry_page.resolve().as_uri())
        browser_opened = open_result is not False

    print_build_summary(result, browser_opened, stdout)
    for warning in result.warnings:
        print(f"Warning: {warning}", file=stderr)

    if should_verify:
        if verification_errors:
            print("Verification: failed", file=stdout)
            for error in verification_errors:
                print(f"Verification error: {error}", file=stderr)
        else:
            print("Verification: passed", file=stdout)

    if should_fail_on_warning:
        print("Failing because warnings were emitted.", file=stderr)
        return 1

    if verification_errors:
        return 1

    return 0


def validate_input_path(input_path: Path) -> Path:
    resolved = input_path.resolve()
    if not resolved.exists():
        raise CliError(f"Input path does not exist: {input_path}")
    if resolved.is_file() and resolved.suffix.lower() != ".md":
        raise CliError(f"Input file is not Markdown: {input_path}")
    if not resolved.is_dir() and not resolved.is_file():
        raise CliError(f"Input path is neither a directory nor a file: {input_path}")
    return resolved


def validate_review_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    manifest_path = resolved / ".md-for-human" / "manifest.json"
    if not resolved.exists() or not resolved.is_dir():
        raise CliError(f"Review output directory does not exist: {output_dir}")
    if not manifest_path.exists():
        raise CliError(f"Review output directory is missing manifest.json: {manifest_path}")
    return resolved


def determine_output_dir(input_path: Path, output_arg: str | None) -> tuple[Path, bool]:
    if output_arg:
        output_path = os.path.abspath(os.path.expanduser(output_arg))
        return Path(output_path), True
    default_name = input_path.stem if input_path.is_file() else input_path.name
    return input_path.parent / f"{default_name}-site", False


def prepare_output_dir(
    input_path: Path,
    output_dir: Path,
    *,
    custom_output: bool,
    overwrite: bool,
) -> None:
    validate_output_location(input_path, output_dir)

    if not output_dir.exists() and not output_dir.is_symlink():
        return

    if custom_output and not overwrite:
        raise CliError(
            f"Custom output directory already exists: {output_dir}. Use --overwrite to replace it."
        )

    remove_existing_path(output_dir)


def validate_output_location(input_path: Path, output_dir: Path) -> None:
    try:
        comparison_output_dir = normalize_for_containment_check(output_dir)
    except (RuntimeError, OSError) as exc:
        raise CliError(f"Could not resolve output directory: {output_dir}") from exc
    if input_path.is_dir():
        if comparison_output_dir == input_path:
            raise CliError("Output directory must not be the same as the input directory.")
        if input_path in comparison_output_dir.parents:
            raise CliError("Output directory must not be inside the input directory.")
        if comparison_output_dir in input_path.parents:
            raise CliError("Output directory must not be an ancestor of the input directory.")
    elif comparison_output_dir == input_path:
        raise CliError("Output directory must not be the same as the input Markdown file.")
    elif comparison_output_dir in input_path.parents:
        raise CliError("Output directory must not be an ancestor of the input Markdown file.")


def normalize_for_containment_check(path: Path) -> Path:
    if path.parent.is_symlink():
        path.parent.resolve(strict=True)
    return path.parent.resolve(strict=False) / path.name


def remove_existing_path(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def print_build_summary(result: BuildResult, browser_opened: bool, stdout: TextIO) -> None:
    print(f"Built site at: {result.entry_page}", file=stdout)
    print(f"Output directory: {result.output_dir}", file=stdout)
    print(f"Pages: {len(result.pages)}", file=stdout)
    print(f"Assets copied: {len(result.copied_assets)}", file=stdout)
    print(f"Warnings: {len(result.warnings)}", file=stdout)
    print(f"Browser opened: {'yes' if browser_opened else 'no'}", file=stdout)


def serve_review_output(
    output_dir: Path,
    *,
    opener: Callable[[str], object],
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        resolved_output_dir = validate_review_output_dir(output_dir)
        return serve_review(resolved_output_dir, opener=opener, stdout=stdout)
    except (CliError, ReviewServerError, OSError) as exc:
        print(f"Error: {exc}", file=stderr)
    return 1


def build_and_serve_review_output(
    input_path: Path,
    *,
    output_arg: str | None,
    overwrite: bool,
    opener: Callable[[str], object],
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        resolved_input = validate_input_path(input_path)
        output_dir, custom_output = determine_output_dir(resolved_input, output_arg)
        validate_output_location(resolved_input, output_dir)
        if custom_output and (output_dir.exists() or output_dir.is_symlink()) and not overwrite:
            raise CliError(
                f"Custom output directory already exists: {output_dir}. "
                "Use --overwrite to replace it."
            )
        build_site_preserving_review(resolved_input, output_dir)
        resolved_output_dir = validate_review_output_dir(output_dir)
        return serve_review(
            resolved_output_dir,
            source_input=resolved_input,
            opener=opener,
            stdout=stdout,
        )
    except (CliError, DiscoveryError, OSError, ReviewServerError) as exc:
        print(f"Error: {exc}", file=stderr)
    return 1


def validate_review_output(
    output_dir: Path,
    *,
    fail_on_warning: bool,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    result = validate_review(output_dir)
    should_fail = bool(result.errors) or (fail_on_warning and bool(result.warnings))

    print(f"Review validation: {'failed' if should_fail else 'passed'}", file=stdout)
    print(f"Annotations: {result.annotation_count}", file=stdout)
    print(f"Pages touched: {result.pages_touched}", file=stdout)
    print(f"Warnings: {len(result.warnings)}", file=stdout)
    if result.summary_path is not None:
        print(f"Review summary: {result.summary_path}", file=stdout)

    print_review_diagnostics(result, stderr)
    if fail_on_warning and result.warnings:
        print("Failing because review warnings were emitted.", file=stderr)

    return 1 if should_fail else 0


def print_review_diagnostics(result: ReviewValidationResult, stderr: TextIO) -> None:
    for warning in result.warnings:
        print(f"Review warning: {warning}", file=stderr)
    for error in result.errors:
        print(f"Review error: {error}", file=stderr)


def verify_build_result(result: BuildResult) -> list[str]:
    errors: list[str] = []
    entry_relative = result.entry_page.relative_to(result.output_dir).as_posix()
    if not result.entry_page.exists():
        errors.append(f"Entry page does not exist: {entry_relative}")
        return errors

    entry_html = result.entry_page.read_text(encoding="utf-8")
    if not entry_html.lstrip().startswith("<!DOCTYPE html>"):
        errors.append(f"Entry page is not an HTML document: {entry_relative}")
    if 'aria-label="Site navigation"' not in entry_html:
        errors.append(f"Entry page is missing site navigation: {entry_relative}")

    for page in result.pages:
        page_path = result.output_dir / page
        if not page_path.exists():
            errors.append(f"Expected page missing: {page}")
            continue
        html = page_path.read_text(encoding="utf-8")
        for target in extract_local_targets(html):
            if target.startswith("#"):
                continue
            parsed_target = urlsplit(target)
            if not parsed_target.path:
                continue
            target_without_fragment = decode_url_path(parsed_target.path)
            if target_without_fragment.lower().endswith(".md"):
                errors.append(f"Markdown link appears unrevised in page: {page}")
            target_path = (page_path.parent / target_without_fragment).resolve()
            if result.output_dir.resolve() not in target_path.parents and target_path != result.output_dir.resolve():
                continue
            if not target_path.exists():
                errors.append(f"Local target missing from {page}: {target}")

    for asset in result.copied_assets:
        if not (result.output_dir / asset).exists():
            errors.append(f"Copied asset missing: {asset}")

    if not result.manifest_path.exists():
        errors.append(".md-for-human/manifest.json is missing")

    return errors
