from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from md_for_human.builder import build_site
from md_for_human.review.server import (
    REVIEW_API_PREFIX,
    ReviewAuthError,
    ReviewServerApp,
    ReviewServerError,
    make_review_handler,
)
from md_for_human.review.artifacts import (
    stale_annotations_path,
    write_json_atomic,
    write_text_atomic,
)
from md_for_human.review.validate import validate_review


def _valid_artifact() -> dict[str, object]:
    return {
        "schema_version": "mdfh-review-v2",
        "source_manifest": ".md-for-human/manifest.json",
        "annotations": [
            {
                "id": "ann_ui",
                "page": "guide/setup.html",
                "source_path": "guide/setup.md",
                "quote": "Run the setup steps here.",
                "comment": "This should be clearer for handoff.",
                "created_at": "2026-05-28T12:00:00Z",
                "updated_at": "2026-05-28T12:00:00Z",
            }
        ],
    }


def test_review_server_initializes_empty_human_artifact(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")

    state = app.get_state(token="test-token")
    artifact_path = output_dir / ".md-for-human" / "review" / "annotations.json"

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "mdfh-review-v2"
    assert "created_by" not in artifact
    assert artifact["annotations"] == []
    assert state["artifact"] == artifact
    assert state["validation"]["errors"] == []


def test_review_server_requires_token_for_api_calls(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")

    with pytest.raises(ReviewAuthError):
        app.get_state(token="")
    with pytest.raises(ReviewAuthError):
        app.save_annotations(token="wrong-token", artifact=_valid_artifact())
    with pytest.raises(ReviewAuthError):
        app.validate(token="wrong-token")


def test_review_server_rejects_hard_failures_before_writing(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    artifact_path = output_dir / ".md-for-human" / "review" / "annotations.json"
    original = artifact_path.read_text(encoding="utf-8") if artifact_path.exists() else ""
    invalid_artifact = _valid_artifact()
    annotations = invalid_artifact["annotations"]
    assert isinstance(annotations, list)
    annotations[0]["page"] = "index.html/../synthetic.html"

    with pytest.raises(ReviewServerError) as exc_info:
        app.save_annotations(token="test-token", artifact=invalid_artifact)

    assert "is not listed in manifest documents" in "\n".join(exc_info.value.errors)
    assert artifact_path.read_text(encoding="utf-8") == original
    assert not (output_dir / ".md-for-human" / "review" / "review.md").exists()


def test_review_server_rejects_legacy_schema_on_save(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    legacy_artifact = _valid_artifact()
    legacy_artifact["schema_version"] = "mdfh-review-v1"
    legacy_artifact["created_by"] = {"kind": "human", "name": "local-reviewer"}

    with pytest.raises(ReviewServerError) as exc_info:
        app.save_annotations(token="test-token", artifact=legacy_artifact)

    assert "browser review writes only mdfh-review-v2" in "\n".join(exc_info.value.errors)


def test_review_server_saves_degraded_quote_without_returning_user_warnings(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    annotations[0]["quote"] = "Missing quote anchor."

    response = app.save_annotations(token="test-token", artifact=artifact)

    assert response["validation"]["errors"] == []
    assert response["validation"]["warnings"] == []
    assert response["validation"]["summary_path"] == str(
        output_dir / ".md-for-human" / "review" / "review.md"
    )
    saved = json.loads(
        (output_dir / ".md-for-human" / "review" / "annotations.json").read_text(
            encoding="utf-8"
        )
    )
    saved_annotations = saved["annotations"]
    assert isinstance(saved_annotations, list)
    assert saved_annotations[0]["quote"] == "Missing quote anchor."
    assert saved_annotations[0]["locator"]["status"] == "degraded"
    assert (output_dir / ".md-for-human" / "review" / "review.md").exists()

    dev_result = validate_review(output_dir)
    assert dev_result.warnings == ["ann_ui: quote not found in guide/setup.html"]


def test_review_server_refreshes_locator_metadata_for_existing_degraded_quotes(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    annotations[0]["quote"] = "Missing quote anchor."
    write_json_atomic(
        output_dir / ".md-for-human" / "review" / "annotations.json",
        artifact,
    )
    app = ReviewServerApp(output_dir, token="test-token")

    state = app.get_state(token="test-token")

    state_annotations = state["artifact"]["annotations"]
    assert isinstance(state_annotations, list)
    assert state_annotations[0]["locator"]["status"] == "degraded"
    saved = json.loads(
        (output_dir / ".md-for-human" / "review" / "annotations.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved["annotations"][0]["locator"]["reason"] == "quote_not_found"


def test_review_server_valid_saved_artifact_passes_validate_review(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")

    response = app.save_annotations(token="test-token", artifact=_valid_artifact())
    result = validate_review(output_dir)

    assert response["validation"]["errors"] == []
    assert response["validation"]["warnings"] == []
    assert result.errors == []
    assert result.warnings == []
    assert result.annotation_count == 1


def test_atomic_text_writes_use_unique_temp_files(tmp_path: Path):
    path = tmp_path / "review.md"
    errors: list[BaseException] = []

    def write_content(index: int) -> None:
        try:
            write_text_atomic(path, f"content {index}\n")
        except BaseException as exc:  # pragma: no cover - only fails on race regressions
            errors.append(exc)

    threads = [threading.Thread(target=write_content, args=(index,)) for index in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert path.read_text(encoding="utf-8").startswith("content ")


def test_review_server_rebuilds_when_source_tree_changes(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    rebuilds: list[tuple[Path, Path]] = []

    def fake_rebuild(source_input: Path, rebuild_output: Path) -> None:
        rebuilds.append((source_input, rebuild_output))
        build_site(source_input, rebuild_output)

    app = ReviewServerApp(
        output_dir,
        token="test-token",
        source_input=sample_site_copy,
        rebuild_site=fake_rebuild,
        source_poll_interval=0,
        rebuild_debounce=0,
    )
    initial_state = app.get_state(token="test-token")

    (sample_site_copy / "guide" / "setup.md").write_text(
        "# Setup\n\n## Install\n\nRun the updated setup steps here.\n",
        encoding="utf-8",
    )
    changed_state = app.get_state(token="test-token")

    assert rebuilds == [(sample_site_copy, output_dir)]
    assert changed_state["build"]["version"] == initial_state["build"]["version"] + 1
    assert changed_state["build"]["error"] is None
    assert "updated setup steps" in (output_dir / "guide" / "setup.html").read_text(
        encoding="utf-8"
    )


def test_review_server_quarantines_stale_annotations_after_source_delete(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(
        output_dir,
        token="test-token",
        source_input=sample_site_copy,
        source_poll_interval=0,
        rebuild_debounce=0,
    )
    app.save_annotations(token="test-token", artifact=_valid_artifact())

    (sample_site_copy / "guide" / "setup.md").unlink()
    state = app.get_state(token="test-token")

    assert state["artifact"]["annotations"] == []
    stale = json.loads(stale_annotations_path(output_dir).read_text(encoding="utf-8"))
    assert stale["annotations"][0]["id"] == "ann_ui"
    assert "no longer listed" in stale["annotations"][0]["stale_reason"]
    result = validate_review(output_dir)
    assert result.errors == []


def test_review_server_quarantines_stale_annotations_after_source_path_mismatch(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    annotations[0]["source_path"] = "guide/intro.md"
    write_json_atomic(
        output_dir / ".md-for-human" / "review" / "annotations.json",
        artifact,
    )

    app = ReviewServerApp(output_dir, token="test-token")
    state = app.get_state(token="test-token")

    assert state["artifact"]["annotations"] == []
    stale = json.loads(stale_annotations_path(output_dir).read_text(encoding="utf-8"))
    assert stale["annotations"][0]["id"] == "ann_ui"
    assert "no longer matches manifest source_path" in stale["annotations"][0]["stale_reason"]
    result = validate_review(output_dir)
    assert result.errors == []


def test_review_server_rebuild_failure_keeps_last_good_output(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    original_html = (output_dir / "guide" / "setup.html").read_text(encoding="utf-8")

    def failing_rebuild(_source_input: Path, _rebuild_output: Path) -> None:
        raise RuntimeError("broken markdown")

    app = ReviewServerApp(
        output_dir,
        token="test-token",
        source_input=sample_site_copy,
        rebuild_site=failing_rebuild,
        source_poll_interval=0,
        rebuild_debounce=0,
    )
    initial_state = app.get_state(token="test-token")

    (sample_site_copy / "guide" / "setup.md").write_text("# Broken\n", encoding="utf-8")
    changed_state = app.get_state(token="test-token")

    assert changed_state["build"]["version"] == initial_state["build"]["version"]
    assert "broken markdown" in changed_state["build"]["error"]
    assert (output_dir / "guide" / "setup.html").read_text(encoding="utf-8") == original_html


def test_review_server_injects_client_without_modifying_html(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    html_path = output_dir / "guide" / "setup.html"
    original_html = html_path.read_text(encoding="utf-8")
    app = ReviewServerApp(output_dir, token="test-token")

    served = app.render_site_file("guide/setup.html")

    assert REVIEW_API_PREFIX in served
    assert "data-mdfh-review-unplaced" in served
    assert "data-mdfh-review-open" in served
    assert html_path.read_text(encoding="utf-8") == original_html


def test_review_server_static_path_stays_inside_output_dir(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")

    with pytest.raises(ReviewServerError):
        app.render_site_file("../secret.html")
    with pytest.raises(ReviewServerError):
        app.render_site_file("/etc/passwd")


def test_review_server_http_api_requires_token_and_does_not_enable_cors(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_review_handler(app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        request = Request(f"http://127.0.0.1:{server.server_port}{REVIEW_API_PREFIX}/state")
        with pytest.raises(HTTPError) as exc_info:
            urlopen(request, timeout=2)
        assert exc_info.value.code == 401

        request = Request(
            f"http://127.0.0.1:{server.server_port}{REVIEW_API_PREFIX}/state",
            headers={"X-MDFH-Review-Token": "test-token", "Origin": "https://example.com"},
        )
        response = urlopen(request, timeout=2)
        assert response.status == 200
        assert response.headers.get("Access-Control-Allow-Origin") is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_review_server_injected_ui_uses_inline_comments_without_fixed_rail(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")

    served = app.render_site_file("guide/setup.html")

    assert "data-mdfh-review-unplaced" in served
    assert "mdfh-review-row" in served
    assert "mdfh-review-comments" in served
    assert "data-mdfh-review-comment-input" in served
    assert "mdfh-review-underline" in served
    assert "pageAnnotations" in served
    assert "renderInlineComments" in served
    assert "hasActiveEditor" in served
    assert "if (!preserveEditor) {" in served
    assert "uniqueMessages" in served
    assert "Page comments" in served
    assert "Check unplaced comments on each page" not in served
    assert "Quote not found on this page" not in served
    assert "findQuoteRanges" in served
    assert "/state" in served
    assert "locateQuote" in served
    assert "scrollIntoView" in served
    assert "data-mdfh-review-rail" not in served
    assert "data-mdfh-review-connector-layer" not in served
    assert "positionCommentCards" not in served
    assert "updateConnectors" not in served
    assert 'window.addEventListener("scroll"' not in served
    assert "suggest_insert" not in served
    assert "Selected annotation" not in served
    assert "Reviewer name" not in served
    assert "Status" not in served
