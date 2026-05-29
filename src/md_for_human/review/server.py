from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Callable, TextIO
from urllib.parse import unquote, urlsplit

from md_for_human.review import SCHEMA_VERSION
from md_for_human.builder import build_site_preserving_review
from md_for_human.review.client_assets import inject_review_client
from md_for_human.review.constants import LOCAL_REVIEW_HOST, REVIEW_API_PREFIX, TOKEN_HEADER
from md_for_human.review.artifacts import (
    annotations_path,
    empty_artifact,
    stale_annotations_path,
    write_json_atomic,
)
from md_for_human.review.locators import add_locator_metadata
from md_for_human.review.source_watch import snapshot_source_tree, stale_annotation_reason
from md_for_human.review.summary import write_review_summary
from md_for_human.review.validate import (
    ReviewValidationResult,
    is_safe_relative_posix_path,
    load_json_file,
    parse_manifest_documents,
    validate_review,
    validate_review_artifact,
)

class ReviewServerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        errors: list[str] | None = None,
        status: HTTPStatus = HTTPStatus.BAD_REQUEST,
    ) -> None:
        super().__init__(message)
        self.errors = errors or [message]
        self.status = status


class ReviewAuthError(ReviewServerError):
    def __init__(self) -> None:
        super().__init__(
            "review token is missing or invalid",
            status=HTTPStatus.UNAUTHORIZED,
        )


class ReviewServerApp:
    def __init__(
        self,
        output_dir: Path,
        *,
        token: str,
        source_input: Path | None = None,
        rebuild_site: Callable[[Path, Path], object] = build_site_preserving_review,
        source_poll_interval: float = 1.0,
        rebuild_debounce: float = 0.5,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.token = token
        self.source_input = Path(source_input) if source_input is not None else None
        self._rebuild_site = rebuild_site
        self._source_poll_interval = source_poll_interval
        self._rebuild_debounce = rebuild_debounce
        self._last_source_poll = 0.0
        self._last_source_snapshot = (
            snapshot_source_tree(self.source_input) if self.source_input is not None else {}
        )
        self._pending_source_snapshot: dict[str, tuple[int, int]] | None = None
        self._pending_since = 0.0
        self._build_version = 0
        self._build_error: str | None = None
        self.manifest_path = self.output_dir / ".md-for-human" / "manifest.json"
        if not self.manifest_path.exists():
            raise ReviewServerError(f"manifest.json is missing in {self.output_dir}")
        self._ensure_artifact()

    def get_state(self, *, token: str) -> dict[str, Any]:
        self._require_token(token)
        self._maybe_rebuild()
        artifact = self._ensure_artifact()
        validation = validate_review(self.output_dir)
        manifest_errors: list[str] = []
        manifest = load_json_file(self.manifest_path, manifest_errors)
        if manifest is None:
            manifest = {}
        return {
            "api_prefix": REVIEW_API_PREFIX,
            "artifact": artifact,
            "build": self._build_payload(),
            "manifest": manifest,
            "validation": validation_payload(validation),
        }

    def save_annotations(self, *, token: str, artifact: dict[str, Any]) -> dict[str, Any]:
        self._require_token(token)
        if artifact.get("schema_version") != SCHEMA_VERSION:
            raise ReviewServerError(
                "review server writes only mdfh-review-v2 artifacts",
                errors=["annotations.json: browser review writes only mdfh-review-v2"],
            )
        result = validate_review_artifact(self.output_dir, artifact, write_summary=False)
        if result.errors:
            raise ReviewServerError(
                "review artifact has hard validation errors",
                errors=result.errors,
            )
        writable_artifact = add_locator_metadata(self.output_dir, artifact)
        write_json_atomic(annotations_path(self.output_dir), writable_artifact)
        summary_path = write_review_summary(self.output_dir, writable_artifact)
        validation = browser_save_validation_payload(result)
        validation["summary_path"] = str(summary_path)
        return {
            "artifact": writable_artifact,
            "validation": validation,
        }

    def validate(self, *, token: str) -> dict[str, Any]:
        self._require_token(token)
        self._maybe_rebuild()
        self._ensure_artifact()
        return {"validation": validation_payload(validate_review(self.output_dir))}

    def render_site_file(self, relative_url_path: str, *, nonce: str) -> str:
        self._maybe_rebuild()
        relative_path = self._site_path_from_url(relative_url_path)
        path = self._resolve_site_path(relative_path)
        if path.suffix.lower() != ".html":
            raise ReviewServerError(f"not an HTML page: {relative_path.as_posix()}")
        html = path.read_text(encoding="utf-8")
        return inject_review_client(html, self.token, nonce=nonce)

    def read_static_file(self, relative_url_path: str) -> tuple[bytes, str]:
        self._maybe_rebuild()
        relative_path = self._site_path_from_url(relative_url_path)
        path = self._resolve_site_path(relative_path)
        return path.read_bytes(), content_type_for_path(path)

    def entry_page(self) -> str:
        errors: list[str] = []
        manifest = load_json_file(self.manifest_path, errors)
        if not isinstance(manifest, dict):
            raise ReviewServerError("manifest.json is invalid", errors=errors)
        entry_page = manifest.get("entry_page")
        if not isinstance(entry_page, str) or not entry_page:
            raise ReviewServerError("manifest.json entry_page is missing or invalid")
        if not is_safe_relative_posix_path(entry_page):
            raise ReviewServerError(f'manifest entry_page "{entry_page}" is unsafe')
        return entry_page

    def _ensure_artifact(self) -> dict[str, Any]:
        path = annotations_path(self.output_dir)
        if not path.exists():
            artifact = empty_artifact()
            write_json_atomic(path, artifact)
            return artifact
        errors: list[str] = []
        loaded_artifact = load_json_file(path, errors)
        if not isinstance(loaded_artifact, dict):
            raise ReviewServerError("annotations.json is invalid", errors=errors)
        active_artifact = self._quarantine_stale_annotations(loaded_artifact)
        return self._refresh_locator_metadata(active_artifact)

    def _quarantine_stale_annotations(self, artifact: dict[str, Any]) -> dict[str, Any]:
        if artifact.get("schema_version") != SCHEMA_VERSION:
            return artifact
        annotations = artifact.get("annotations")
        if not isinstance(annotations, list):
            return artifact

        manifest_errors: list[str] = []
        manifest = load_json_file(self.manifest_path, manifest_errors)
        documents = parse_manifest_documents(manifest, manifest_errors)
        if manifest_errors:
            return artifact

        active_annotations: list[Any] = []
        stale_annotations: list[dict[str, Any]] = []
        for annotation in annotations:
            if not isinstance(annotation, dict):
                active_annotations.append(annotation)
                continue
            stale_reason = stale_annotation_reason(annotation, documents)
            if stale_reason is None:
                active_annotations.append(annotation)
                continue
            stale_item = dict(annotation)
            stale_item["stale_reason"] = stale_reason
            stale_annotations.append(stale_item)

        if not stale_annotations:
            return artifact

        cleaned_artifact = dict(artifact)
        cleaned_artifact["annotations"] = active_annotations
        write_json_atomic(annotations_path(self.output_dir), cleaned_artifact)
        self._append_stale_annotations(stale_annotations)
        return cleaned_artifact

    def _append_stale_annotations(self, stale_annotations: list[dict[str, Any]]) -> None:
        path = stale_annotations_path(self.output_dir)
        existing_errors: list[str] = []
        existing = load_json_file(path, existing_errors) if path.exists() else None
        if isinstance(existing, dict) and isinstance(existing.get("annotations"), list):
            combined = dict(existing)
            combined_annotations = [
                item for item in existing["annotations"] if isinstance(item, dict)
            ]
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
        for annotation in stale_annotations:
            annotation_id = annotation.get("id")
            if isinstance(annotation_id, str) and annotation_id in seen_ids:
                continue
            combined_annotations.append(annotation)
            if isinstance(annotation_id, str):
                seen_ids.add(annotation_id)
        combined["annotations"] = combined_annotations
        write_json_atomic(path, combined)

    def _refresh_locator_metadata(self, artifact: dict[str, Any]) -> dict[str, Any]:
        if artifact.get("schema_version") != SCHEMA_VERSION:
            return artifact
        refreshed_artifact = add_locator_metadata(self.output_dir, artifact)
        if refreshed_artifact != artifact:
            write_json_atomic(annotations_path(self.output_dir), refreshed_artifact)
        return refreshed_artifact

    def _site_path_from_url(self, relative_url_path: str) -> PurePosixPath:
        raw_path = unquote(urlsplit(relative_url_path).path).lstrip("/")
        if raw_path.startswith(REVIEW_API_PREFIX.lstrip("/")):
            raise ReviewServerError("review API path is not a static file")
        if raw_path == "":
            raw_path = self.entry_page()
        if not is_safe_relative_posix_path(raw_path):
            raise ReviewServerError(f'static path "{raw_path}" is unsafe')
        return PurePosixPath(raw_path)

    def _resolve_site_path(self, relative_path: PurePosixPath) -> Path:
        root = self.output_dir.resolve()
        path = (self.output_dir / relative_path).resolve()
        if path != root and root not in path.parents:
            raise ReviewServerError(f'static path "{relative_path.as_posix()}" escapes output')
        if not path.exists() or not path.is_file():
            raise ReviewServerError(
                f'static path "{relative_path.as_posix()}" does not exist',
                status=HTTPStatus.NOT_FOUND,
            )
        return path

    def _require_token(self, token: str) -> None:
        if not token or not secrets.compare_digest(token, self.token):
            raise ReviewAuthError()

    def _build_payload(self) -> dict[str, Any]:
        return {
            "watching": self.source_input is not None,
            "version": self._build_version,
            "error": self._build_error,
            "entry_page": self.entry_page(),
        }

    def _maybe_rebuild(self) -> None:
        if self.source_input is None:
            return
        now = time.monotonic()
        if now - self._last_source_poll < self._source_poll_interval:
            return
        self._last_source_poll = now
        current_snapshot = snapshot_source_tree(self.source_input)
        if current_snapshot == self._last_source_snapshot:
            self._pending_source_snapshot = None
            self._pending_since = 0.0
            return
        if current_snapshot != self._pending_source_snapshot:
            self._pending_source_snapshot = current_snapshot
            self._pending_since = now
            if self._rebuild_debounce > 0:
                return
        if now - self._pending_since < self._rebuild_debounce:
            return
        try:
            self._rebuild_site(self.source_input, self.output_dir)
        except Exception as exc:
            self._build_error = str(exc)
            self._last_source_snapshot = current_snapshot
            self._pending_source_snapshot = None
            return
        self._build_version += 1
        self._build_error = None
        self._last_source_snapshot = current_snapshot
        self._pending_source_snapshot = None
        self.manifest_path = self.output_dir / ".md-for-human" / "manifest.json"
        self._ensure_artifact()


def validation_payload(result: ReviewValidationResult) -> dict[str, Any]:
    return {
        "passed": result.passed,
        "errors": result.errors,
        "warnings": result.warnings,
        "annotation_count": result.annotation_count,
        "pages_touched": result.pages_touched,
        "summary_path": str(result.summary_path) if result.summary_path is not None else None,
    }


def browser_save_validation_payload(result: ReviewValidationResult) -> dict[str, Any]:
    payload = validation_payload(result)
    payload["warnings"] = []
    return payload


def content_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".css":
        return "text/css; charset=utf-8"
    if suffix == ".js":
        return "application/javascript; charset=utf-8"
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


def review_content_security_policy(nonce: str) -> str:
    return "; ".join(
        [
            "default-src 'none'",
            f"script-src 'nonce-{nonce}'",
            f"style-src 'nonce-{nonce}'",
            "img-src 'self' data: blob: http: https:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
            "frame-ancestors 'none'",
        ]
    )


def make_review_handler(app: ReviewServerApp) -> type[BaseHTTPRequestHandler]:
    class ReviewRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if urlsplit(self.path).path == "/favicon.ico":
                self._send_bytes(b"", "image/x-icon", status=HTTPStatus.NO_CONTENT)
                return
            if self.path == f"{REVIEW_API_PREFIX}/state":
                self._handle_json(lambda: app.get_state(token=self._token()))
                return
            self._handle_static()

        def do_POST(self) -> None:
            if self.path == f"{REVIEW_API_PREFIX}/validate":
                self._handle_json(lambda: app.validate(token=self._token()))
                return
            self._send_json(
                {"error": "not found"},
                status=HTTPStatus.NOT_FOUND,
            )

        def do_PUT(self) -> None:
            if self.path == f"{REVIEW_API_PREFIX}/annotations":
                self._handle_json(
                    lambda: app.save_annotations(
                        token=self._token(),
                        artifact=self._read_json_body(),
                    )
                )
                return
            self._send_json(
                {"error": "not found"},
                status=HTTPStatus.NOT_FOUND,
            )

        def _handle_static(self) -> None:
            try:
                if urlsplit(self.path).path.lower().endswith(".html") or self.path in {"", "/"}:
                    nonce = secrets.token_urlsafe(16)
                    body = app.render_site_file(self.path, nonce=nonce).encode("utf-8")
                    self._send_bytes(
                        body,
                        "text/html; charset=utf-8",
                        content_security_policy=review_content_security_policy(nonce),
                    )
                    return
                body, content_type = app.read_static_file(self.path)
                self._send_bytes(body, content_type)
            except ReviewServerError as exc:
                self._send_json({"error": str(exc), "errors": exc.errors}, status=exc.status)
            except OSError as exc:
                self._send_json(
                    {"error": f"could not read static file: {exc}"},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def _handle_json(self, callback: Callable[[], dict[str, Any]]) -> None:
            try:
                self._send_json(callback())
            except ReviewServerError as exc:
                self._send_json({"error": str(exc), "errors": exc.errors}, status=exc.status)
            except json.JSONDecodeError as exc:
                self._send_json(
                    {"error": f"invalid JSON: {exc.msg}", "errors": [exc.msg]},
                    status=HTTPStatus.BAD_REQUEST,
                )

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            value = json.loads(body.decode("utf-8"))
            if not isinstance(value, dict):
                raise ReviewServerError("request JSON body must be an object")
            return value

        def _token(self) -> str:
            return self.headers.get(TOKEN_HEADER, "")

        def _send_json(
            self,
            payload: dict[str, Any],
            *,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8", status=status)

        def _send_bytes(
            self,
            body: bytes,
            content_type: str,
            *,
            status: HTTPStatus = HTTPStatus.OK,
            content_security_policy: str | None = None,
        ) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if content_security_policy is not None:
                self.send_header("Content-Security-Policy", content_security_policy)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return ReviewRequestHandler


def serve_review(
    output_dir: Path,
    *,
    source_input: Path | None = None,
    host: str = LOCAL_REVIEW_HOST,
    port: int = 0,
    opener: Callable[[str], object] = webbrowser.open,
    stdout: TextIO | None = None,
) -> int:
    stdout = stdout or None
    token = secrets.token_urlsafe(24)
    app = ReviewServerApp(output_dir, token=token, source_input=source_input)
    handler = make_review_handler(app)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{server.server_port}/"
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    if stdout is not None:
        print(f"Review server: {url}", file=stdout, flush=True)
        print("Press Ctrl-C to stop.", file=stdout, flush=True)
    opener(url)
    try:
        while server_thread.is_alive():
            server_thread.join(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
    return 0
