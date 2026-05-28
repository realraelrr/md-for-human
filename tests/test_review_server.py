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


def test_review_server_saves_quote_warnings_and_regenerates_summary(
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
    assert response["validation"]["warnings"] == [
        "ann_ui: quote not found in guide/setup.html"
    ]
    assert response["validation"]["summary_path"] == str(
        output_dir / ".md-for-human" / "review" / "review.md"
    )
    saved = json.loads(
        (output_dir / ".md-for-human" / "review" / "annotations.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved == artifact
    assert (output_dir / ".md-for-human" / "review" / "review.md").exists()


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
    assert "data-mdfh-review-panel" in served
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


def test_review_server_injected_ui_uses_comment_rail_without_action_form(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")

    served = app.render_site_file("guide/setup.html")

    assert "data-mdfh-review-rail" in served
    assert "data-mdfh-review-comment-input" in served
    assert "mdfh-review-underline" in served
    assert "locateQuote" in served
    assert "scrollIntoView" in served
    assert "suggest_insert" not in served
    assert "Selected annotation" not in served
    assert "Reviewer name" not in served
    assert "Status" not in served
