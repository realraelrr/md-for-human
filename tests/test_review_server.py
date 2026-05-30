from __future__ import annotations

import json
import re
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
    archive_path,
    write_json_atomic,
    write_text_atomic,
)
from md_for_human.review.validate import validate_review
from md_for_human.static_assets import BASE_CSS, BASE_JS


def _valid_artifact() -> dict[str, object]:
    return {
        "schema_version": "mdfh-review-v2",
        "source_manifest": ".md-for-human/manifest.json",
        "annotations": [
            {
                "id": "ann_ui",
                "source_path": "guide/setup.md",
                "source_range": {"start_line": 5, "end_line": 5},
                "comment": "This should be clearer for handoff.",
                "meta": {
                    "quote": "Run the setup steps here.",
                },
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
    annotations[0]["source_range"] = {"start_line": 5, "end_line": 6}

    with pytest.raises(ReviewServerError) as exc_info:
        app.save_annotations(token="test-token", artifact=invalid_artifact)

    assert (
        "source_range end_line 6 exceeds source_line_count 5 for guide/setup.md"
        in "\n".join(exc_info.value.errors)
    )
    assert artifact_path.read_text(encoding="utf-8") == original
    assert not (output_dir / ".md-for-human" / "review" / "review.md").exists()


def test_review_server_rejects_invalid_save_before_writing_archive(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    artifact_path = output_dir / ".md-for-human" / "review" / "annotations.json"
    original = artifact_path.read_text(encoding="utf-8") if artifact_path.exists() else ""
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    stale_annotation = dict(annotations[0])
    stale_annotation["id"] = "ann_old"
    stale_annotation["source_sha256"] = "0" * 64
    invalid_annotation = dict(annotations[0])
    invalid_annotation["id"] = "ann_invalid"
    invalid_annotation.pop("comment")
    annotations[:] = [stale_annotation, invalid_annotation]

    with pytest.raises(ReviewServerError) as exc_info:
        app.save_annotations(token="test-token", artifact=artifact)

    assert "required field comment" in "\n".join(exc_info.value.errors)
    assert artifact_path.read_text(encoding="utf-8") == original
    assert not archive_path(output_dir).exists()


def test_review_server_rejects_unsupported_schema_on_save(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    unsupported_artifact = _valid_artifact()
    unsupported_artifact["schema_version"] = "mdfh-review-v1"

    with pytest.raises(ReviewServerError) as exc_info:
        app.save_annotations(token="test-token", artifact=unsupported_artifact)

    assert "browser review writes only mdfh-review-v2" in "\n".join(exc_info.value.errors)


def test_review_server_saves_quote_as_the_only_optional_meta(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    annotations[0]["meta"]["quote"] = "Missing quote anchor."

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
    assert saved_annotations[0]["meta"] == {"quote": "Missing quote anchor."}
    assert (output_dir / ".md-for-human" / "review" / "review.md").exists()

    dev_result = validate_review(output_dir)
    assert dev_result.warnings == []


def test_review_server_strips_old_bookkeeping_metadata(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    annotations[0]["meta"]["quote"] = "Missing quote anchor."
    write_json_atomic(
        output_dir / ".md-for-human" / "review" / "annotations.json",
        artifact,
    )
    app = ReviewServerApp(output_dir, token="test-token")

    state = app.get_state(token="test-token")

    state_annotations = state["artifact"]["annotations"]
    assert isinstance(state_annotations, list)
    assert state_annotations[0]["meta"] == {"quote": "Missing quote anchor."}
    saved = json.loads(
        (output_dir / ".md-for-human" / "review" / "annotations.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved["annotations"][0]["meta"] == {"quote": "Missing quote anchor."}


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


def test_review_server_saves_source_range_and_generates_line_summary(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    annotations[0]["source_range"] = {"start_line": 5, "end_line": 5}

    response = app.save_annotations(token="test-token", artifact=artifact)
    saved = response["artifact"]
    saved_annotations = saved["annotations"]
    assert isinstance(saved_annotations, list)

    summary = (output_dir / ".md-for-human" / "review" / "review.md").read_text(
        encoding="utf-8"
    )
    assert saved_annotations[0]["source_range"] == {"start_line": 5, "end_line": 5}
    assert isinstance(saved_annotations[0]["source_sha256"], str)
    assert "## guide/setup.md:L5" in summary


def test_review_server_keeps_quote_context_without_requiring_quote_match(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    annotations[0]["source_range"] = {"start_line": 5, "end_line": 5}
    annotations[0]["meta"]["quote"] = "Old wording that is not in rendered HTML."

    response = app.save_annotations(token="test-token", artifact=artifact)
    saved_annotations = response["artifact"]["annotations"]
    assert isinstance(saved_annotations, list)

    assert saved_annotations[0]["meta"] == {
        "quote": "Old wording that is not in rendered HTML."
    }
    assert response["validation"]["warnings"] == []


def test_review_server_saves_l0_global_comment(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    annotations[0]["meta"].pop("quote")
    annotations[0]["source_range"] = {"start_line": 0, "end_line": 0}

    response = app.save_annotations(token="test-token", artifact=artifact)
    saved_annotations = response["artifact"]["annotations"]
    assert isinstance(saved_annotations, list)
    saved = saved_annotations[0]

    assert saved["source_range"] == {"start_line": 0, "end_line": 0}
    assert isinstance(saved["source_sha256"], str)
    summary = (output_dir / ".md-for-human" / "review" / "review.md").read_text(
        encoding="utf-8"
    )
    assert "## guide/setup.md:L0" in summary
    assert "Global comment" in summary


def test_review_server_archives_annotations_after_source_hash_change(
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

    (sample_site_copy / "guide" / "setup.md").write_text(
        "# Setup\n\n## Install\n\nRun the changed setup steps here.\n",
        encoding="utf-8",
    )
    state = app.get_state(token="test-token")

    assert state["artifact"]["annotations"] == []
    archive = json.loads(archive_path(output_dir).read_text(encoding="utf-8"))
    archived = archive["annotations"][0]
    assert archived["id"] == "ann_ui"
    assert archived["archive_reason"] == "source_changed"
    assert set(archived) == {
        "id",
        "source_path",
        "source_range",
        "comment",
        "source_sha256",
        "meta",
        "archive_reason",
    }
    assert archived["meta"] == {"quote": "Run the setup steps here."}
    summary = (output_dir / ".md-for-human" / "review" / "review.md").read_text(
        encoding="utf-8"
    )
    assert "ann_ui" not in summary


def test_review_server_state_archiving_does_not_write_summary_for_invalid_active_artifact(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    artifact_path = output_dir / ".md-for-human" / "review" / "annotations.json"
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    stale_annotation = dict(annotations[0])
    stale_annotation["id"] = "ann_old"
    stale_annotation["source_sha256"] = "0" * 64
    invalid_annotation = dict(annotations[0])
    invalid_annotation["id"] = "ann_invalid"
    invalid_annotation["source_range"] = {"start_line": 5, "end_line": 6}
    annotations[:] = [stale_annotation, invalid_annotation]
    write_json_atomic(artifact_path, artifact)

    state = app.get_state(token="test-token")

    assert (
        "ann_invalid: source_range end_line 6 exceeds "
        "source_line_count 5 for guide/setup.md"
    ) in state["validation"]["errors"]
    assert not (output_dir / ".md-for-human" / "review" / "review.md").exists()
    archive = json.loads(archive_path(output_dir).read_text(encoding="utf-8"))
    assert archive["annotations"][0]["id"] == "ann_old"


def test_review_server_save_archives_stale_annotations_without_dropping_them(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")
    artifact = _valid_artifact()
    annotations = artifact["annotations"]
    assert isinstance(annotations, list)
    stale_annotation = dict(annotations[0])
    stale_annotation["id"] = "ann_old"
    stale_annotation["source_sha256"] = "0" * 64
    active_annotation = dict(annotations[0])
    active_annotation["id"] = "ann_new"
    annotations[:] = [stale_annotation, active_annotation]

    response = app.save_annotations(token="test-token", artifact=artifact)

    saved_annotations = response["artifact"]["annotations"]
    assert isinstance(saved_annotations, list)
    assert [item["id"] for item in saved_annotations] == ["ann_new"]
    archive = json.loads(archive_path(output_dir).read_text(encoding="utf-8"))
    archived = archive["annotations"][0]
    assert archived["id"] == "ann_old"
    assert archived["archive_reason"] == "source_changed"


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


def test_review_server_archives_annotations_after_source_delete(
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
    archive = json.loads(archive_path(output_dir).read_text(encoding="utf-8"))
    archived = archive["annotations"][0]
    assert archived["id"] == "ann_ui"
    assert archived["archive_reason"] == "source_removed"
    result = validate_review(output_dir)
    assert result.errors == []


def test_review_server_archives_annotations_after_source_path_mismatch(
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

    assert state["artifact"]["annotations"]
    meta = state["artifact"]["annotations"][0].get("meta", {})
    assert "page" not in meta
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

    served = app.render_site_file("guide/setup.html", nonce="test-nonce")

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
        app.render_site_file("../secret.html", nonce="test-nonce")
    with pytest.raises(ReviewServerError):
        app.render_site_file("/etc/passwd", nonce="test-nonce")


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


def test_review_server_html_response_adds_csp_nonce_without_affecting_api_or_assets(
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
        html_response = urlopen(
            f"http://127.0.0.1:{server.server_port}/guide/setup.html",
            timeout=2,
        )
        html = html_response.read().decode("utf-8")
        csp = html_response.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "script-src 'nonce-" in csp
        assert "style-src 'nonce-" in csp
        assert "connect-src 'self'" in csp
        assert "object-src 'none'" in csp
        assert "'unsafe-inline'" not in csp
        nonce_match = re.search(r"'nonce-([^']+)'", csp)
        assert nonce_match is not None
        assert f'nonce="{nonce_match.group(1)}"' in html

        api_request = Request(
            f"http://127.0.0.1:{server.server_port}{REVIEW_API_PREFIX}/state",
            headers={"X-MDFH-Review-Token": "test-token"},
        )
        api_response = urlopen(api_request, timeout=2)
        assert api_response.status == 200
        assert api_response.headers.get("Content-Security-Policy") is None

        asset_response = urlopen(
            f"http://127.0.0.1:{server.server_port}/images/diagram.png",
            timeout=2,
        )
        assert asset_response.status == 200
        assert asset_response.headers.get("Content-Security-Policy") is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_review_server_nonce_only_marks_owned_inline_assets(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "guide" / "setup.md").write_text(
        "\n".join(
            [
                "# Setup",
                "",
                '<script data-mdfh-base-script>window.mdfhSpoofed = true;</script>',
                '<script>window.mdfhPwned = true;</script>',
                '<style data-mdfh-base-style>.spoofed { color: red; }</style>',
                '<button onclick="window.mdfhClicked = true">Click</button>',
                '<a href="javascript:window.mdfhLink = true">JS link</a>',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    html_path = output_dir / "guide" / "setup.html"
    original_html = html_path.read_text(encoding="utf-8")
    app = ReviewServerApp(output_dir, token="test-token")

    served = app.render_site_file("guide/setup.html", nonce="fixed-nonce")

    assert '<style data-mdfh-base-style nonce="fixed-nonce">:root' in served
    assert '<script data-mdfh-base-script nonce="fixed-nonce">(() => {' in served
    assert '<style data-mdfh-review-style nonce="fixed-nonce">' in served
    assert '<script data-mdfh-review-script nonce="fixed-nonce">' in served
    assert '<script data-mdfh-base-script>window.mdfhSpoofed = true;</script>' in served
    assert '<script>window.mdfhPwned = true;</script>' in served
    assert '<style data-mdfh-base-style>.spoofed { color: red; }</style>' in served
    assert '<button onclick="window.mdfhClicked = true">Click</button>' in served
    assert '<a href="javascript:window.mdfhLink = true">JS link</a>' in served
    assert html_path.read_text(encoding="utf-8") == original_html


def test_review_server_legacy_output_does_not_nonce_spoofed_markers(
    sample_site_copy: Path,
    tmp_path: Path,
):
    (sample_site_copy / "guide" / "setup.md").write_text(
        "\n".join(
            [
                "# Setup",
                "",
                '<script data-mdfh-base-script>window.mdfhSpoofed = true;</script>',
                '<style data-mdfh-base-style>.spoofed { color: red; }</style>',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    html_path = output_dir / "guide" / "setup.html"
    legacy_html = (
        html_path.read_text(encoding="utf-8")
        .replace(
            f"<style data-mdfh-base-style>{BASE_CSS}</style>",
            f"<style>{BASE_CSS}</style>",
        )
        .replace(
            f"<script data-mdfh-base-script>{BASE_JS}</script>",
            f"<script>{BASE_JS}</script>",
        )
    )
    html_path.write_text(legacy_html, encoding="utf-8")
    app = ReviewServerApp(output_dir, token="test-token")

    served = app.render_site_file("guide/setup.html", nonce="fixed-nonce")

    assert '<style nonce="fixed-nonce">:root' in served
    assert '<script nonce="fixed-nonce">(() => {' in served
    assert '<script data-mdfh-base-script>window.mdfhSpoofed = true;</script>' in served
    assert '<style data-mdfh-base-style>.spoofed { color: red; }</style>' in served


def test_review_server_injected_ui_uses_inline_comments_without_fixed_rail(
    sample_site_copy: Path,
    tmp_path: Path,
):
    output_dir = tmp_path / "output"
    build_site(sample_site_copy, output_dir)
    app = ReviewServerApp(output_dir, token="test-token")

    served = app.render_site_file("guide/setup.html", nonce="test-nonce")

    assert served.count("data-mdfh-review-style") == 1
    assert '<script data-mdfh-review-script nonce="test-nonce">' in served
    assert "data-mdfh-review-unplaced" in served
    assert "data-mdfh-review-comment-input" in served
    assert "X-MDFH-Review-Token" in served
    assert 'request("/state")' in served
    assert 'request("/annotations"' in served
    assert "data-mdfh-source-lines" in served
    assert "annotation.source_range" in served
    assert "source_range = { start_line: 0, end_line: 0 }" in served
    assert "isGlobalAnnotation" in served
    assert "data-mdfh-review-rail" not in served
    assert "data-mdfh-review-connector-layer" not in served
    assert "suggest_insert" not in served
    assert "Reviewer name" not in served
