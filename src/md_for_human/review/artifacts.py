from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from md_for_human.review import SCHEMA_VERSION

REVIEW_DIR = Path(".md-for-human") / "review"
ANNOTATIONS_FILE = "annotations.json"
SUMMARY_FILE = "review.md"


def review_dir(output_dir: Path) -> Path:
    return output_dir / REVIEW_DIR


def annotations_path(output_dir: Path) -> Path:
    return review_dir(output_dir) / ANNOTATIONS_FILE


def summary_path(output_dir: Path) -> Path:
    return review_dir(output_dir) / SUMMARY_FILE


def empty_artifact() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_manifest": ".md-for-human/manifest.json",
        "annotations": [],
    }


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp_path, path)


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, path)
