from __future__ import annotations

import json
import secrets
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Callable, TextIO
from urllib.parse import unquote, urlsplit

from md_for_human.review import SCHEMA_VERSION
from md_for_human.builder import build_site_preserving_review
from md_for_human.review.artifacts import (
    annotations_path,
    empty_artifact,
    write_json_atomic,
)
from md_for_human.review.summary import write_review_summary
from md_for_human.review.validate import (
    ReviewValidationResult,
    is_safe_relative_posix_path,
    load_json_file,
    validate_review,
    validate_review_artifact,
)

REVIEW_API_PREFIX = "/__mdfh_review"
TOKEN_HEADER = "X-MDFH-Review-Token"
LOCAL_REVIEW_HOST = "127.0.0.1"


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
        write_json_atomic(annotations_path(self.output_dir), artifact)
        summary_path = write_review_summary(self.output_dir, artifact)
        validation = validation_payload(result)
        validation["summary_path"] = str(summary_path)
        return {
            "artifact": artifact,
            "validation": validation,
        }

    def validate(self, *, token: str) -> dict[str, Any]:
        self._require_token(token)
        self._maybe_rebuild()
        self._ensure_artifact()
        return {"validation": validation_payload(validate_review(self.output_dir))}

    def render_site_file(self, relative_url_path: str) -> str:
        self._maybe_rebuild()
        relative_path = self._site_path_from_url(relative_url_path)
        path = self._resolve_site_path(relative_path)
        if path.suffix.lower() != ".html":
            raise ReviewServerError(f"not an HTML page: {relative_path.as_posix()}")
        html = path.read_text(encoding="utf-8")
        return inject_review_client(html, self.token)

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
        return loaded_artifact

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


def snapshot_source_tree(source_input: Path) -> dict[str, tuple[int, int]]:
    source_input = Path(source_input)
    if source_input.is_file() or source_input.is_symlink():
        return {source_input.name: stat_signature(source_input)}
    if not source_input.exists():
        return {}
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sorted(source_input.rglob("*")):
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(source_input).as_posix()
        snapshot[relative] = stat_signature(path)
    return snapshot


def stat_signature(path: Path) -> tuple[int, int]:
    stat_result = path.lstat()
    return stat_result.st_mtime_ns, stat_result.st_size


def validation_payload(result: ReviewValidationResult) -> dict[str, Any]:
    return {
        "passed": result.passed,
        "errors": result.errors,
        "warnings": result.warnings,
        "annotation_count": result.annotation_count,
        "pages_touched": result.pages_touched,
        "summary_path": str(result.summary_path) if result.summary_path is not None else None,
    }


def inject_review_client(html: str, token: str) -> str:
    markup = review_client_markup(token)
    if "</body>" in html:
        return html.replace("</body>", f"{markup}\n</body>", 1)
    return html + markup


def review_client_markup(token: str) -> str:
    script = REVIEW_CLIENT_JS.replace("__MDFH_TOKEN__", json.dumps(token)).replace(
        "__MDFH_API_PREFIX__",
        json.dumps(REVIEW_API_PREFIX),
    )
    return f"{REVIEW_CLIENT_STYLE}\n{REVIEW_CLIENT_PANEL}\n<script>{script}</script>"


REVIEW_CLIENT_STYLE = """
<style data-mdfh-review-style>
.mdfh-review-open {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  z-index: 50;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0.55rem 0.8rem;
  background: var(--panel-strong);
  color: var(--text);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.24);
  cursor: pointer;
  font: 0.9rem "Avenir Next", "Helvetica Neue", sans-serif;
}

.mdfh-review-open:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.mdfh-review-content {
  --mdfh-review-gap: clamp(1rem, 2.2vw, 1.5rem);
  --mdfh-review-comment-width: minmax(15rem, 21rem);
}

.mdfh-review-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--mdfh-review-comment-width);
  column-gap: var(--mdfh-review-gap);
  align-items: start;
  min-width: 0;
}

.mdfh-review-body,
.mdfh-review-comments {
  min-width: 0;
}

.mdfh-review-body {
  grid-column: 1;
}

.mdfh-review-comments {
  grid-column: 2;
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
}

.mdfh-review-card,
.mdfh-review-editor,
.mdfh-review-unplaced {
  border: 1px solid rgba(250, 204, 21, 0.42);
  border-left: 3px solid #facc15;
  border-radius: 0.65rem;
  background: rgba(250, 204, 21, 0.12);
  color: var(--text);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
  font-size: 0.9rem;
  line-height: 1.45;
}

.mdfh-review-card,
.mdfh-review-editor {
  padding: 0.7rem 0.75rem;
}

.mdfh-review-card {
  cursor: pointer;
}

.mdfh-review-card:hover,
.mdfh-review-card.is-active {
  border-color: #fde68a;
  background: rgba(250, 204, 21, 0.17);
}

.mdfh-review-card p,
.mdfh-review-unplaced p {
  margin: 0;
}

.mdfh-review-card small,
.mdfh-review-editor small,
.mdfh-review-unplaced small {
  display: block;
  margin-top: 0.35rem;
  color: var(--muted);
  line-height: 1.35;
}

.mdfh-review-card-actions,
.mdfh-review-editor-actions {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin-top: 0.6rem;
}

.mdfh-review-card button,
.mdfh-review-editor button,
.mdfh-review-unplaced button {
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  padding: 0.42rem 0.58rem;
  background: var(--panel-strong);
  color: var(--text);
  cursor: pointer;
  font: inherit;
}

.mdfh-review-card button:hover,
.mdfh-review-editor button:hover,
.mdfh-review-unplaced button:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.mdfh-review-comment-input {
  width: 100%;
  min-height: 6.25rem;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  padding: 0.7rem;
  background: var(--bg);
  color: var(--text);
  resize: vertical;
  font: inherit;
}

.mdfh-review-anchor {
  max-height: 5rem;
  overflow: auto;
  margin-bottom: 0.55rem;
  border-left: 2px solid #facc15;
  padding-left: 0.55rem;
  color: var(--muted);
  font-size: 0.84rem;
  line-height: 1.4;
  white-space: pre-wrap;
}

.mdfh-review-unplaced {
  margin-bottom: 1rem;
  padding: 0.8rem;
}

.mdfh-review-unplaced[hidden] {
  display: none !important;
}

.mdfh-review-unplaced-list {
  display: grid;
  gap: 0.55rem;
  margin-top: 0.55rem;
}

.mdfh-review-unplaced-item {
  display: grid;
  gap: 0.35rem;
  border-top: 1px dashed rgba(250, 204, 21, 0.32);
  padding-top: 0.55rem;
}

.mdfh-review-toast {
  position: fixed;
  right: 1rem;
  bottom: 4.1rem;
  z-index: 52;
  max-width: min(24rem, calc(100vw - 2rem));
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  padding: 0.6rem 0.7rem;
  color: var(--text);
  background: var(--panel-strong);
  font-size: 0.85rem;
  line-height: 1.4;
}

.mdfh-review-underline {
  border-bottom: 3px solid #facc15;
  background: rgba(250, 204, 21, 0.24);
  box-shadow: inset 0 -0.22em 0 rgba(250, 204, 21, 0.22);
  cursor: pointer;
}

.mdfh-review-pending {
  border-bottom-style: dashed;
}

.mdfh-review-flash {
  animation: mdfh-review-flash 1.5s ease-out;
  border-radius: 0.25rem;
}

@keyframes mdfh-review-flash {
  0% {
    outline: 3px solid rgba(250, 204, 21, 0.95);
    background: rgba(250, 204, 21, 0.24);
  }
  100% {
    outline: 0 solid rgba(250, 204, 21, 0);
    background: transparent;
  }
}

@media (max-width: 960px) {
  .mdfh-review-row {
    grid-template-columns: minmax(0, 1fr);
    row-gap: 0.5rem;
  }

  .mdfh-review-comments {
    grid-column: 1;
  }

  .mdfh-review-card,
  .mdfh-review-editor {
    margin-top: 0.35rem !important;
  }
}
</style>
""".strip()

REVIEW_CLIENT_PANEL = """
<button type="button" class="mdfh-review-open" data-mdfh-review-open>Comment</button>
<div class="mdfh-review-unplaced" data-mdfh-review-unplaced hidden></div>
<div class="mdfh-review-toast" data-mdfh-review-toast role="status" hidden></div>
""".strip()

REVIEW_CLIENT_JS = r"""
(() => {
  const token = __MDFH_TOKEN__;
  const apiPrefix = __MDFH_API_PREFIX__;
  const content = document.querySelector("[data-mdfh-content='1']");
  if (!content) {
    return;
  }

  const article = content.closest("[data-doc-card]") || content.parentElement;
  const page = document.body.dataset.mdfhPage || "";
  const sourcePath = document.body.dataset.mdfhSourcePath || "";
  const els = {
    open: document.querySelector("[data-mdfh-review-open]"),
    toast: document.querySelector("[data-mdfh-review-toast]"),
    unplaced: document.querySelector("[data-mdfh-review-unplaced]"),
  };
  const state = {
    artifact: null,
    selectedQuote: "",
    editingId: "",
    documentMode: false,
    draftComment: "",
    pendingSpans: [],
    toastTimer: 0,
    buildVersion: null,
    anchorState: new Map(),
  };

  const nowIso = () => new Date().toISOString();
  const clone = (value) => JSON.parse(JSON.stringify(value));
  prepareReviewLayout();

  async function request(path, options = {}) {
    const headers = Object.assign(
      { [ "X-MDFH-Review-Token" ]: token },
      options.headers || {},
    );
    const response = await fetch(apiPrefix + path, Object.assign({}, options, { headers }));
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) {
      const message = (payload.errors || [payload.error || "Request failed"]).join("\n");
      throw new Error(message);
    }
    return payload;
  }

  function ensureV2Artifact(artifact) {
    if (artifact && artifact.schema_version === "mdfh-review-v2") {
      artifact.annotations = Array.isArray(artifact.annotations) ? artifact.annotations : [];
      return artifact;
    }
    return {
      schema_version: "mdfh-review-v2",
      source_manifest: ".md-for-human/manifest.json",
      annotations: [],
    };
  }

  function toast(message, validation = null) {
    window.clearTimeout(state.toastTimer);
    const lines = [];
    if (message) {
      lines.push(escapeHtml(message));
    }
    const hasErrors = Boolean(validation && validation.errors && validation.errors.length);
    const hasWarnings = Boolean(validation && validation.warnings && validation.warnings.length);
    if (validation && validation.errors && validation.errors.length) {
      lines.push(validation.errors.map((item) => `Error: ${escapeHtml(item)}`).join("<br>"));
    }
    if (validation && validation.warnings && validation.warnings.length) {
      lines.push(validation.warnings.map((item) => `Warning: ${escapeHtml(item)}`).join("<br>"));
    }
    els.toast.innerHTML = lines.join("<br>");
    els.toast.hidden = lines.length === 0;
    if (!hasErrors && !hasWarnings && message) {
      state.toastTimer = window.setTimeout(() => {
        els.toast.hidden = true;
      }, 1800);
    }
  }

  function currentAnnotations() {
    if (!state.artifact || !Array.isArray(state.artifact.annotations)) {
      return [];
    }
    return state.artifact.annotations;
  }

  function pageAnnotations() {
    return currentAnnotations().filter((annotation) => annotation.page === page);
  }

  function prepareReviewLayout() {
    if (!article || content.dataset.mdfhReviewPrepared === "1") {
      return;
    }
    const unplaced = els.unplaced || document.createElement("div");
    unplaced.className = "mdfh-review-unplaced";
    unplaced.dataset.mdfhReviewUnplaced = "1";
    unplaced.hidden = true;
    article.insertBefore(unplaced, content);
    els.unplaced = unplaced;

    content.classList.add("mdfh-review-content");
    Array.from(content.childNodes).forEach((node) => {
      if (node.nodeType === Node.TEXT_NODE && !node.nodeValue.trim()) {
        node.remove();
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE && node.nodeType !== Node.TEXT_NODE) {
        return;
      }
      const row = document.createElement("div");
      row.className = "mdfh-review-row";
      row.dataset.mdfhReviewRow = "1";
      const body = document.createElement("div");
      body.className = "mdfh-review-body";
      body.dataset.mdfhReviewBody = "1";
      const comments = document.createElement("div");
      comments.className = "mdfh-review-comments";
      comments.dataset.mdfhReviewComments = "1";
      row.append(body, comments);
      content.insertBefore(row, node);
      body.appendChild(node);
    });

    if (!content.querySelector("[data-mdfh-review-row]")) {
      const row = document.createElement("div");
      row.className = "mdfh-review-row";
      row.dataset.mdfhReviewRow = "1";
      row.innerHTML = '<div class="mdfh-review-body" data-mdfh-review-body="1"></div><div class="mdfh-review-comments" data-mdfh-review-comments="1"></div>';
      content.appendChild(row);
    }
    content.dataset.mdfhReviewPrepared = "1";
  }

  function resetDraft() {
    clearPendingSpans();
    state.selectedQuote = "";
    state.editingId = "";
    state.documentMode = false;
    state.draftComment = "";
  }

  function startDocumentComment() {
    resetDraft();
    state.documentMode = true;
    renderAnnotations();
    focusEditor();
  }

  function setTargetFromQuote(quote) {
    state.selectedQuote = quote.trim();
    state.editingId = "";
    state.documentMode = false;
    state.draftComment = "";
    renderAnnotations();
    focusEditor();
  }

  function focusEditor() {
    window.requestAnimationFrame(() => {
      const editor = content.querySelector("[data-mdfh-review-comment-input]");
      if (editor) {
        editor.focus();
      }
    });
  }

  function currentEditorValue() {
    const editor = content.querySelector("[data-mdfh-review-comment-input]");
    return editor ? editor.value.trim() : "";
  }

  function captureSelection() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      return;
    }
    const range = selection.getRangeAt(0);
    if (!isRangeInsideReviewBody(range)) {
      return;
    }
    const selectedText = selection.toString().trim();
    if (!selectedText) {
      return;
    }
    clearPendingSpans();
    markPendingRange(range);
    setTargetFromQuote(selectedText);
  }

  function isRangeInsideReviewBody(range) {
    const start = elementForNode(range.startContainer);
    const end = elementForNode(range.endContainer);
    return Boolean(
      start &&
      end &&
      start.closest("[data-mdfh-review-body]") &&
      end.closest("[data-mdfh-review-body]"),
    );
  }

  function markPendingRange(range) {
    const segments = segmentsForRange(range);
    state.pendingSpans = wrapSegments(segments, { pending: true });
    window.getSelection()?.removeAllRanges();
  }

  function segmentsForRange(range) {
    const segments = [];
    textRoots().forEach((root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        if (range.intersectsNode(node)) {
          let start = 0;
          let end = node.nodeValue ? node.nodeValue.length : 0;
          if (node === range.startContainer) {
            start = range.startOffset;
          }
          if (node === range.endContainer) {
            end = range.endOffset;
          }
          if (end > start) {
            segments.push({ node, start, end });
          }
        }
        node = walker.nextNode();
      }
    });
    return segments;
  }

  function clearPendingSpans() {
    state.pendingSpans.forEach((span) => unwrapSpan(span));
    state.pendingSpans = [];
  }

  function unwrapSpan(span) {
    if (!span || !span.parentNode) {
      return;
    }
    const parent = span.parentNode;
    while (span.firstChild) {
      parent.insertBefore(span.firstChild, span);
    }
    parent.removeChild(span);
    parent.normalize();
  }

  async function saveCurrent() {
    if (!state.artifact) {
      toast("Still loading comments.");
      return;
    }
    const comment = currentEditorValue();
    if (!comment) {
      toast("Write a comment before saving.");
      return;
    }
    const artifact = clone(state.artifact);
    artifact.schema_version = "mdfh-review-v2";
    artifact.source_manifest = ".md-for-human/manifest.json";
    const annotations = Array.isArray(artifact.annotations) ? artifact.annotations : [];
    const existing = annotations.find((annotation) => annotation.id === state.editingId);
    const timestamp = nowIso();
    const annotation = {
      id: state.editingId || `ann_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      page,
      source_path: sourcePath,
      comment,
      created_at: existing ? existing.created_at : timestamp,
      updated_at: timestamp,
      ui_marker: "underline",
    };
    if (state.selectedQuote.trim() && !state.documentMode) {
      annotation.quote = state.selectedQuote.trim();
    } else {
      annotation.scope = "document";
    }
    artifact.annotations = annotations
      .filter((item) => item.id !== annotation.id)
      .concat(annotation);
    if (await saveArtifact(artifact, "Saved.")) {
      resetDraft();
      renderAnnotations();
    }
  }

  async function saveArtifact(artifact, message) {
    try {
      const payload = await request("/annotations", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(artifact),
      });
      state.artifact = ensureV2Artifact(payload.artifact);
      clearPendingSpans();
      renderAnnotations();
      toast(message, payload.validation);
      return true;
    } catch (error) {
      toast(error.message);
      return false;
    }
  }

  async function deleteCurrent() {
    if (!state.editingId || !state.artifact) {
      return;
    }
    const artifact = clone(state.artifact);
    artifact.annotations = currentAnnotations().filter((item) => item.id !== state.editingId);
    if (await saveArtifact(artifact, "Deleted.")) {
      resetDraft();
      renderAnnotations();
    }
  }

  function renderAnnotations() {
    unwrapSavedMarkers();
    clearCommentColumns();
    state.anchorState = new Map();
    const annotations = pageAnnotations();
    annotations
      .filter((annotation) => annotation.quote)
      .forEach((annotation) => markSavedQuote(annotation));
    renderInlineComments(annotations);
    renderUnplacedComments(annotations);
  }

  function clearCommentColumns() {
    content.querySelectorAll("[data-mdfh-review-comments]").forEach((comments) => {
      comments.innerHTML = "";
    });
  }

  function renderInlineComments(annotations) {
    const itemsByRow = new Map();
    annotations.forEach((annotation) => {
      if (annotation.id === state.editingId) {
        return;
      }
      const row = rowForAnnotation(annotation);
      if (!row) {
        return;
      }
      const status = state.anchorState.get(annotation.id);
      if (status && status.warning) {
        return;
      }
      addRowItem(itemsByRow, row, {
        kind: "card",
        annotation,
        offset: offsetForAnnotation(annotation, row),
      });
    });
    const editorPlacement = currentEditorTarget();
    if (editorPlacement) {
      addRowItem(itemsByRow, editorPlacement.row, {
        kind: "editor",
        offset: editorPlacement.offset,
      });
    }
    renderRowItems(itemsByRow);
  }

  function addRowItem(itemsByRow, row, item) {
    if (!itemsByRow.has(row)) {
      itemsByRow.set(row, []);
    }
    itemsByRow.get(row).push(item);
  }

  function renderRowItems(itemsByRow) {
    itemsByRow.forEach((items, row) => {
      const comments = row.querySelector("[data-mdfh-review-comments]");
      if (!comments) {
        return;
      }
      let bottom = 0;
      items
        .slice()
        .sort((left, right) => left.offset - right.offset)
        .forEach((item) => {
          const element = item.kind === "editor" ? createEditor() : createCommentCard(item.annotation);
          const marginTop = Math.max(0, item.offset - bottom);
          element.style.marginTop = `${marginTop}px`;
          comments.appendChild(element);
          bottom += marginTop + element.offsetHeight + 8;
        });
    });
  }

  function createCommentCard(annotation) {
    const card = document.createElement("article");
    card.className = "mdfh-review-card";
    card.dataset.mdfhReviewCard = annotation.id;
    card.tabIndex = 0;
    card.innerHTML = `
      <p>${escapeHtml(annotation.comment)}</p>
      <small>${escapeHtml(annotation.quote || "Document comment")}</small>
      <div class="mdfh-review-card-actions">
        <button type="button" data-mdfh-review-edit="${escapeAttr(annotation.id)}">Edit</button>
      </div>
    `;
    return card;
  }

  function createEditor() {
    const existing = state.editingId
      ? currentAnnotations().find((annotation) => annotation.id === state.editingId)
      : null;
    const value = state.draftComment || "";
    const anchor = state.documentMode ? "Document comment" : state.selectedQuote;
    const editor = document.createElement("form");
    editor.className = "mdfh-review-editor";
    editor.dataset.mdfhReviewEditor = "1";
    editor.innerHTML = `
      <div class="mdfh-review-anchor">${escapeHtml(anchor || "Document comment")}</div>
      <textarea class="mdfh-review-comment-input" data-mdfh-review-comment-input
        placeholder="Write the requested change and why it matters.">${escapeHtml(value)}</textarea>
      <div class="mdfh-review-editor-actions">
        <button type="submit" data-mdfh-review-save>Save</button>
        ${state.editingId ? '<button type="button" data-mdfh-review-delete>Delete</button>' : ""}
        <button type="button" data-mdfh-review-cancel>Cancel</button>
      </div>
    `;
    return editor;
  }

  function renderUnplacedComments(annotations) {
    if (!els.unplaced) {
      return;
    }
    const unplaced = annotations.filter((annotation) => {
      const status = state.anchorState.get(annotation.id);
      return annotation.quote && status && status.warning;
    });
    if (unplaced.length === 0) {
      els.unplaced.hidden = true;
      els.unplaced.innerHTML = "";
      return;
    }
    els.unplaced.hidden = false;
    els.unplaced.innerHTML = `
      <p><strong>Unplaced comments</strong></p>
      <small>These comments belong to this page, but their quote cannot be placed uniquely.</small>
      <div class="mdfh-review-unplaced-list">
        ${unplaced.map((annotation) => {
          const status = state.anchorState.get(annotation.id);
          return `
            <div class="mdfh-review-unplaced-item">
              <p>${escapeHtml(annotation.comment)}</p>
              <small>${escapeHtml(status.warning)} ${escapeHtml(annotation.quote || "")}</small>
              <div class="mdfh-review-card-actions">
                <button type="button" data-mdfh-review-edit="${escapeAttr(annotation.id)}">Edit</button>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  function markSavedQuote(annotation) {
    const ranges = findQuoteRanges(annotation.quote);
    if (ranges.length !== 1) {
      state.anchorState.set(annotation.id, {
        warning: ranges.length === 0 ? "Quote not found on this page." : "Quote appears more than once.",
      });
      return;
    }
    wrapSegments(ranges[0].segments, { annotationId: annotation.id });
    state.anchorState.set(annotation.id, {});
  }

  function unwrapSavedMarkers() {
    content.querySelectorAll(".mdfh-review-underline:not(.mdfh-review-pending)").forEach((span) => {
      const parent = span.parentNode;
      while (span.firstChild) {
        parent.insertBefore(span.firstChild, span);
      }
      parent.removeChild(span);
      parent.normalize();
    });
  }

  function textRoots() {
    return Array.from(content.querySelectorAll("[data-mdfh-review-body]"));
  }

  function findQuoteRanges(quote) {
    const parts = [];
    let text = "";
    textRoots().forEach((root, rootIndex) => {
      if (rootIndex > 0) {
        text += "\n";
      }
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        const value = node.nodeValue || "";
        parts.push({ node, start: text.length, end: text.length + value.length });
        text += value;
        node = walker.nextNode();
      }
    });
    const ranges = [];
    let index = 0;
    while (quote && true) {
      index = text.indexOf(quote, index);
      if (index === -1) {
        break;
      }
      const end = index + quote.length;
      const segments = parts
        .filter((part) => part.end > index && part.start < end)
        .map((part) => ({
          node: part.node,
          start: Math.max(0, index - part.start),
          end: Math.min(part.end - part.start, end - part.start),
        }))
        .filter((segment) => segment.end > segment.start);
      ranges.push({ start: index, end, segments });
      index = end;
    }
    return ranges;
  }

  function wrapSegments(segments, { annotationId = "", pending = false } = {}) {
    const spans = [];
    segments.slice().reverse().forEach((segment) => {
      const textNode = segment.node;
      const parent = textNode.parentNode;
      if (!parent) {
        return;
      }
      const after = textNode.splitText(segment.end);
      const middle = textNode.splitText(segment.start);
      const span = document.createElement("span");
      span.className = pending
        ? "mdfh-review-underline mdfh-review-pending"
        : "mdfh-review-underline";
      if (annotationId) {
        span.dataset.mdfhReviewAnchorId = annotationId;
      }
      parent.insertBefore(span, after);
      span.appendChild(middle);
      spans.unshift(span);
    });
    return spans;
  }

  function rowForAnnotation(annotation) {
    if (annotation.scope === "document") {
      return firstReviewRow();
    }
    const marker = firstMarkerForAnnotation(annotation.id);
    return marker ? marker.closest("[data-mdfh-review-row]") : null;
  }

  function currentEditorTarget() {
    if (!state.editingId && !state.selectedQuote && !state.documentMode) {
      return null;
    }
    if (state.documentMode) {
      return { row: firstReviewRow(), offset: 0 };
    }
    const pending = state.pendingSpans.find(Boolean);
    if (pending) {
      const row = pending.closest("[data-mdfh-review-row]");
      return row ? { row, offset: offsetForMarker(pending, row) } : null;
    }
    if (state.editingId) {
      const annotation = currentAnnotations().find((item) => item.id === state.editingId);
      if (annotation && annotation.scope === "document") {
        return { row: firstReviewRow(), offset: 0 };
      }
      const marker = firstMarkerForAnnotation(state.editingId);
      const row = marker ? marker.closest("[data-mdfh-review-row]") : firstReviewRow();
      return row ? { row, offset: marker ? offsetForMarker(marker, row) : 0 } : null;
    }
    return null;
  }

  function firstReviewRow() {
    return content.querySelector("[data-mdfh-review-row]");
  }

  function firstMarkerForAnnotation(annotationId) {
    return content.querySelector(`[data-mdfh-review-anchor-id="${cssEscape(annotationId)}"]`);
  }

  function offsetForAnnotation(annotation, row) {
    if (annotation.scope === "document") {
      return 0;
    }
    const marker = firstMarkerForAnnotation(annotation.id);
    return marker ? offsetForMarker(marker, row) : 0;
  }

  function offsetForMarker(marker, row) {
    return Math.max(0, marker.getBoundingClientRect().top - row.getBoundingClientRect().top);
  }

  function editAnnotation(annotation) {
    if (annotation.page !== page) {
      window.location.href = `/${annotation.page}`;
      return;
    }
    state.editingId = annotation.id;
    state.selectedQuote = annotation.quote || "";
    state.documentMode = annotation.scope === "document";
    state.draftComment = annotation.comment || "";
    clearPendingSpans();
    renderAnnotations();
    if (annotation.quote) {
      locateQuote(annotation.quote);
    }
    focusEditor();
  }

  function locateQuote(quote) {
    const ranges = findQuoteRanges(quote);
    if (ranges.length !== 1) {
      toast(ranges.length === 0 ? "Quote was not found on this page." : "Quote appears more than once.");
      return;
    }
    let target = firstMarkerForAnnotation(state.editingId);
    if (!target && window.find && window.find(quote)) {
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
        const node = selection.getRangeAt(0).startContainer;
        target = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
        selection.removeAllRanges();
      }
    }
    if (!target || !content.contains(target)) {
      toast("Quote location could not be resolved.");
      return;
    }
    const block = target.closest("p, li, blockquote, pre, h1, h2, h3, h4, h5, h6") || target;
    block.scrollIntoView({ behavior: "smooth", block: "center" });
    block.classList.add("mdfh-review-flash");
    setTimeout(() => block.classList.remove("mdfh-review-flash"), 1600);
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, "&#96;");
  }

  function cssEscape(value) {
    if (window.CSS && window.CSS.escape) {
      return window.CSS.escape(value || "");
    }
    return String(value || "").replace(/"/g, '\\"');
  }

  function elementForNode(node) {
    if (!node) {
      return null;
    }
    return node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  }

  function activateCard(annotationId) {
    content.querySelectorAll("[data-mdfh-review-card]").forEach((card) => {
      card.classList.toggle("is-active", card.dataset.mdfhReviewCard === annotationId);
    });
  }

  function focusCard(annotationId) {
    const card = content.querySelector(`[data-mdfh-review-card="${cssEscape(annotationId)}"]`);
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.classList.add("mdfh-review-flash");
      setTimeout(() => card.classList.remove("mdfh-review-flash"), 1600);
      activateCard(annotationId);
    }
  }

  function handleReviewClick(event) {
    const editButton = event.target.closest("[data-mdfh-review-edit]");
    if (editButton) {
      event.preventDefault();
      event.stopPropagation();
      const annotation = currentAnnotations().find((item) => item.id === editButton.dataset.mdfhReviewEdit);
      if (annotation) {
        editAnnotation(annotation);
      }
      return;
    }

    if (event.target.closest("[data-mdfh-review-cancel]")) {
      event.preventDefault();
      resetDraft();
      renderAnnotations();
      return;
    }

    if (event.target.closest("[data-mdfh-review-delete]")) {
      event.preventDefault();
      deleteCurrent();
      return;
    }

    const card = event.target.closest("[data-mdfh-review-card]");
    if (card) {
      const annotation = currentAnnotations().find((item) => item.id === card.dataset.mdfhReviewCard);
      if (annotation && annotation.quote) {
        activateCard(annotation.id);
        locateQuote(annotation.quote);
      }
      return;
    }

    const marker = event.target.closest("[data-mdfh-review-anchor-id]");
    if (marker) {
      const annotation = currentAnnotations().find((item) => item.id === marker.dataset.mdfhReviewAnchorId);
      if (annotation) {
        focusCard(annotation.id);
      }
    }
  }

  content.addEventListener("click", handleReviewClick);
  if (els.unplaced) {
    els.unplaced.addEventListener("click", handleReviewClick);
  }
  content.addEventListener("submit", (event) => {
    if (!event.target.closest("[data-mdfh-review-editor]")) {
      return;
    }
    event.preventDefault();
    saveCurrent();
  });
  content.addEventListener("input", (event) => {
    if (event.target.closest("[data-mdfh-review-comment-input]")) {
      state.draftComment = event.target.value;
    }
  });
  document.addEventListener("mouseup", captureSelection);
  document.addEventListener("keyup", captureSelection);
  els.open.addEventListener("click", startDocumentComment);
  window.addEventListener("resize", () => renderAnnotations());
  content.querySelectorAll("img").forEach((image) => {
    image.addEventListener("load", () => renderAnnotations(), { once: true });
  });

  request("/state")
    .then((payload) => handleStatePayload(payload, { initial: true }))
    .catch((error) => toast(error.message));

  window.setInterval(() => {
    request("/state")
      .then((payload) => handleStatePayload(payload, { initial: false }))
      .catch((error) => toast(error.message));
  }, 1500);

  function hasActiveEditor() {
    return Boolean(content.querySelector("[data-mdfh-review-editor]"));
  }

  function handleStatePayload(payload, { initial }) {
    const incomingVersion = payload.build ? payload.build.version : 0;
    if (state.buildVersion === null) {
      state.buildVersion = incomingVersion;
    } else if (incomingVersion !== state.buildVersion) {
      const pages = payload.manifest && Array.isArray(payload.manifest.pages)
        ? payload.manifest.pages
        : [];
      const entryPage = payload.build && payload.build.entry_page ? payload.build.entry_page : "index.html";
      if (pages.includes(page)) {
        window.location.reload();
      } else {
        window.location.href = `/${entryPage}`;
      }
      return;
    }
    const preserveEditor = !initial && hasActiveEditor();
    state.artifact = ensureV2Artifact(payload.artifact);
    if (!preserveEditor) {
      renderAnnotations();
    }
    if (payload.build && payload.build.error) {
      toast(payload.build.error);
    } else if (
      !preserveEditor &&
      payload.validation &&
      payload.validation.errors &&
      payload.validation.errors.length
    ) {
      toast("", payload.validation);
    }
  }
})();
""".strip()


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
                    body = app.render_site_file(self.path).encode("utf-8")
                    self._send_bytes(body, "text/html; charset=utf-8")
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
        ) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
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
    if stdout is not None:
        print(f"Review server: {url}", file=stdout)
        print("Press Ctrl-C to stop.", file=stdout)
    opener(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
