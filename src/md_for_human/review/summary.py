from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from md_for_human.review.annotations import annotation_quote
from md_for_human.review.artifacts import annotations_path, summary_path, write_text_atomic

HEADER = "<!-- Generated from .md-for-human/review/annotations.json. Do not edit manually. -->"


def write_review_summary(output_dir: Path, artifact: dict[str, Any]) -> Path:
    path = summary_path(output_dir)
    write_text_atomic(path, render_review_summary(artifact))
    return path


def render_review_summary(artifact: dict[str, Any]) -> str:
    annotations = artifact.get("annotations")
    if not isinstance(annotations, list):
        annotations = []

    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        label = source_location_label(annotation)
        grouped.setdefault(label, []).append(annotation)

    lines = [
        HEADER,
        "",
        "# Review Summary",
        "",
        f"- Schema: {string_value(artifact.get('schema_version'))}",
        f"- Annotation count: {len(annotations)}",
        f"- Files touched: {len({string_value(item.get('source_path')) for item in annotations if isinstance(item, dict)})}",
        "",
    ]

    for label, page_annotations in grouped.items():
        lines.extend([f"## {label}", ""])
        for annotation in page_annotations:
            lines.extend(render_annotation_v2(annotation))

    return "\n".join(lines).rstrip() + "\n"


def render_annotation_v2(annotation: dict[str, Any]) -> list[str]:
    annotation_id = string_value(annotation.get("id"), fallback="unknown")
    quote = annotation_quote(annotation)
    lines = [f"### {annotation_id}", ""]

    if quote:
        lines.extend([blockquote(quote), ""])
    if is_global_comment(annotation):
        lines.extend(["Global comment", ""])

    lines.extend([string_value(annotation.get("comment")), ""])
    return lines


def source_location_label(annotation: dict[str, Any]) -> str:
    source_path = string_value(annotation.get("source_path"))
    base = source_path or "unknown"
    line_label = source_line_label(annotation.get("source_range"))
    if line_label:
        return f"{base}:{line_label}"
    return base


def source_line_label(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    start_line = value.get("start_line")
    end_line = value.get("end_line")
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return ""
    if start_line == 0 and end_line == 0:
        return "L0"
    if start_line <= 0 or end_line < start_line:
        return ""
    if start_line == end_line:
        return f"L{start_line}"
    return f"L{start_line}-L{end_line}"


def is_global_comment(annotation: dict[str, Any]) -> bool:
    source_range = annotation.get("source_range")
    return (
        isinstance(source_range, dict)
        and source_range.get("start_line") == 0
        and source_range.get("end_line") == 0
    )


def blockquote(text: str) -> str:
    if not text:
        return ">"
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def string_value(value: object, fallback: str = "") -> str:
    if isinstance(value, str):
        return value
    return fallback


def source_annotations_path(output_dir: Path) -> Path:
    return annotations_path(output_dir)
