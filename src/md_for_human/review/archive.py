from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from md_for_human.review import SCHEMA_VERSION
from md_for_human.review.annotations import normalize_annotation_shape
from md_for_human.review.artifacts import archive_path, write_json_atomic


def split_inactive_annotations(
    artifact: dict[str, Any],
    documents: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if artifact.get("schema_version") != SCHEMA_VERSION:
        return artifact, []
    annotations = artifact.get("annotations")
    if not isinstance(annotations, list):
        return artifact, []

    active_annotations: list[Any] = []
    archived_annotations: list[dict[str, Any]] = []
    for annotation in annotations:
        if not isinstance(annotation, dict):
            active_annotations.append(annotation)
            continue
        archive_reason = archive_annotation_status(
            annotation,
            documents,
        )
        if archive_reason is None:
            active_annotations.append(annotation)
            continue
        archived_annotations.append(
            archived_annotation(
                annotation,
                archive_reason=archive_reason,
            )
        )

    if not archived_annotations and active_annotations == annotations:
        return artifact, []

    cleaned_artifact = dict(artifact)
    cleaned_artifact["annotations"] = active_annotations
    return cleaned_artifact, archived_annotations


def archive_annotation_status(
    annotation: dict[str, Any],
    documents: dict[str, Any],
) -> str | None:
    source_path = annotation.get("source_path")
    if not isinstance(source_path, str) or not is_safe_relative_posix_path(source_path):
        return None
    documents_by_source_path = {
        document.source_path: document for document in documents.values()
    }
    document = documents_by_source_path.get(source_path)
    if document is None:
        return "source_removed"
    source_sha256 = annotation.get("source_sha256")
    if isinstance(source_sha256, str) and source_sha256 != document.source_sha256:
        return "source_changed"
    return None


def archived_annotation(
    annotation: dict[str, Any],
    *,
    archive_reason: str,
) -> dict[str, Any]:
    archived = normalize_annotation_shape(annotation)
    archived["archive_reason"] = archive_reason
    return archived


def append_archived_annotations(output_dir: Path, archived_annotations: list[dict[str, Any]]) -> None:
    if not archived_annotations:
        return
    path = archive_path(output_dir)
    existing = load_json_file(path) if path.exists() else None
    if isinstance(existing, dict) and isinstance(existing.get("annotations"), list):
        combined = dict(existing)
        combined_annotations = [item for item in existing["annotations"] if isinstance(item, dict)]
    else:
        combined = {
            "schema_version": SCHEMA_VERSION,
            "source_manifest": ".md-for-human/manifest.json",
            "annotations": [],
        }
        combined_annotations = []

    seen_ids = {
        item.get("id") for item in combined_annotations if isinstance(item.get("id"), str)
    }
    for annotation in archived_annotations:
        annotation_id = annotation.get("id")
        if isinstance(annotation_id, str) and annotation_id in seen_ids:
            continue
        combined_annotations.append(annotation)
        if isinstance(annotation_id, str):
            seen_ids.add(annotation_id)
    combined["annotations"] = combined_annotations
    write_json_atomic(path, combined)


def load_json_file(path: Path) -> Any | None:
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def is_safe_relative_posix_path(value: str) -> bool:
    if not value or value.startswith("/"):
        return False
    path = PurePosixPath(value)
    return ".." not in path.parts
