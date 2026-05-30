from __future__ import annotations

from hashlib import sha256
from typing import Any

from md_for_human.review import SCHEMA_VERSION


META_FIELDS = {
    "quote",
}


def annotation_meta(annotation: dict[str, Any]) -> dict[str, Any]:
    meta = annotation.get("meta")
    return meta if isinstance(meta, dict) else {}


def annotation_quote(annotation: dict[str, Any]) -> str:
    value = annotation_meta(annotation).get("quote", annotation.get("quote"))
    return value if isinstance(value, str) else ""


def normalize_annotation_shape(
    annotation: dict[str, Any],
    *,
    source_sha256: str = "",
    annotation_id: str = "",
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in ("id", "source_path", "source_range", "comment", "source_sha256"):
        if field in annotation:
            normalized[field] = annotation[field]
    if annotation_id and "id" not in normalized:
        normalized["id"] = annotation_id
    if source_sha256 and "source_sha256" not in normalized:
        normalized["source_sha256"] = source_sha256

    existing_meta = annotation_meta(annotation)
    meta = {field: existing_meta[field] for field in META_FIELDS if field in existing_meta}
    for field in META_FIELDS:
        if field in annotation and field not in meta:
            meta[field] = annotation[field]
    if meta:
        normalized["meta"] = meta
    return normalized


def normalize_artifact_shape(
    artifact: dict[str, Any],
    documents: dict[str, Any],
) -> dict[str, Any]:
    schema_version = artifact.get("schema_version")
    if schema_version is not None and schema_version != SCHEMA_VERSION:
        return artifact
    annotations = artifact.get("annotations")
    if not isinstance(annotations, list):
        return artifact

    normalized_annotations: list[Any] = []
    seen_ids: set[str] = set()
    changed = False
    for annotation in annotations:
        if not isinstance(annotation, dict):
            normalized_annotations.append(annotation)
            continue
        document = document_for_source_path(documents, annotation.get("source_path"))
        annotation_id = generated_annotation_id(annotation, seen_ids)
        normalized = normalize_annotation_shape(
            annotation,
            source_sha256=document.source_sha256 if document is not None else "",
            annotation_id=annotation_id,
        )
        if isinstance(normalized.get("id"), str):
            seen_ids.add(normalized["id"])
        if normalized != annotation:
            changed = True
        normalized_annotations.append(normalized)

    needs_header = (
        artifact.get("schema_version") != SCHEMA_VERSION
        or artifact.get("source_manifest") != ".md-for-human/manifest.json"
    )
    if not changed and not needs_header:
        return artifact
    normalized_artifact = dict(artifact)
    normalized_artifact["schema_version"] = SCHEMA_VERSION
    normalized_artifact["source_manifest"] = ".md-for-human/manifest.json"
    normalized_artifact["annotations"] = normalized_annotations
    return normalized_artifact


def generated_annotation_id(annotation: dict[str, Any], seen_ids: set[str]) -> str:
    existing_id = annotation.get("id")
    if isinstance(existing_id, str) and existing_id:
        return existing_id
    payload = "|".join(
        [
            string_value(annotation.get("source_path")),
            source_range_fingerprint(annotation.get("source_range")),
            string_value(annotation.get("comment")),
        ]
    )
    base = "ann_" + sha256(payload.encode("utf-8")).hexdigest()[:12]
    candidate = base
    suffix = 2
    while candidate in seen_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def source_range_fingerprint(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return f"{value.get('start_line')}:{value.get('end_line')}"


def string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def document_for_source_path(documents: dict[str, Any], source_path: object) -> Any | None:
    if not isinstance(source_path, str):
        return None
    for document in documents.values():
        if document.source_path == source_path:
            return document
    return None
