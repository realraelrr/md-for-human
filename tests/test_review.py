from __future__ import annotations

import json
from pathlib import Path

from md_for_human.builder import build_site
from md_for_human.review.validate import validate_review


def _write_review_artifact_v2(output_dir: Path, annotations: list[dict[str, str]]) -> Path:
    review_dir = output_dir / ".md-for-human" / "review"
    review_dir.mkdir(parents=True)
    artifact_path = review_dir / "annotations.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "mdfh-review-v2",
                "source_manifest": ".md-for-human/manifest.json",
                "annotations": annotations,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact_path


def _write_review_artifact(output_dir: Path, annotations: list[dict[str, str]]) -> Path:
    review_dir = output_dir / ".md-for-human" / "review"
    review_dir.mkdir(parents=True)
    artifact_path = review_dir / "annotations.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "mdfh-review-v1",
                "created_by": {"kind": "agent", "name": "codex"},
                "source_manifest": ".md-for-human/manifest.json",
                "annotations": annotations,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact_path


def test_validate_review_accepts_v2_quote_and_document_comments(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact_v2(
        output_dir,
        [
            {
                "id": "ann_quote_setup",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "comment": "This is too vague; include the exact command and strict check.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
            {
                "id": "ann_doc_setup",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "scope": "document",
                "comment": "The setup page needs a failure-mode note.",
                "created_at": "2026-05-28T12:01:00Z",
                "updated_at": "2026-05-28T12:01:00Z",
            },
        ],
    )

    result = validate_review(output_dir)
    summary_path = output_dir / ".md-for-human" / "review" / "review.md"
    summary = summary_path.read_text(encoding="utf-8")

    assert result.errors == []
    assert result.warnings == []
    assert result.annotation_count == 2
    assert result.pages_touched == 1
    assert "### ann_quote_setup" in summary
    assert "> Run the setup steps here." in summary
    assert "This is too vague; include the exact command and strict check." in summary
    assert "### ann_doc_setup" in summary
    assert "Scope: document" in summary
    assert "type" not in summary.lower()


def test_validate_review_v2_summary_prefers_source_line_ranges(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact_v2(
        output_dir,
        [
            {
                "id": "ann_line_setup",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 5},
                "quote": "Run the setup steps here.",
                "comment": "This is too vague; include the exact command and strict check.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
            {
                "id": "ann_stale_quote_line_setup",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 7},
                "quote": "Old wording that no longer renders.",
                "comment": "Line numbers still give the agent the primary location.",
                "created_at": "2026-05-28T12:01:00Z",
                "updated_at": "2026-05-28T12:01:00Z",
            },
        ],
    )

    result = validate_review(output_dir)
    summary_path = output_dir / ".md-for-human" / "review" / "review.md"
    summary = summary_path.read_text(encoding="utf-8")

    assert result.errors == []
    assert result.summary_path == summary_path
    assert "## guide/setup.md:L5" in summary
    assert "## guide/setup.md:L5-L7" in summary
    assert "Line numbers still give the agent the primary location." in summary
    assert "ann_stale_quote_line_setup: quote not found in guide/setup.html" in result.warnings


def test_validate_review_v2_does_not_require_action_fields(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact_v2(
        output_dir,
        [
            {
                "id": "ann_minimal",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "comment": "Replace this with concrete command guidance.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert result.errors == []


def test_validate_review_v2_requires_comment_and_target(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact_v2(
        output_dir,
        [
            {
                "id": "ann_missing_comment",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
            {
                "id": "ann_missing_target",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "comment": "This lacks both quote and document scope.",
                "created_at": "2026-05-28T12:01:00Z",
                "updated_at": "2026-05-28T12:01:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert "ann_missing_comment: required field comment must be a non-empty string" in result.errors
    assert (
        'ann_missing_target: annotation must include quote or scope "document"'
        in result.errors
    )


def test_validate_review_v2_rejects_synthetic_landing_page_target(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "README.md").unlink()
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact_v2(
        output_dir,
        [
            {
                "id": "ann_synthetic",
                "page": "index.html",
                "source_path": "index.html",
                "quote": "Document Index",
                "comment": "Synthetic pages are not valid review targets.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert result.errors == [
        'ann_synthetic: page "index.html" is not listed in manifest documents'
    ]


def test_validate_review_accepts_valid_artifact_and_generates_summary(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_replace_setup",
                "type": "suggest_replace",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "note": "Use the project CLI terminology consistently.",
                "suggested_text": "Run md-for-human with the documented options.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
            {
                "id": "ann_insert_setup",
                "type": "suggest_insert",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "note": "Call out strict mode for agent handoff.",
                "placement": "after",
                "suggested_text": "Use --strict before handing the output back to an agent.",
                "created_at": "2026-05-28T12:01:00Z",
                "updated_at": "2026-05-28T12:01:00Z",
            },
        ],
    )

    result = validate_review(output_dir)
    summary_path = output_dir / ".md-for-human" / "review" / "review.md"
    summary = summary_path.read_text(encoding="utf-8")

    assert result.errors == []
    assert result.warnings == []
    assert result.annotation_count == 2
    assert result.pages_touched == 1
    assert result.summary_path == summary_path
    assert summary.startswith(
        "<!-- Generated from .md-for-human/review/annotations.json. Do not edit manually. -->"
    )
    assert "### ann_replace_setup - suggest_replace" in summary
    assert "### ann_insert_setup - suggest_insert" in summary
    assert "Placement: after" in summary
    assert "Suggested text:" in summary


def test_validate_review_rejects_synthetic_landing_page_target(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "README.md").unlink()
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_synthetic",
                "type": "comment",
                "page": "index.html",
                "source_path": "index.html",
                "quote": "Document Index",
                "note": "Synthetic pages are not valid review targets.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert result.errors == [
        'ann_synthetic: page "index.html" is not listed in manifest documents'
    ]


def test_validate_review_reports_schema_errors(sample_site_copy: Path, tmp_path: Path):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_bad",
                "type": "highlight",
                "page": "guide/setup.html",
                "source_path": "guide/intro.md",
                "quote": "Run the setup steps here.",
                "note": "Unsupported type and source mismatch.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
            {
                "id": "ann_bad",
                "type": "comment",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "note": "",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert 'ann_bad: unknown annotation type "highlight"' in result.errors
    assert (
        'ann_bad: source_path "guide/intro.md" does not match manifest documents '
        'for page "guide/setup.html"'
    ) in result.errors
    assert 'ann_bad: duplicate annotation id "ann_bad"' in result.errors
    assert "ann_bad: required field note must be a non-empty string" in result.errors


def test_validate_review_reports_invalid_json(sample_site_copy: Path, tmp_path: Path):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    review_dir = output_dir / ".md-for-human" / "review"
    review_dir.mkdir(parents=True)
    (review_dir / "annotations.json").write_text("{", encoding="utf-8")

    result = validate_review(output_dir)

    assert result.summary_path is None
    assert result.errors == ["annotations.json: invalid JSON: Expecting property name enclosed in double quotes"]


def test_validate_review_rejects_missing_or_invalid_annotations_array(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    review_dir = output_dir / ".md-for-human" / "review"
    review_dir.mkdir(parents=True)
    artifact_path = review_dir / "annotations.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "mdfh-review-v1",
                "created_by": {"kind": "agent", "name": "codex"},
                "source_manifest": ".md-for-human/manifest.json",
            }
        ),
        encoding="utf-8",
    )

    missing_result = validate_review(output_dir)

    assert missing_result.summary_path is None
    assert missing_result.errors == ["annotations.json: annotations missing or not an array"]

    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "mdfh-review-v1",
                "created_by": {"kind": "agent", "name": "codex"},
                "source_manifest": ".md-for-human/manifest.json",
                "annotations": {},
            }
        ),
        encoding="utf-8",
    )

    invalid_result = validate_review(output_dir)

    assert invalid_result.summary_path is None
    assert invalid_result.errors == ["annotations.json: annotations missing or not an array"]


def test_validate_review_reports_unsupported_schema_and_bad_manifest_hash(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    manifest_path = output_dir / ".md-for-human" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"][0]["source_sha256"] = "bad"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    review_dir = output_dir / ".md-for-human" / "review"
    review_dir.mkdir(parents=True)
    (review_dir / "annotations.json").write_text(
        json.dumps(
            {
                "schema_version": "mdfh-review-v0",
                "created_by": {"kind": "agent", "name": "codex"},
                "source_manifest": ".md-for-human/manifest.json",
                "annotations": [],
            }
        ),
        encoding="utf-8",
    )

    result = validate_review(output_dir)

    assert 'manifest documents[0]: source_sha256 for page "index.html" is not a valid sha256' in result.errors
    assert "annotations.json: schema_version missing or unsupported" in result.errors


def test_validate_review_rejects_unsafe_manifest_document_paths(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    manifest_path = output_dir / ".md-for-human" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"][1]["page"] = "../outside.html"
    manifest["documents"][2]["source_path"] = "/tmp/setup.md"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_unsafe",
                "type": "comment",
                "page": "../outside.html",
                "source_path": "guide/intro.md",
                "quote": "Welcome to the guide.",
                "note": "Unsafe manifest page paths must not be trusted.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert 'manifest documents[1]: page "../outside.html" is unsafe' in result.errors
    assert 'manifest documents[2]: source_path "/tmp/setup.md" is unsafe' in result.errors
    assert 'ann_unsafe: page "../outside.html" is not listed in manifest documents' in result.errors


def test_validate_review_rejects_html_metadata_mismatch(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    setup_page = output_dir / "guide" / "setup.html"
    setup_page.write_text(
        setup_page.read_text(encoding="utf-8")
        .replace('data-mdfh-page="guide/setup.html"', 'data-mdfh-page="wrong.html"')
        .replace('data-mdfh-source-path="guide/setup.md"', 'data-mdfh-source-path="wrong.md"'),
        encoding="utf-8",
    )
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_metadata",
                "type": "comment",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "note": "The HTML page metadata must match the manifest target.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert (
        'ann_metadata: HTML metadata page "wrong.html" does not match '
        '"guide/setup.html"'
    ) in result.errors
    assert (
        'ann_metadata: HTML metadata source_path "wrong.md" does not match '
        '"guide/setup.md"'
    ) in result.errors


def test_validate_review_rejects_missing_page_or_content_marker(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    setup_page = output_dir / "guide" / "setup.html"
    setup_html = setup_page.read_text(encoding="utf-8")
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_missing_content",
                "type": "comment",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "note": "A referenced page must expose review content metadata.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
        ],
    )

    setup_page.write_text(
        setup_html.replace(' data-mdfh-content="1"', ""),
        encoding="utf-8",
    )

    missing_marker_result = validate_review(output_dir)

    assert missing_marker_result.errors == [
        "ann_missing_content: page content marker not found in guide/setup.html"
    ]

    setup_page.unlink()

    missing_page_result = validate_review(output_dir)

    assert missing_page_result.errors == [
        "ann_missing_content: page content marker not found in guide/setup.html"
    ]


def test_validate_review_warns_for_missing_and_repeated_quotes(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "guide" / "setup.md").write_text(
        "# Setup\n\nRepeat anchor.\n\nRepeat anchor.\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_missing_quote",
                "type": "comment",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "This quote is not on the page.",
                "note": "The validator should report this as a warning.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
            {
                "id": "ann_repeated_quote",
                "type": "comment",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Repeat anchor.",
                "note": "Repeated quote anchors need human or agent attention.",
                "created_at": "2026-05-28T12:01:00Z",
                "updated_at": "2026-05-28T12:01:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert result.errors == []
    assert 'ann_missing_quote: quote not found in guide/setup.html' in result.warnings
    assert 'ann_repeated_quote: quote found multiple times in guide/setup.html' in result.warnings


def test_validate_review_canonicalizes_inline_markup_and_cjk_punctuation(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "guide" / "setup.md").write_text(
        (
            "# Setup\n\n"
            "现有 `workspace/groups/<group_slug>/`，"
            "暂不新增 [`workspace/roles/`](../reference/README.md)。\n"
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact_v2(
        output_dir,
        [
            {
                "id": "ann_cjk_inline",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "现有 workspace/groups/<group_slug>/，暂不新增 workspace/roles/。",
                "comment": "这类跨 inline markup 的选区刷新后也应该稳定定位。",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert result.errors == []
    assert result.warnings == []


def test_validate_review_warns_for_context_mismatch(sample_site_copy: Path, tmp_path: Path):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_context",
                "type": "comment",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "context_before": "Unexpected before",
                "context_after": "Unexpected after",
                "note": "Context should help identify stale or imprecise anchors.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            },
        ],
    )

    result = validate_review(output_dir)

    assert result.errors == []
    assert "ann_context: context_before does not match nearby rendered text" in result.warnings
    assert "ann_context: context_after does not match nearby rendered text" in result.warnings
