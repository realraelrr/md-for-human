from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from md_for_human.review.validate import (
    count_occurrences,
    extract_page_content_text,
    normalize_anchor_text,
    normalize_whitespace,
    string_field,
)


def add_locator_metadata(output_dir: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    writable_artifact = deepcopy(artifact)
    annotations = writable_artifact.get("annotations")
    if not isinstance(annotations, list):
        return writable_artifact

    page_text_cache: dict[str, str | None] = {}
    for annotation in annotations:
        if isinstance(annotation, dict):
            apply_locator_metadata(output_dir, annotation, page_text_cache)
    return writable_artifact


def apply_locator_metadata(
    output_dir: Path,
    annotation: dict[str, Any],
    page_text_cache: dict[str, str | None],
) -> None:
    quote = string_field(annotation, "quote")
    if not quote:
        annotation["locator"] = {"status": "document", "strategy": "document"}
        return

    page = string_field(annotation, "page")
    if page not in page_text_cache:
        page_content = extract_page_content_text(output_dir / page) if page else None
        page_text_cache[page] = page_content.text if page_content is not None else None
    page_text = page_text_cache[page]
    if page_text is None:
        annotation["locator"] = {
            "status": "degraded",
            "strategy": "page",
            "reason": "page_text_unavailable",
        }
        return

    exact_page_text = normalize_whitespace(page_text)
    exact_quote = normalize_whitespace(quote)
    exact_count = count_occurrences(exact_page_text, exact_quote)
    canonical_page_text = normalize_anchor_text(page_text)
    canonical_quote = normalize_anchor_text(quote)
    canonical_count = count_occurrences(canonical_page_text, canonical_quote)

    if exact_count == 1:
        update_resolved_locator(annotation, exact_page_text, exact_quote, "exact_quote")
    elif canonical_count == 1:
        update_resolved_locator(
            annotation,
            canonical_page_text,
            canonical_quote,
            "canonical_quote",
        )
    else:
        annotation["locator"] = {
            "status": "degraded",
            "strategy": "page",
            "reason": "quote_repeated" if canonical_count > 1 else "quote_not_found",
            "canonical_quote": canonical_quote,
        }


def update_resolved_locator(
    annotation: dict[str, Any],
    page_text: str,
    quote: str,
    strategy: str,
) -> None:
    start = page_text.find(quote)
    annotation["locator"] = {
        "status": "resolved",
        "strategy": strategy,
        "canonical_quote": quote,
        "occurrence": 0,
        "text_offset": start,
    }
    context_before, context_after = locator_context(page_text, start, len(quote))
    if context_before:
        annotation.setdefault("context_before", context_before)
    if context_after:
        annotation.setdefault("context_after", context_after)


def locator_context(page_text: str, start: int, quote_length: int) -> tuple[str, str]:
    window = 80
    if start < 0:
        return "", ""
    before = page_text[max(0, start - window) : start].strip()
    after = page_text[start + quote_length : start + quote_length + window].strip()
    return before, after


