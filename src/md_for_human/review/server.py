from __future__ import annotations

import json
import secrets
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Callable, TextIO
from urllib.parse import unquote, urlsplit

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
    def __init__(self, output_dir: Path, *, token: str) -> None:
        self.output_dir = Path(output_dir)
        self.token = token
        self.manifest_path = self.output_dir / ".md-for-human" / "manifest.json"
        if not self.manifest_path.exists():
            raise ReviewServerError(f"manifest.json is missing in {self.output_dir}")
        self._ensure_artifact()

    def get_state(self, *, token: str) -> dict[str, Any]:
        self._require_token(token)
        artifact = self._ensure_artifact()
        validation = validate_review(self.output_dir)
        manifest_errors: list[str] = []
        manifest = load_json_file(self.manifest_path, manifest_errors)
        if manifest is None:
            manifest = {}
        return {
            "api_prefix": REVIEW_API_PREFIX,
            "artifact": artifact,
            "manifest": manifest,
            "validation": validation_payload(validation),
        }

    def save_annotations(self, *, token: str, artifact: dict[str, Any]) -> dict[str, Any]:
        self._require_token(token)
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
        self._ensure_artifact()
        return {"validation": validation_payload(validate_review(self.output_dir))}

    def render_site_file(self, relative_url_path: str) -> str:
        relative_path = self._site_path_from_url(relative_url_path)
        path = self._resolve_site_path(relative_path)
        if path.suffix.lower() != ".html":
            raise ReviewServerError(f"not an HTML page: {relative_path.as_posix()}")
        html = path.read_text(encoding="utf-8")
        return inject_review_client(html, self.token)

    def read_static_file(self, relative_url_path: str) -> tuple[bytes, str]:
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
            artifact = empty_artifact(created_by_kind="human")
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
body.mdfh-review-enabled .layout {
  padding-right: min(28rem, 34vw);
}

.mdfh-review-panel {
  position: fixed;
  inset: 0 0 0 auto;
  width: min(28rem, 34vw);
  min-width: 22rem;
  z-index: 50;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
  overflow: auto;
  border-left: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel) 94%, black);
  box-shadow: -16px 0 48px rgba(0, 0, 0, 0.28);
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
}

.mdfh-review-panel h2,
.mdfh-review-panel h3 {
  margin: 0;
  font-family: "Avenir Next", "Helvetica Neue", sans-serif;
}

.mdfh-review-panel [hidden] {
  display: none !important;
}

.mdfh-review-panel label {
  display: grid;
  gap: 0.35rem;
  font-size: 0.82rem;
  color: var(--muted);
}

.mdfh-review-panel select,
.mdfh-review-panel input,
.mdfh-review-panel textarea {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  padding: 0.55rem 0.65rem;
  background: var(--bg);
  color: var(--text);
  font: inherit;
}

.mdfh-review-panel textarea {
  min-height: 5.5rem;
  resize: vertical;
}

.mdfh-review-panel button {
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  padding: 0.5rem 0.7rem;
  background: var(--panel-strong);
  color: var(--text);
  cursor: pointer;
  font: inherit;
}

.mdfh-review-panel button:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.mdfh-review-actions,
.mdfh-review-toolbar {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.mdfh-review-section {
  display: grid;
  gap: 0.75rem;
  padding: 0.85rem;
  border: 1px solid var(--border);
  border-radius: 0.8rem;
  background: rgba(255, 255, 255, 0.03);
}

.mdfh-review-quote {
  max-height: 7rem;
  overflow: auto;
  margin: 0;
  padding: 0.65rem;
  border-radius: 0.55rem;
  background: var(--code-bg);
  color: var(--code-text);
  white-space: pre-wrap;
}

.mdfh-review-list {
  display: grid;
  gap: 0.6rem;
}

.mdfh-review-item {
  display: grid;
  gap: 0.3rem;
  width: 100%;
  text-align: left;
}

.mdfh-review-item small {
  color: var(--muted);
}

.mdfh-review-diagnostics {
  display: grid;
  gap: 0.35rem;
  font-size: 0.84rem;
}

.mdfh-review-error {
  color: #fca5a5;
}

.mdfh-review-warning {
  color: #fde68a;
}

.mdfh-review-flash {
  animation: mdfh-review-flash 1.6s ease-out;
  border-radius: 0.35rem;
}

@keyframes mdfh-review-flash {
  0% {
    outline: 3px solid rgba(250, 204, 21, 0.95);
    background: rgba(250, 204, 21, 0.22);
  }
  100% {
    outline: 0 solid rgba(250, 204, 21, 0);
    background: transparent;
  }
}

@media (max-width: 960px) {
  body.mdfh-review-enabled .layout {
    padding-right: 0;
  }

  .mdfh-review-panel {
    position: static;
    width: auto;
    min-width: 0;
    border-left: 0;
    border-top: 1px solid var(--border);
  }
}
</style>
""".strip()

REVIEW_CLIENT_PANEL = """
<aside class="mdfh-review-panel" data-mdfh-review-panel aria-label="Review annotations">
  <section class="mdfh-review-section">
    <h2>Review</h2>
    <label>
      Reviewer name
      <input type="text" data-mdfh-review-name value="local-reviewer">
    </label>
    <div class="mdfh-review-toolbar">
      <button type="button" data-mdfh-review-validate>Validate</button>
      <button type="button" data-mdfh-review-finish>Finish</button>
    </div>
  </section>
  <section class="mdfh-review-section">
    <h3>Selected annotation</h3>
    <pre class="mdfh-review-quote" data-mdfh-review-quote>No text selected.</pre>
    <label>
      Type
      <select data-mdfh-review-type>
        <option value="comment">Comment</option>
        <option value="suggest_delete">Suggest delete</option>
        <option value="suggest_insert">Suggest insert</option>
        <option value="suggest_replace">Suggest replace</option>
      </select>
    </label>
    <label data-mdfh-review-placement-row hidden>
      Placement
      <select data-mdfh-review-placement>
        <option value="before">Insert before selected anchor</option>
        <option value="after">Insert after selected anchor</option>
      </select>
    </label>
    <label>
      Note
      <textarea data-mdfh-review-note placeholder="Why should the author or agent consider this?"></textarea>
    </label>
    <label data-mdfh-review-suggested-row hidden>
      Suggested text
      <textarea data-mdfh-review-suggested placeholder="Text to insert or replace with."></textarea>
    </label>
    <div class="mdfh-review-actions">
      <button type="button" data-mdfh-review-save>Save</button>
      <button type="button" data-mdfh-review-delete hidden>Delete</button>
      <button type="button" data-mdfh-review-clear>Clear</button>
    </div>
  </section>
  <section class="mdfh-review-section">
    <h3>Annotations</h3>
    <div class="mdfh-review-list" data-mdfh-review-list></div>
  </section>
  <section class="mdfh-review-section">
    <h3>Status</h3>
    <div class="mdfh-review-diagnostics" data-mdfh-review-status></div>
  </section>
</aside>
""".strip()

REVIEW_CLIENT_JS = r"""
(() => {
  const token = __MDFH_TOKEN__;
  const apiPrefix = __MDFH_API_PREFIX__;
  const content = document.querySelector("[data-mdfh-content='1']");
  const panel = document.querySelector("[data-mdfh-review-panel]");
  if (!content || !panel) {
    return;
  }

  document.body.classList.add("mdfh-review-enabled");

  const page = document.body.dataset.mdfhPage || "";
  const sourcePath = document.body.dataset.mdfhSourcePath || "";
  const els = {
    name: panel.querySelector("[data-mdfh-review-name]"),
    quote: panel.querySelector("[data-mdfh-review-quote]"),
    type: panel.querySelector("[data-mdfh-review-type]"),
    placementRow: panel.querySelector("[data-mdfh-review-placement-row]"),
    placement: panel.querySelector("[data-mdfh-review-placement]"),
    note: panel.querySelector("[data-mdfh-review-note]"),
    suggestedRow: panel.querySelector("[data-mdfh-review-suggested-row]"),
    suggested: panel.querySelector("[data-mdfh-review-suggested]"),
    save: panel.querySelector("[data-mdfh-review-save]"),
    del: panel.querySelector("[data-mdfh-review-delete]"),
    clear: panel.querySelector("[data-mdfh-review-clear]"),
    validate: panel.querySelector("[data-mdfh-review-validate]"),
    finish: panel.querySelector("[data-mdfh-review-finish]"),
    list: panel.querySelector("[data-mdfh-review-list]"),
    status: panel.querySelector("[data-mdfh-review-status]"),
  };
  const state = {
    artifact: null,
    selectedQuote: "",
    editingId: "",
  };

  const normalize = (value) => value.split(/\s+/).filter(Boolean).join(" ");
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
      const message = (payload.errors || [payload.error || "Review request failed"]).join("\n");
      throw new Error(message);
    }
    return payload;
  }

  function setStatus(validation, extraMessage = "") {
    const lines = [];
    if (extraMessage) {
      lines.push(`<div>${escapeHtml(extraMessage)}</div>`);
    }
    if (!validation) {
      els.status.innerHTML = lines.join("");
      return;
    }
    lines.push(`<div>${validation.passed ? "Validation passed" : "Validation has errors"}</div>`);
    (validation.errors || []).forEach((error) => {
      lines.push(`<div class="mdfh-review-error">Error: ${escapeHtml(error)}</div>`);
    });
    (validation.warnings || []).forEach((warning) => {
      lines.push(`<div class="mdfh-review-warning">Warning: ${escapeHtml(warning)}</div>`);
    });
    els.status.innerHTML = lines.join("") || "<div>Ready.</div>";
  }

  function renderList() {
    const annotations = currentAnnotations();
    if (annotations.length === 0) {
      els.list.innerHTML = "<p>No annotations yet.</p>";
      return;
    }
    els.list.innerHTML = annotations.map((annotation) => `
      <button type="button" class="mdfh-review-item" data-mdfh-review-item="${escapeAttr(annotation.id)}">
        <strong>${escapeHtml(annotation.type)}: ${escapeHtml(annotation.note)}</strong>
        <small>${escapeHtml(annotation.page)} / ${escapeHtml(annotation.source_path)}</small>
        <small>${escapeHtml(annotation.quote)}</small>
      </button>
    `).join("");
  }

  function currentAnnotations() {
    if (!state.artifact || !Array.isArray(state.artifact.annotations)) {
      return [];
    }
    return state.artifact.annotations;
  }

  function resetForm() {
    state.selectedQuote = "";
    state.editingId = "";
    els.quote.textContent = "No text selected.";
    els.note.value = "";
    els.suggested.value = "";
    els.type.value = "comment";
    els.placement.value = "after";
    els.del.hidden = true;
    updateTypeRows();
  }

  function updateTypeRows() {
    const type = els.type.value;
    els.placementRow.hidden = type !== "suggest_insert";
    els.suggestedRow.hidden = type !== "suggest_insert" && type !== "suggest_replace";
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
    state.selectedQuote = selectedText;
    state.editingId = "";
    els.quote.textContent = selectedText;
    els.del.hidden = true;
  }

  function applyReviewerName() {
    if (!state.artifact) {
      return;
    }
    state.artifact.created_by = {
      kind: "human",
      name: els.name.value.trim() || "local-reviewer",
    };
  }

  async function saveCurrent() {
    if (!state.artifact) {
      setStatus(null, "Review state is still loading.");
      return;
    }
    if (!state.selectedQuote.trim()) {
      setStatus(null, "Select text in the document first.");
      return;
    }
    if (!els.note.value.trim()) {
      setStatus(null, "Note is required.");
      return;
    }
    const type = els.type.value;
    if ((type === "suggest_insert" || type === "suggest_replace") && !els.suggested.value.trim()) {
      setStatus(null, "Suggested text is required for this annotation type.");
      return;
    }
    applyReviewerName();
    const artifact = clone(state.artifact);
    const annotations = Array.isArray(artifact.annotations) ? artifact.annotations : [];
    const existing = annotations.find((annotation) => annotation.id === state.editingId);
    const timestamp = nowIso();
    const annotation = {
      id: state.editingId || `ann_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      type,
      page,
      source_path: sourcePath,
      quote: state.selectedQuote.trim(),
      note: els.note.value.trim(),
      created_at: existing ? existing.created_at : timestamp,
      updated_at: timestamp,
    };
    if (type === "suggest_insert") {
      annotation.placement = els.placement.value;
      annotation.suggested_text = els.suggested.value.trim();
    }
    if (type === "suggest_replace") {
      annotation.suggested_text = els.suggested.value.trim();
    }
    const nextAnnotations = annotations.filter((item) => item.id !== annotation.id);
    nextAnnotations.push(annotation);
    artifact.annotations = nextAnnotations;
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
      state.artifact = payload.artifact;
      setStatus(payload.validation, message);
      renderList();
    } catch (error) {
      setStatus(null, error.message);
    }
  }

  async function deleteCurrent() {
    if (!state.editingId || !state.artifact) {
      return;
    }
    applyReviewerName();
    const artifact = clone(state.artifact);
    artifact.annotations = currentAnnotations().filter((annotation) => annotation.id !== state.editingId);
    await saveArtifact(artifact, "Deleted.");
    resetForm();
  }

  async function validateCurrent(message = "Validated.") {
    try {
      const payload = await request("/validate", { method: "POST" });
      setStatus(payload.validation, message);
    } catch (error) {
      setStatus(null, error.message);
    }
  }

  function editAnnotation(annotation) {
    if (annotation.page !== page) {
      window.location.href = annotation.page;
      return;
    }
    state.editingId = annotation.id;
    state.selectedQuote = annotation.quote;
    els.quote.textContent = annotation.quote;
    els.type.value = annotation.type;
    els.placement.value = annotation.placement || "after";
    els.note.value = annotation.note || "";
    els.suggested.value = annotation.suggested_text || "";
    els.del.hidden = false;
    updateTypeRows();
    locateQuote(annotation.quote);
  }

  function locateQuote(quote) {
    const normalizedQuote = normalize(quote);
    const normalizedText = normalize(content.innerText || content.textContent || "");
    const count = countOccurrences(normalizedText, normalizedQuote);
    if (count !== 1) {
      setStatus(null, count === 0 ? "Quote was not found on this page." : "Quote appears multiple times on this page.");
      return;
    }
    let target = null;
    if (window.find && window.find(quote)) {
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
        const node = selection.getRangeAt(0).startContainer;
        target = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
      }
    }
    if (!target || !content.contains(target)) {
      target = content;
    }
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.add("mdfh-review-flash");
    setTimeout(() => target.classList.remove("mdfh-review-flash"), 1800);
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

  panel.addEventListener("click", (event) => {
    const button = event.target.closest("[data-mdfh-review-item]");
    if (!button) {
      return;
    }
    const annotation = currentAnnotations().find((item) => item.id === button.dataset.mdfhReviewItem);
    if (annotation) {
      editAnnotation(annotation);
    }
  });
  document.addEventListener("mouseup", captureSelection);
  document.addEventListener("keyup", captureSelection);
  els.type.addEventListener("change", updateTypeRows);
  els.save.addEventListener("click", saveCurrent);
  els.del.addEventListener("click", deleteCurrent);
  els.clear.addEventListener("click", resetForm);
  els.validate.addEventListener("click", () => validateCurrent());
  els.finish.addEventListener("click", () => validateCurrent("Review artifact ready."));

  request("/state")
    .then((payload) => {
      state.artifact = payload.artifact;
      if (state.artifact && state.artifact.created_by && state.artifact.created_by.name) {
        els.name.value = state.artifact.created_by.name;
      }
      setStatus(payload.validation, "Ready.");
      renderList();
      updateTypeRows();
    })
    .catch((error) => setStatus(null, error.message));
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
    host: str = LOCAL_REVIEW_HOST,
    port: int = 0,
    opener: Callable[[str], object] = webbrowser.open,
    stdout: TextIO | None = None,
) -> int:
    stdout = stdout or None
    token = secrets.token_urlsafe(24)
    app = ReviewServerApp(output_dir, token=token)
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
