from __future__ import annotations

import argparse
import os
import shutil
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Sequence, TextIO

from md_for_human.builder import build_site
from md_for_human.discovery import DiscoveryError


class CliError(ValueError):
    """Raised when CLI inputs are invalid before build execution starts."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md-for-human",
        description=(
            "Turn agent-generated Markdown files into a human-friendly, navigable HTML reading site."
        ),
    )
    parser.add_argument("input_path", help="Markdown directory or single Markdown file to humanize")
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

    try:
        input_path = validate_input_path(Path(args.input_path))
        output_dir, custom_output = determine_output_dir(input_path, args.output)
        prepare_output_dir(input_path, output_dir, custom_output=custom_output, overwrite=args.overwrite)
        result = build_site(input_path, output_dir)
    except (CliError, DiscoveryError, OSError) as exc:
        print(f"Error: {exc}", file=stderr)
        return 1

    print(f"Built site at {result.entry_page}", file=stdout)
    for warning in result.warnings:
        print(f"Warning: {warning}", file=stderr)

    if not args.no_open:
        opener(result.entry_page.resolve().as_uri())

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
    try:
        comparison_output_dir = normalize_for_containment_check(output_dir)
    except RuntimeError as exc:
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

    if not output_dir.exists() and not output_dir.is_symlink():
        return

    if custom_output and not overwrite:
        raise CliError(
            f"Custom output directory already exists: {output_dir}. Use --overwrite to replace it."
        )

    remove_existing_path(output_dir)


def normalize_for_containment_check(path: Path) -> Path:
    return path.parent.resolve(strict=False) / path.name


def remove_existing_path(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
