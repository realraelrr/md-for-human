from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

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
        page = string_value(annotation.get("page"), fallback="unknown")
        grouped.setdefault(page, []).append(annotation)

    created_by = artifact.get("created_by")
    created_by_kind = ""
    created_by_name = ""
    if isinstance(created_by, dict):
        created_by_kind = string_value(created_by.get("kind"))
        created_by_name = string_value(created_by.get("name"))

    lines = [
        HEADER,
        "",
        "# Review Summary",
        "",
        f"- Schema: {string_value(artifact.get('schema_version'))}",
        f"- Created by: {created_by_kind} / {created_by_name}",
        f"- Annotation count: {len(annotations)}",
        f"- Pages touched: {len(grouped)}",
        "",
    ]

    for page, page_annotations in grouped.items():
        lines.extend([f"## {page}", ""])
        source_path = first_source_path(page_annotations)
        if source_path:
            lines.extend([f"Source: `{source_path}`", ""])
        for annotation in page_annotations:
            lines.extend(render_annotation(annotation))

    return "\n".join(lines).rstrip() + "\n"


def render_annotation(annotation: dict[str, Any]) -> list[str]:
    annotation_id = string_value(annotation.get("id"), fallback="unknown")
    annotation_type = string_value(annotation.get("type"), fallback="unknown")
    lines = [
        f"### {annotation_id} - {annotation_type}",
        "",
        "Quote:",
        "",
        blockquote(string_value(annotation.get("quote"))),
        "",
        "Note:",
        "",
        string_value(annotation.get("note")),
        "",
    ]

    placement = string_value(annotation.get("placement"))
    if placement:
        lines.extend([f"Placement: {placement}", ""])

    suggested_text = string_value(annotation.get("suggested_text"))
    if suggested_text:
        lines.extend(
            [
                "Suggested text:",
                "",
                "```text",
                suggested_text,
                "```",
                "",
            ]
        )

    return lines


def first_source_path(annotations: list[dict[str, Any]]) -> str:
    for annotation in annotations:
        source_path = string_value(annotation.get("source_path"))
        if source_path:
            return source_path
    return ""


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
