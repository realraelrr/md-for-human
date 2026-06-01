from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from md_for_human.review import SCHEMA_VERSION
from md_for_human.review.annotations import normalize_artifact_shape
from md_for_human.review.archive import append_archived_annotations, split_inactive_annotations
from md_for_human.review.artifacts import (
    annotations_path,
    empty_artifact,
    write_json_atomic,
)
from md_for_human.review.summary import write_review_summary
from md_for_human.review.validate import (
    ManifestDocument,
    ReviewValidationResult,
    load_json_file,
    parse_manifest_documents,
    validate_review_artifact,
)


class ReviewArtifactStoreError(RuntimeError):
    def __init__(self, message: str, *, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or [message]


@dataclass(slots=True)
class ReviewArtifactSaveResult:
    artifact: dict[str, Any]
    validation: ReviewValidationResult
    summary_path: Path | None


@dataclass(slots=True)
class ReviewArtifactStore:
    output_dir: Path
    manifest_path: Path

    def ensure_artifact(self) -> dict[str, Any]:
        path = annotations_path(self.output_dir)
        if not path.exists():
            artifact = empty_artifact()
            write_json_atomic(path, artifact)
            return artifact

        errors: list[str] = []
        loaded_artifact = load_json_file(path, errors)
        if not isinstance(loaded_artifact, dict):
            raise ReviewArtifactStoreError("annotations.json is invalid", errors=errors)

        documents = self.optional_manifest_documents()
        normalized_artifact = self.normalize_artifact(loaded_artifact, documents=documents)
        active_artifact, archived_annotations = self.split_inactive_annotations(
            normalized_artifact,
            documents=documents,
        )
        if active_artifact != loaded_artifact or archived_annotations:
            append_archived_annotations(self.output_dir, archived_annotations)
            write_json_atomic(annotations_path(self.output_dir), active_artifact)
            self.write_review_summary_if_valid(active_artifact, documents=documents)
        return active_artifact

    def save_browser_artifact(self, artifact: dict[str, Any]) -> ReviewArtifactSaveResult:
        documents = self.manifest_documents()
        normalized_artifact = self.normalize_artifact(artifact, documents=documents)
        writable_artifact, archived_annotations = split_inactive_annotations(
            normalized_artifact,
            documents,
        )
        validation = validate_review_artifact(
            self.output_dir,
            writable_artifact,
            documents=documents,
            write_summary=False,
        )
        if validation.errors:
            return ReviewArtifactSaveResult(writable_artifact, validation, None)

        append_archived_annotations(self.output_dir, archived_annotations)
        write_json_atomic(annotations_path(self.output_dir), writable_artifact)
        summary_path = write_review_summary(self.output_dir, writable_artifact)
        return ReviewArtifactSaveResult(writable_artifact, validation, summary_path)

    def normalize_artifact(
        self,
        artifact: dict[str, Any],
        *,
        documents: dict[str, ManifestDocument] | None = None,
    ) -> dict[str, Any]:
        schema_version = artifact.get("schema_version")
        if schema_version is not None and schema_version != SCHEMA_VERSION:
            return artifact
        annotations = artifact.get("annotations")
        if not isinstance(annotations, list):
            return artifact

        manifest_documents = documents if documents is not None else self.optional_manifest_documents()
        if manifest_documents is None:
            return artifact

        return normalize_artifact_shape(artifact, manifest_documents)

    def split_inactive_annotations(
        self,
        artifact: dict[str, Any],
        *,
        documents: dict[str, ManifestDocument] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if artifact.get("schema_version") != SCHEMA_VERSION:
            return artifact, []
        annotations = artifact.get("annotations")
        if not isinstance(annotations, list):
            return artifact, []

        manifest_documents = documents if documents is not None else self.optional_manifest_documents()
        if manifest_documents is None:
            return artifact, []

        return split_inactive_annotations(artifact, manifest_documents)

    def write_review_summary_if_valid(
        self,
        artifact: dict[str, Any],
        *,
        documents: dict[str, ManifestDocument] | None = None,
    ) -> None:
        validation = validate_review_artifact(
            self.output_dir,
            artifact,
            documents=documents,
            write_summary=False,
        )
        if validation.errors:
            return
        write_review_summary(self.output_dir, artifact)

    def manifest_documents(self) -> dict[str, ManifestDocument]:
        manifest_errors: list[str] = []
        manifest = load_json_file(self.manifest_path, manifest_errors)
        documents = parse_manifest_documents(manifest, manifest_errors)
        if manifest_errors:
            raise ReviewArtifactStoreError(
                "manifest.json is invalid",
                errors=manifest_errors,
            )
        return documents

    def optional_manifest_documents(self) -> dict[str, ManifestDocument] | None:
        manifest_errors: list[str] = []
        manifest = load_json_file(self.manifest_path, manifest_errors)
        documents = parse_manifest_documents(manifest, manifest_errors)
        if manifest_errors:
            return None
        return documents
