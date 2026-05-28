from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any

from md_for_human.review import SCHEMA_VERSION
from md_for_human.review.artifacts import annotations_path
from md_for_human.review.summary import write_review_summary

ALLOWED_TYPES = {"comment", "suggest_delete", "suggest_insert", "suggest_replace"}
COMMON_REQUIRED_FIELDS = (
    "id",
    "type",
    "page",
    "source_path",
    "quote",
    "note",
    "created_at",
    "updated_at",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(slots=True)
class ReviewValidationResult:
    errors: list[str]
    warnings: list[str]
    annotation_count: int
    pages_touched: int
    summary_path: Path | None

    @property
    def passed(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class ManifestDocument:
    page: str
    source_path: str
    source_sha256: str


@dataclass(slots=True)
class PageContent:
    text: str
    page: str | None
    source_path: str | None


def validate_review(output_dir: Path) -> ReviewValidationResult:
    output_dir = Path(output_dir)
    errors: list[str] = []
    warnings: list[str] = []
    manifest = load_json_file(output_dir / ".md-for-human" / "manifest.json", errors)
    documents = parse_manifest_documents(manifest, errors)

    artifact_path = annotations_path(output_dir)
    artifact = load_json_file(artifact_path, errors)
    if artifact is None:
        return ReviewValidationResult(errors, warnings, 0, 0, None)

    return validate_review_artifact(
        output_dir,
        artifact,
        documents=documents,
        errors=errors,
        warnings=warnings,
        write_summary=True,
    )


def validate_review_artifact(
    output_dir: Path,
    artifact: Any,
    *,
    documents: dict[str, ManifestDocument] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    write_summary: bool = False,
) -> ReviewValidationResult:
    output_dir = Path(output_dir)
    errors = [] if errors is None else errors
    warnings = [] if warnings is None else warnings
    if documents is None:
        manifest = load_json_file(output_dir / ".md-for-human" / "manifest.json", errors)
        documents = parse_manifest_documents(manifest, errors)

    annotation_count = 0
    pages_touched: set[str] = set()
    if isinstance(artifact, dict):
        pages_touched = validate_artifact(output_dir, artifact, documents, errors, warnings)
        annotations = artifact.get("annotations")
        if isinstance(annotations, list):
            annotation_count = len(annotations)
    else:
        errors.append("annotations.json: top-level object is not an object")

    written_summary_path: Path | None = None
    if write_summary and isinstance(artifact, dict) and isinstance(artifact.get("annotations"), list):
        written_summary_path = write_review_summary(output_dir, artifact)

    return ReviewValidationResult(
        errors=errors,
        warnings=warnings,
        annotation_count=annotation_count,
        pages_touched=len(pages_touched),
        summary_path=written_summary_path,
    )


def load_json_file(path: Path, errors: list[str]) -> Any | None:
    if not path.exists():
        errors.append(f"{path.name}: file is missing")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name}: invalid JSON: {exc.msg}")
        return None
    except OSError as exc:
        errors.append(f"{path.name}: could not be read: {exc}")
        return None


def parse_manifest_documents(
    manifest: Any,
    errors: list[str],
) -> dict[str, ManifestDocument]:
    documents_by_page: dict[str, ManifestDocument] = {}
    if not isinstance(manifest, dict):
        if manifest is not None:
            errors.append("manifest.json: top-level object is not an object")
        return documents_by_page

    documents = manifest.get("documents")
    if not isinstance(documents, list):
        errors.append("manifest.json: documents missing or not an array")
        return documents_by_page

    for index, item in enumerate(documents):
        label = f"manifest documents[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: entry is not an object")
            continue
        page = item.get("page")
        source_path = item.get("source_path")
        source_sha256 = item.get("source_sha256")
        if not isinstance(page, str) or not page:
            errors.append(f"{label}: page missing or invalid")
            continue
        if not is_safe_relative_posix_path(page):
            errors.append(f'{label}: page "{page}" is unsafe')
            continue
        if not isinstance(source_path, str) or not source_path:
            errors.append(f"{label}: source_path missing or invalid")
            continue
        if not is_safe_relative_posix_path(source_path):
            errors.append(f'{label}: source_path "{source_path}" is unsafe')
            continue
        if not isinstance(source_sha256, str) or not SHA256_RE.fullmatch(source_sha256):
            errors.append(f'{label}: source_sha256 for page "{page}" is not a valid sha256')
            continue
        documents_by_page[page] = ManifestDocument(page, source_path, source_sha256)

    return documents_by_page


def validate_artifact(
    output_dir: Path,
    artifact: dict[str, Any],
    documents: dict[str, ManifestDocument],
    errors: list[str],
    warnings: list[str],
) -> set[str]:
    if artifact.get("schema_version") != SCHEMA_VERSION:
        errors.append("annotations.json: schema_version missing or unsupported")
    validate_created_by(artifact.get("created_by"), errors)
    source_manifest = artifact.get("source_manifest")
    if source_manifest != ".md-for-human/manifest.json":
        errors.append("annotations.json: source_manifest must be .md-for-human/manifest.json")

    annotations = artifact.get("annotations")
    if not isinstance(annotations, list):
        errors.append("annotations.json: annotations missing or not an array")
        return set()

    pages_touched: set[str] = set()
    seen_ids: set[str] = set()
    page_text_cache: dict[str, PageContent | None] = {}
    for index, raw_annotation in enumerate(annotations):
        label = f"annotation[{index}]"
        if not isinstance(raw_annotation, dict):
            errors.append(f"{label}: annotation is not an object")
            continue
        annotation_id = validate_annotation_id(raw_annotation, label, seen_ids, errors)
        validate_annotation_fields(raw_annotation, annotation_id, errors)
        page = string_field(raw_annotation, "page")
        source_path = string_field(raw_annotation, "source_path")
        if page:
            document = documents.get(page)
            if document is None:
                errors.append(f'{annotation_id}: page "{page}" is not listed in manifest documents')
            else:
                pages_touched.add(page)
                if source_path and source_path != document.source_path:
                    errors.append(
                        f'{annotation_id}: source_path "{source_path}" does not match '
                        f'manifest documents for page "{page}"'
                    )
                validate_quote(
                    output_dir,
                    page,
                    source_path,
                    raw_annotation,
                    annotation_id,
                    page_text_cache,
                    errors,
                    warnings,
                )
    return pages_touched


def validate_created_by(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("annotations.json: created_by missing or invalid")
        return
    kind = value.get("kind")
    name = value.get("name")
    if kind not in {"human", "agent"}:
        errors.append("annotations.json: created_by.kind must be human or agent")
    if not isinstance(name, str) or not name:
        errors.append("annotations.json: created_by.name must be a non-empty string")


def validate_annotation_id(
    annotation: dict[str, Any],
    label: str,
    seen_ids: set[str],
    errors: list[str],
) -> str:
    annotation_id = annotation.get("id")
    if not isinstance(annotation_id, str) or not annotation_id:
        errors.append(f"{label}: required field id must be a non-empty string")
        return label
    if annotation_id in seen_ids:
        errors.append(f'{annotation_id}: duplicate annotation id "{annotation_id}"')
    seen_ids.add(annotation_id)
    return annotation_id


def validate_annotation_fields(
    annotation: dict[str, Any],
    annotation_id: str,
    errors: list[str],
) -> None:
    for field in COMMON_REQUIRED_FIELDS:
        if not non_empty_string(annotation.get(field)):
            errors.append(f"{annotation_id}: required field {field} must be a non-empty string")

    annotation_type = annotation.get("type")
    if isinstance(annotation_type, str) and annotation_type not in ALLOWED_TYPES:
        errors.append(f'{annotation_id}: unknown annotation type "{annotation_type}"')

    if annotation_type == "suggest_insert":
        placement = annotation.get("placement")
        if placement not in {"before", "after"}:
            errors.append(f"{annotation_id}: placement must be before or after")
        if not non_empty_string(annotation.get("suggested_text")):
            errors.append(
                f"{annotation_id}: required field suggested_text must be a non-empty string"
            )
    elif annotation_type == "suggest_replace" and not non_empty_string(
        annotation.get("suggested_text")
    ):
        errors.append(f"{annotation_id}: required field suggested_text must be a non-empty string")


def validate_quote(
    output_dir: Path,
    page: str,
    source_path: str,
    annotation: dict[str, Any],
    annotation_id: str,
    page_text_cache: dict[str, PageContent | None],
    errors: list[str],
    warnings: list[str],
) -> None:
    quote = string_field(annotation, "quote")
    if not quote:
        return
    if page not in page_text_cache:
        page_text_cache[page] = extract_page_content_text(output_dir / page)
    page_content = page_text_cache[page]
    if page_content is None:
        errors.append(f"{annotation_id}: page content marker not found in {page}")
        return
    if page_content.page != page:
        errors.append(
            f'{annotation_id}: HTML metadata page "{page_content.page or ""}" does not match "{page}"'
        )
    if page_content.source_path != source_path:
        errors.append(
            f'{annotation_id}: HTML metadata source_path "{page_content.source_path or ""}" '
            f'does not match "{source_path}"'
        )

    normalized_page_text = normalize_whitespace(page_content.text)
    normalized_quote = normalize_whitespace(quote)
    match_count = count_occurrences(normalized_page_text, normalized_quote)
    if match_count == 0:
        warnings.append(f"{annotation_id}: quote not found in {page}")
    elif match_count > 1:
        warnings.append(f"{annotation_id}: quote found multiple times in {page}")
    validate_context(annotation, normalized_page_text, normalized_quote, annotation_id, warnings)


def validate_context(
    annotation: dict[str, Any],
    normalized_page_text: str,
    normalized_quote: str,
    annotation_id: str,
    warnings: list[str],
) -> None:
    context_before = normalize_whitespace(string_field(annotation, "context_before"))
    context_after = normalize_whitespace(string_field(annotation, "context_after"))
    if context_before:
        before_anchor = normalize_whitespace(f"{context_before} {normalized_quote}")
        if before_anchor not in normalized_page_text:
            warnings.append(f"{annotation_id}: context_before does not match nearby rendered text")
    if context_after:
        after_anchor = normalize_whitespace(f"{normalized_quote} {context_after}")
        if after_anchor not in normalized_page_text:
            warnings.append(f"{annotation_id}: context_after does not match nearby rendered text")


def extract_page_content_text(path: Path) -> PageContent | None:
    if not path.exists():
        return None
    parser = ContentTextParser()
    parser.feed(path.read_text(encoding="utf-8"))
    if not parser.found_content:
        return None
    return PageContent(
        text=" ".join(parser.text_parts),
        page=parser.page,
        source_path=parser.source_path,
    )


class ContentTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found_content = False
        self._in_content = False
        self._depth = 0
        self._skip_depth = 0
        self.text_parts: list[str] = []
        self.page: str | None = None
        self.source_path: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "body":
            self.page = attr_map.get("data-mdfh-page")
            self.source_path = attr_map.get("data-mdfh-source-path")
        if self._in_content:
            self._depth += 1
            if tag in {"script", "style"}:
                self._skip_depth += 1
            return
        if attr_map.get("data-mdfh-content") == "1":
            self.found_content = True
            self._in_content = True
            self._depth = 1

    def handle_endtag(self, tag: str) -> None:
        if not self._in_content:
            return
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1
        self._depth -= 1
        if self._depth <= 0:
            self._in_content = False

    def handle_data(self, data: str) -> None:
        if self._in_content and self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def count_occurrences(haystack: str, needle: str) -> int:
    if not needle:
        return 0
    count = 0
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index == -1:
            return count
        count += 1
        start = index + len(needle)


def is_safe_relative_posix_path(value: str) -> bool:
    path = PurePosixPath(value)
    if path.is_absolute() or value == "":
        return False
    return ".." not in path.parts


def string_field(mapping: dict[str, Any], field: str) -> str:
    value = mapping.get(field)
    if isinstance(value, str):
        return value
    return ""


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)
