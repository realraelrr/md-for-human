from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from md_for_human.builder import build_site
from md_for_human.review.validate import validate_review


def _compact_annotation(annotation: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: annotation[key]
        for key in ("id", "source_path", "source_range", "comment", "source_sha256")
        if key in annotation
    }
    meta = {key: annotation[key] for key in ("quote",) if key in annotation}
    if meta:
        compact["meta"] = meta
    return compact


def _write_review_artifact(output_dir: Path, annotations: list[dict[str, Any]]) -> Path:
    review_dir = output_dir / ".md-for-human" / "review"
    review_dir.mkdir(parents=True)
    artifact_path = review_dir / "annotations.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "mdfh-review-v2",
                "source_manifest": ".md-for-human/manifest.json",
                "annotations": [_compact_annotation(annotation) for annotation in annotations],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact_path


def test_validate_review_normalizes_minimal_agent_intent(
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
                "annotations": [
                    {
                        "source_path": "guide/setup.md",
                        "source_range": {"start_line": 5, "end_line": 5},
                        "comment": "Make the setup command explicit.",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_review(output_dir)
    saved = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert result.errors == []
    assert result.warnings == []
    assert saved["schema_version"] == "mdfh-review-v2"
    assert saved["source_manifest"] == ".md-for-human/manifest.json"
    assert saved["annotations"][0]["id"].startswith("ann_")
    assert saved["annotations"][0]["source_path"] == "guide/setup.md"
    assert saved["annotations"][0]["source_range"] == {"start_line": 5, "end_line": 5}
    assert saved["annotations"][0]["comment"] == "Make the setup command explicit."
    assert isinstance(saved["annotations"][0]["source_sha256"], str)
    assert "meta" not in saved["annotations"][0]


def test_validate_review_accepts_v2_quote_and_document_comments(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_quote_setup",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 5},
                "quote": "Run the setup steps here.",
                "comment": "This is too vague; include the exact command and strict check.",
            },
            {
                "id": "ann_doc_setup",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 0, "end_line": 0},
                "comment": "The setup page needs a failure-mode note.",
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
    assert "## guide/setup.md:L0" in summary
    assert "Global comment" in summary
    assert "type" not in summary.lower()


def test_validate_review_v2_summary_prefers_source_line_ranges(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_line_setup",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 5},
                "quote": "Run the setup steps here.",
                "comment": "This is too vague; include the exact command and strict check.",
            },
            {
                "id": "ann_stale_quote_line_setup",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 4, "end_line": 5},
                "quote": "Old wording that no longer renders.",
                "comment": "Line numbers still give the agent the primary location.",
            },
        ],
    )

    result = validate_review(output_dir)
    summary_path = output_dir / ".md-for-human" / "review" / "review.md"
    summary = summary_path.read_text(encoding="utf-8")

    assert result.errors == []
    assert result.summary_path == summary_path
    assert "## guide/setup.md:L5" in summary
    assert "## guide/setup.md:L4-L5" in summary
    assert "Line numbers still give the agent the primary location." in summary
    assert result.warnings == []


def test_validate_review_v2_accepts_l0_global_comment(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_global_setup",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 0, "end_line": 0},
                "comment": "This page needs a clearer overall narrative.",
            },
        ],
    )

    result = validate_review(output_dir)
    summary = (output_dir / ".md-for-human" / "review" / "review.md").read_text(
        encoding="utf-8"
    )

    assert result.errors == []
    assert "## guide/setup.md:L0" in summary
    assert "Global comment" in summary
    assert "This page needs a clearer overall narrative." in summary


def test_validate_review_v2_rejects_invalid_source_ranges(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_zero_to_one",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 0, "end_line": 1},
                "comment": "Invalid mixed global range.",
            },
            {
                "id": "ann_reversed",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 3, "end_line": 2},
                "comment": "Invalid reversed range.",
            },
            {
                "id": "ann_bool",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": True, "end_line": 2},
                "comment": "Invalid boolean range.",
            },
            {
                "id": "ann_non_object",
                "source_path": "guide/setup.md",
                "source_range": "1:2",
                "comment": "Invalid non-object range.",
            },
            {
                "id": "ann_out_of_bounds",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 6},
                "comment": "Invalid range beyond the source file.",
            },
        ],
    )

    result = validate_review(output_dir)

    assert (
        "ann_zero_to_one: source_range must be 0:0 or positive start_line and end_line"
        in result.errors
    )
    assert (
        "ann_reversed: source_range must be 0:0 or positive start_line and end_line"
        in result.errors
    )
    assert (
        "ann_bool: source_range must be 0:0 or positive start_line and end_line"
        in result.errors
    )
    assert "ann_non_object: source_range must be an object" in result.errors
    assert (
        "ann_out_of_bounds: source_range end_line 6 exceeds "
        "source_line_count 5 for guide/setup.md"
    ) in result.errors
    assert result.summary_path is None
    assert not (output_dir / ".md-for-human" / "review" / "review.md").exists()


def test_validate_review_rejects_missing_and_invalid_manifest_source_line_count(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    manifest_path = output_dir / ".md-for-human" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["documents"][0]["source_line_count"]
    manifest["documents"][1]["source_line_count"] = -1
    manifest["documents"][2]["source_line_count"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_setup",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 5},
                "comment": "A valid annotation should still reject a bad manifest.",
            },
        ],
    )

    result = validate_review(output_dir)

    assert "manifest documents[0]: source_line_count missing or invalid" in result.errors
    assert "manifest documents[1]: source_line_count missing or invalid" in result.errors
    assert "manifest documents[2]: source_line_count missing or invalid" in result.errors
    assert result.summary_path is None
    assert not (output_dir / ".md-for-human" / "review" / "review.md").exists()


def test_validate_review_rejects_missing_and_invalid_manifest_protocol_metadata(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    manifest_path = output_dir / ".md-for-human" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["manifest_schema_version"]
    manifest["tool_name"] = "other-tool"
    manifest["tool_version"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_setup",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 5},
                "comment": "A valid annotation should still reject a bad manifest.",
            },
        ],
    )

    result = validate_review(output_dir)

    assert (
        "manifest.json: manifest_schema_version missing or unsupported"
        in result.errors
    )
    assert 'manifest.json: tool_name must be "md-for-human"' in result.errors
    assert "manifest.json: tool_version missing or invalid" in result.errors
    assert result.summary_path is None
    assert not (output_dir / ".md-for-human" / "review" / "review.md").exists()


def test_validate_review_does_not_update_existing_summary_on_hard_errors(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_out_of_bounds",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 6, "end_line": 6},
                "comment": "This invalid range must not overwrite the summary.",
            },
        ],
    )
    summary_path = output_dir / ".md-for-human" / "review" / "review.md"
    summary_path.write_text("existing summary\n", encoding="utf-8")

    result = validate_review(output_dir)

    assert (
        "ann_out_of_bounds: source_range end_line 6 exceeds "
        "source_line_count 5 for guide/setup.md"
    ) in result.errors
    assert result.summary_path is None
    assert summary_path.read_text(encoding="utf-8") == "existing summary\n"


def test_validate_review_archives_source_hash_mismatch_before_summary(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_old_hash",
                "source_path": "guide/setup.md",
                "source_sha256": "0" * 64,
                "source_range": {"start_line": 5, "end_line": 5},
                "comment": "Old source feedback.",
            },
        ],
    )

    result = validate_review(output_dir)
    artifact = json.loads(
        (output_dir / ".md-for-human" / "review" / "annotations.json").read_text(
            encoding="utf-8"
        )
    )
    archive = json.loads(
        (output_dir / ".md-for-human" / "review" / "archive.json").read_text(
            encoding="utf-8"
        )
    )
    summary = (output_dir / ".md-for-human" / "review" / "review.md").read_text(
        encoding="utf-8"
    )

    assert result.errors == []
    assert artifact["annotations"] == []
    assert archive["annotations"][0]["id"] == "ann_old_hash"
    assert archive["annotations"][0]["archive_reason"] == "source_changed"
    assert "ann_old_hash" not in summary


def test_validate_review_v2_does_not_require_action_fields(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_minimal",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 5},
                "quote": "Run the setup steps here.",
                "comment": "Replace this with concrete command guidance.",
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
    _write_review_artifact(
        output_dir,
        [
                {
                    "id": "ann_missing_comment",
                        "source_path": "guide/setup.md",
                    "source_range": {"start_line": 5, "end_line": 5},
                    "quote": "Run the setup steps here.",
            },
            {
                "id": "ann_missing_target",
                "source_path": "guide/setup.md",
                "comment": "This lacks both quote and source_range.",
            },
        ],
    )

    result = validate_review(output_dir)

    assert "ann_missing_comment: required field comment must be a non-empty string" in result.errors
    assert "ann_missing_target: source_range must be an object" in result.errors


def test_validate_review_v2_archives_synthetic_landing_page_target(
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
                "source_path": "index.html",
                "quote": "Document Index",
                "comment": "Synthetic pages are not valid review targets.",
            },
        ],
    )

    result = validate_review(output_dir)
    artifact = json.loads(
        (output_dir / ".md-for-human" / "review" / "annotations.json").read_text(
            encoding="utf-8"
        )
    )
    archive = json.loads(
        (output_dir / ".md-for-human" / "review" / "archive.json").read_text(
            encoding="utf-8"
        )
    )

    assert result.errors == []
    assert artifact["annotations"] == []
    assert archive["annotations"][0]["id"] == "ann_synthetic"
    assert archive["annotations"][0]["archive_reason"] == "source_removed"


def test_validate_review_reports_schema_errors(sample_site_copy: Path, tmp_path: Path):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_bad",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "comment": "First duplicate id.",
            },
            {
                "id": "ann_bad",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
            },
        ],
    )

    result = validate_review(output_dir)

    assert 'ann_bad: duplicate annotation id "ann_bad"' in result.errors
    assert "ann_bad: required field comment must be a non-empty string" in result.errors


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
                "schema_version": "mdfh-review-v2",
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
                "schema_version": "mdfh-review-v2",
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
                "source_path": "guide/intro.md",
                "quote": "Welcome to the guide.",
                "comment": "Unsafe manifest page paths must not be trusted.",
            },
        ],
    )

    result = validate_review(output_dir)

    assert 'manifest documents[1]: page "../outside.html" is unsafe' in result.errors
    assert 'manifest documents[2]: source_path "/tmp/setup.md" is unsafe' in result.errors


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
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "comment": "The HTML page metadata must match the manifest target.",
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


def test_validate_review_source_range_does_not_require_html_quote_marker(
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
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 5},
                "quote": "Run the setup steps here.",
                "comment": "A referenced page must expose review content metadata.",
            },
        ],
    )

    setup_page.write_text(
        setup_html.replace(' data-mdfh-content="1"', ""),
        encoding="utf-8",
    )

    missing_marker_result = validate_review(output_dir)

    assert missing_marker_result.errors == []
    assert missing_marker_result.warnings == []

    setup_page.unlink()

    missing_page_result = validate_review(output_dir)

    assert missing_page_result.errors == []
    assert missing_page_result.warnings == []


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
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 3, "end_line": 3},
                "quote": "This quote is not on the page.",
                "comment": "The validator should report this as a warning.",
            },
            {
                "id": "ann_repeated_quote",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 3, "end_line": 3},
                "quote": "Repeat anchor.",
                "comment": "Repeated quote anchors need human or agent attention.",
            },
        ],
    )

    result = validate_review(output_dir)

    assert result.errors == []
    assert result.warnings == []


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
    _write_review_artifact(
        output_dir,
        [
            {
                "id": "ann_cjk_inline",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 3, "end_line": 3},
                "quote": "现有 workspace/groups/<group_slug>/，暂不新增 workspace/roles/。",
                "comment": "这类跨 inline markup 的选区刷新后也应该稳定定位。",
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
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 5},
                "quote": "Run the setup steps here.",
                "comment": "Context should help identify stale or imprecise anchors.",
            },
        ],
    )

    result = validate_review(output_dir)

    assert result.errors == []
    assert result.warnings == []
