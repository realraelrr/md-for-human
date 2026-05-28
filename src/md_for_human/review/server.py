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

body.mdfh-review-rail-open .layout {
  padding-right: min(24rem, 30vw);
}

.mdfh-review-rail {
  position: fixed;
  inset: 0 0 0 auto;
  width: min(24rem, 30vw);
  min-width: 20rem;
  z-index: 51;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  padding: 1rem;
  overflow: auto;
  border-left: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel) 96%, black);
  box-shadow: -16px 0 44px rgba(0, 0, 0, 0.24);
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
}

.mdfh-review-rail[hidden] {
  display: none !important;
}

.mdfh-review-rail-header,
.mdfh-review-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  justify-content: space-between;
}

.mdfh-review-rail-title {
  font-size: 0.95rem;
  font-weight: 650;
}

.mdfh-review-anchor {
  max-height: 6.5rem;
  overflow: auto;
  border-left: 2px solid var(--accent);
  padding-left: 0.65rem;
  color: var(--muted);
  font-size: 0.86rem;
  line-height: 1.45;
  white-space: pre-wrap;
}

.mdfh-review-comment-input {
  width: 100%;
  min-height: 7rem;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  padding: 0.7rem;
  background: var(--bg);
  color: var(--text);
  resize: vertical;
  font: inherit;
}

.mdfh-review-rail button {
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  padding: 0.48rem 0.68rem;
  background: var(--panel-strong);
  color: var(--text);
  cursor: pointer;
  font: inherit;
}

.mdfh-review-rail button:hover,
.mdfh-review-open:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.mdfh-review-list {
  position: relative;
  min-height: 55vh;
  padding-top: 0.35rem;
}

.mdfh-review-item {
  position: fixed;
  right: 1rem;
  width: calc(min(24rem, 30vw) - 2rem);
  display: grid;
  gap: 0.28rem;
  text-align: left;
  transition: top 120ms ease;
}

.mdfh-review-item::before {
  content: "";
  position: absolute;
  top: 50%;
  left: -1rem;
  width: 1rem;
  border-top: 1px dashed var(--border);
}

.mdfh-review-item small {
  color: var(--muted);
  line-height: 1.35;
}

.mdfh-review-toast {
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

.mdfh-review-connectors {
  position: fixed;
  inset: 0;
  z-index: 50;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
}

.mdfh-review-connectors line {
  stroke: #facc15;
  stroke-width: 1.5;
  stroke-dasharray: 4 4;
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
  body.mdfh-review-rail-open .layout {
    padding-right: 0;
  }

  .mdfh-review-rail {
    inset: auto 0 0 0;
    width: auto;
    min-width: 0;
    max-height: 68vh;
    border-left: 0;
    border-top: 1px solid var(--border);
  }

  .mdfh-review-connectors {
    display: none;
  }
}
</style>
""".strip()

REVIEW_CLIENT_PANEL = """
<button type="button" class="mdfh-review-open" data-mdfh-review-open>Comment</button>
<svg class="mdfh-review-connectors" data-mdfh-review-connector-layer
  aria-hidden="true"></svg>
<aside class="mdfh-review-rail" data-mdfh-review-rail data-mdfh-review-panel
  aria-label="Document comments" hidden>
  <div class="mdfh-review-rail-header">
    <div class="mdfh-review-rail-title">Comments</div>
    <button type="button" data-mdfh-review-close>Hide</button>
  </div>
  <div class="mdfh-review-anchor" data-mdfh-review-anchor>Document comment</div>
  <textarea class="mdfh-review-comment-input" data-mdfh-review-comment-input
    placeholder="Write the requested change and why it matters."></textarea>
  <div class="mdfh-review-actions">
    <button type="button" data-mdfh-review-save>Save</button>
    <button type="button" data-mdfh-review-delete hidden>Delete</button>
  </div>
  <div class="mdfh-review-list" data-mdfh-review-list></div>
  <div class="mdfh-review-toast" data-mdfh-review-toast role="status" hidden></div>
</aside>
""".strip()

REVIEW_CLIENT_JS = r"""
(() => {
  const token = __MDFH_TOKEN__;
  const apiPrefix = __MDFH_API_PREFIX__;
  const content = document.querySelector("[data-mdfh-content='1']");
  const rail = document.querySelector("[data-mdfh-review-rail]");
  if (!content || !rail) {
    return;
  }

  const page = document.body.dataset.mdfhPage || "";
  const sourcePath = document.body.dataset.mdfhSourcePath || "";
  const els = {
    open: document.querySelector("[data-mdfh-review-open]"),
    connectors: document.querySelector("[data-mdfh-review-connector-layer]"),
    close: rail.querySelector("[data-mdfh-review-close]"),
    anchor: rail.querySelector("[data-mdfh-review-anchor]"),
    comment: rail.querySelector("[data-mdfh-review-comment-input]"),
    save: rail.querySelector("[data-mdfh-review-save]"),
    del: rail.querySelector("[data-mdfh-review-delete]"),
    list: rail.querySelector("[data-mdfh-review-list]"),
    toast: rail.querySelector("[data-mdfh-review-toast]"),
  };
  const state = {
    artifact: null,
    selectedQuote: "",
    editingId: "",
    pendingSpan: null,
    toastTimer: 0,
    buildVersion: null,
    anchorState: new Map(),
  };

  const normalize = (value) => String(value || "").split(/\s+/).filter(Boolean).join(" ");
  const nowIso = () => new Date().toISOString();
  const clone = (value) => JSON.parse(JSON.stringify(value));

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

  function openRail() {
    rail.hidden = false;
    document.body.classList.add("mdfh-review-rail-open");
    schedulePositioning();
  }

  function closeRail() {
    rail.hidden = true;
    document.body.classList.remove("mdfh-review-rail-open");
    updateConnectors();
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

  function resetForm({ keepQuote = false } = {}) {
    if (!keepQuote) {
      clearPendingSpan();
      state.selectedQuote = "";
      state.editingId = "";
      els.anchor.textContent = "Document comment";
    }
    els.comment.value = "";
    els.del.hidden = true;
  }

  function setTargetFromQuote(quote) {
    state.selectedQuote = quote.trim();
    state.editingId = "";
    els.anchor.textContent = state.selectedQuote || "Document comment";
    els.comment.value = "";
    els.del.hidden = true;
    openRail();
    els.comment.focus();
  }

  function captureSelection() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      return;
    }
    const range = selection.getRangeAt(0);
    if (!content.contains(range.commonAncestorContainer)) {
      return;
    }
    const selectedText = selection.toString().trim();
    if (!selectedText) {
      return;
    }
    clearPendingSpan();
    markPendingRange(range);
    setTargetFromQuote(selectedText);
  }

  function markPendingRange(range) {
    const span = document.createElement("span");
    span.className = "mdfh-review-underline mdfh-review-pending";
    try {
      range.surroundContents(span);
      state.pendingSpan = span;
      window.getSelection()?.removeAllRanges();
    } catch (_error) {
      state.pendingSpan = null;
    }
  }

  function clearPendingSpan() {
    if (!state.pendingSpan) {
      return;
    }
    const parent = state.pendingSpan.parentNode;
    while (state.pendingSpan.firstChild) {
      parent.insertBefore(state.pendingSpan.firstChild, state.pendingSpan);
    }
    parent.removeChild(state.pendingSpan);
    parent.normalize();
    state.pendingSpan = null;
  }

  async function saveCurrent() {
    if (!state.artifact) {
      toast("Still loading comments.");
      return;
    }
    const comment = els.comment.value.trim();
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
    if (state.selectedQuote.trim()) {
      annotation.quote = state.selectedQuote.trim();
    } else {
      annotation.scope = "document";
    }
    artifact.annotations = annotations
      .filter((item) => item.id !== annotation.id)
      .concat(annotation);
    await saveArtifact(artifact, "Saved.");
    state.editingId = annotation.id;
    els.del.hidden = false;
  }

  async function saveArtifact(artifact, message) {
    try {
      const payload = await request("/annotations", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(artifact),
      });
      state.artifact = ensureV2Artifact(payload.artifact);
      clearPendingSpan();
      renderAnnotations();
      toast(message, payload.validation);
    } catch (error) {
      toast(error.message);
    }
  }

  async function deleteCurrent() {
    if (!state.editingId || !state.artifact) {
      return;
    }
    const artifact = clone(state.artifact);
    artifact.annotations = currentAnnotations().filter((item) => item.id !== state.editingId);
    await saveArtifact(artifact, "Deleted.");
    resetForm();
  }

  function renderAnnotations() {
    unwrapSavedMarkers();
    state.anchorState = new Map();
    const annotations = currentAnnotations();
    annotations
      .filter((annotation) => annotation.page === page && annotation.quote)
      .forEach((annotation) => markSavedQuote(annotation));
    renderList(annotations);
    positionCommentCards();
    updateConnectors();
  }

  function renderList(annotations) {
    if (annotations.length === 0) {
      els.list.innerHTML = "";
      return;
    }
    const sortedAnnotations = annotations.slice().sort((left, right) => {
      return annotationSortTop(left) - annotationSortTop(right);
    });
    els.list.innerHTML = sortedAnnotations.map((annotation) => {
      const status = state.anchorState.get(annotation.id);
      const warning = status && status.warning ? `<small>${escapeHtml(status.warning)}</small>` : "";
      return `
      <button type="button" class="mdfh-review-item" data-mdfh-review-item="${escapeAttr(annotation.id)}">
        <span>${escapeHtml(annotation.comment)}</span>
        <small>${escapeHtml(annotation.quote || "Document comment")}</small>
        ${warning}
      </button>
    `;
    }).join("");
  }

  function markSavedQuote(annotation) {
    const ranges = findQuoteRanges(annotation.quote);
    if (ranges.length !== 1) {
      state.anchorState.set(annotation.id, {
        warning: ranges.length === 0 ? "Quote not found on this page." : "Quote appears more than once.",
      });
      return;
    }
    wrapQuoteSegments(ranges[0].segments, annotation.id);
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

  function findQuoteRanges(quote) {
    const parts = [];
    const walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    let text = "";
    while (node) {
      const value = node.nodeValue || "";
      parts.push({ node, start: text.length, end: text.length + value.length });
      text += value;
      node = walker.nextNode();
    }
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

  function wrapQuoteSegments(segments, annotationId) {
    segments.slice().reverse().forEach((segment) => {
      const textNode = segment.node;
      const parent = textNode.parentNode;
      if (!parent) {
        return;
      }
      const after = textNode.splitText(segment.end);
      const middle = textNode.splitText(segment.start);
      const span = document.createElement("span");
      span.className = "mdfh-review-underline";
      span.dataset.mdfhReviewAnchorId = annotationId;
      parent.insertBefore(span, after);
      span.appendChild(middle);
    });
  }

  function annotationSortTop(annotation) {
    if (annotation.page !== page) {
      return Number.MAX_SAFE_INTEGER;
    }
    const marker = firstMarkerForAnnotation(annotation.id);
    if (!marker) {
      return annotation.scope === "document" ? 0 : Number.MAX_SAFE_INTEGER - 1;
    }
    return marker.getBoundingClientRect().top + window.scrollY;
  }

  function firstMarkerForAnnotation(annotationId) {
    return content.querySelector(`[data-mdfh-review-anchor-id="${cssEscape(annotationId)}"]`);
  }

  function positionCommentCards() {
    const railRect = rail.getBoundingClientRect();
    const cards = Array.from(els.list.querySelectorAll("[data-mdfh-review-item]"));
    let nextTop = 72;
    cards.forEach((card) => {
      const annotation = currentAnnotations().find((item) => item.id === card.dataset.mdfhReviewItem);
      const marker = annotation ? firstMarkerForAnnotation(annotation.id) : null;
      const desiredTop = marker ? marker.getBoundingClientRect().top : 72;
      const top = Math.max(72, desiredTop, nextTop);
      card.style.top = `${top}px`;
      nextTop = top + card.offsetHeight + 10;
    });
    els.list.style.minHeight = `${Math.max(window.innerHeight - railRect.top, nextTop + 16)}px`;
  }

  function updateConnectors() {
    if (!els.connectors) {
      return;
    }
    els.connectors.innerHTML = "";
    if (rail.hidden) {
      return;
    }
    els.list.querySelectorAll("[data-mdfh-review-item]").forEach((card) => {
      const annotation = currentAnnotations().find((item) => item.id === card.dataset.mdfhReviewItem);
      const marker = annotation ? firstMarkerForAnnotation(annotation.id) : null;
      if (!marker) {
        return;
      }
      const markerRect = marker.getBoundingClientRect();
      const cardRect = card.getBoundingClientRect();
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(markerRect.right));
      line.setAttribute("y1", String(markerRect.top + markerRect.height / 2));
      line.setAttribute("x2", String(cardRect.left));
      line.setAttribute("y2", String(cardRect.top + Math.min(32, cardRect.height / 2)));
      els.connectors.appendChild(line);
    });
  }

  function schedulePositioning() {
    window.requestAnimationFrame(() => {
      positionCommentCards();
      updateConnectors();
    });
  }

  function editAnnotation(annotation) {
    if (annotation.page !== page) {
      window.location.href = `/${annotation.page}`;
      return;
    }
    state.editingId = annotation.id;
    state.selectedQuote = annotation.quote || "";
    els.anchor.textContent = annotation.quote || "Document comment";
    els.comment.value = annotation.comment || "";
    els.del.hidden = false;
    openRail();
    if (annotation.quote) {
      locateQuote(annotation.quote);
    }
    els.comment.focus();
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
    window.requestAnimationFrame(() => {
      positionCommentCards();
      updateConnectors();
    });
  }

  function countOccurrences(haystack, needle) {
    if (!needle) {
      return 0;
    }
    let count = 0;
    let index = 0;
    while (true) {
      index = haystack.indexOf(needle, index);
      if (index === -1) {
        return count;
      }
      count += 1;
      index += needle.length;
    }
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

  rail.addEventListener("click", (event) => {
    const button = event.target.closest("[data-mdfh-review-item]");
    if (!button) {
      return;
    }
    const annotation = currentAnnotations().find((item) => item.id === button.dataset.mdfhReviewItem);
    if (annotation) {
      editAnnotation(annotation);
    }
  });
  content.addEventListener("click", (event) => {
    const marker = event.target.closest("[data-mdfh-review-anchor-id]");
    if (!marker) {
      return;
    }
    const annotation = currentAnnotations().find((item) => item.id === marker.dataset.mdfhReviewAnchorId);
    if (annotation) {
      editAnnotation(annotation);
    }
  });
  document.addEventListener("mouseup", captureSelection);
  document.addEventListener("keyup", captureSelection);
  els.open.addEventListener("click", () => {
    resetForm();
    openRail();
    els.comment.focus();
  });
  els.close.addEventListener("click", closeRail);
  els.save.addEventListener("click", saveCurrent);
  els.del.addEventListener("click", deleteCurrent);
  window.addEventListener("scroll", schedulePositioning, { passive: true });
  window.addEventListener("resize", schedulePositioning);

  request("/state")
    .then((payload) => handleStatePayload(payload, { initial: true }))
    .catch((error) => toast(error.message));

  window.setInterval(() => {
    request("/state")
      .then((payload) => handleStatePayload(payload, { initial: false }))
      .catch((error) => toast(error.message));
  }, 1500);

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
    state.artifact = ensureV2Artifact(payload.artifact);
    renderAnnotations();
    const pageHasAnnotations = currentAnnotations().some((annotation) => annotation.page === page);
    if (initial && pageHasAnnotations) {
      openRail();
    }
    if (payload.build && payload.build.error) {
      toast(payload.build.error);
    } else if (payload.validation && payload.validation.errors && payload.validation.errors.length) {
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
