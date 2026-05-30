(() => {
  const token = __MDFH_TOKEN__;
  const apiPrefix = __MDFH_API_PREFIX__;
  const content = document.querySelector("[data-mdfh-content='1']");
  if (!content) {
    return;
  }

  const artifact = window.mdfhReviewArtifact;
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
    selectedSourceRange: null,
    editingId: "",
    documentMode: false,
    draftComment: "",
    pendingSpans: [],
    toastTimer: 0,
    buildVersion: null,
    anchorState: new Map(),
  };

  const fallbackReviewMessages = {
    reviewComment: "Comment",
    reviewEdit: "Edit",
    reviewSave: "Save",
    reviewDelete: "Delete",
    reviewCancel: "Cancel",
    reviewDocumentComment: "Document comment",
    reviewPageComments: "Page comments",
    reviewUnplacedHelp: "These comments are saved for this page; the exact underline is not available.",
    reviewPlaceholder: "Write the requested change and why it matters.",
    reviewLoading: "Still loading comments.",
    reviewNeedComment: "Write a comment before saving.",
    reviewSaved: "Saved.",
    reviewDeleted: "Deleted.",
    reviewRequestFailed: "Request failed",
    reviewErrorPrefix: "Error",
    reviewUnderlineUnavailable: "Exact underline is unavailable.",
    reviewUnderlineAmbiguous: "Exact underline is ambiguous.",
    reviewQuoteUnresolved: "Quote location could not be resolved.",
    source: "Source",
    reviewComments: "Review comments",
  };

  function t(key) {
    if (window.mdfhI18n && window.mdfhI18n.t) {
      return window.mdfhI18n.t(key);
    }
    return fallbackReviewMessages[key] || key;
  }

  function applyTranslations(root) {
    if (window.mdfhI18n && window.mdfhI18n.apply) {
      window.mdfhI18n.apply(root);
    }
  }

  function currentAnnotations() {
    return artifact.annotations(state.artifact);
  }

  function pageAnnotations() {
    return artifact.annotationsForPage(state.artifact, sourcePath);
  }

  async function request(path, options = {}) {
    const headers = Object.assign(
      { [ "X-MDFH-Review-Token" ]: token },
      options.headers || {},
    );
    const response = await fetch(apiPrefix + path, Object.assign({}, options, { headers }));
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) {
      const message = (payload.errors || [payload.error || t("reviewRequestFailed")]).join("\n");
      throw new Error(message);
    }
    return payload;
  }

  function toast(message, validation = null) {
    window.clearTimeout(state.toastTimer);
    const lines = [];
    if (message) {
      lines.push(escapeHtml(message));
    }
    const hasErrors = Boolean(validation && validation.errors && validation.errors.length);
    if (validation && validation.errors && validation.errors.length) {
      lines.push(uniqueMessages(validation.errors).map((item) => `${t("reviewErrorPrefix")}: ${escapeHtml(item)}`).join("<br>"));
    }
    els.toast.innerHTML = lines.join("<br>");
    els.toast.hidden = lines.length === 0;
    if (!hasErrors && message) {
      state.toastTimer = window.setTimeout(() => {
        els.toast.hidden = true;
      }, 1800);
    }
  }

  function uniqueMessages(messages) {
    return Array.from(new Set((messages || []).filter(Boolean)));
  }

  function resetDraft() {
    clearPendingSpans();
    state.selectedQuote = "";
    state.selectedSourceRange = null;
    state.editingId = "";
    state.documentMode = false;
    state.draftComment = "";
  }

  function clearPendingSpans() {
    sourceLocator.unwrapSpans(state.pendingSpans);
    state.pendingSpans = [];
  }

  function startDocumentComment() {
    resetDraft();
    state.documentMode = true;
    renderer.renderAnnotations();
    focusEditor();
  }

  function setTargetFromQuote(quote, sourceRange = null) {
    state.selectedQuote = quote.trim();
    state.selectedSourceRange = sourceRange;
    state.editingId = "";
    state.documentMode = false;
    state.draftComment = "";
    renderer.renderAnnotations();
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
    if (!sourceLocator.isRangeInsideReviewBody(range)) {
      return;
    }
    const selectedText = selection.toString().trim();
    if (!selectedText) {
      return;
    }
    const sourceRange = sourceLocator.sourceRangeForSelection(range);
    clearPendingSpans();
    state.pendingSpans = sourceLocator.markRange(range);
    setTargetFromQuote(selectedText, sourceRange);
  }

  async function saveCurrent() {
    if (!state.artifact) {
      toast(t("reviewLoading"));
      return;
    }
    const comment = currentEditorValue();
    if (!comment) {
      toast(t("reviewNeedComment"));
      return;
    }
    const writableArtifact = artifact.clone(state.artifact);
    writableArtifact.schema_version = artifact.schemaVersion;
    writableArtifact.source_manifest = ".md-for-human/manifest.json";
    const annotations = Array.isArray(writableArtifact.annotations) ? writableArtifact.annotations : [];
    const annotation = {
      source_path: sourcePath,
      comment,
    };
    if (state.editingId) {
      annotation.id = state.editingId;
    }
    if (state.selectedQuote.trim() && !state.documentMode) {
      annotation.meta = { quote: state.selectedQuote.trim() };
      if (state.selectedSourceRange) {
        annotation.source_range = state.selectedSourceRange;
      }
    } else {
      annotation.source_range = { start_line: 0, end_line: 0 };
    }
    writableArtifact.annotations = annotations
      .filter((item) => !annotation.id || item.id !== annotation.id)
      .concat(annotation);
    if (await saveArtifact(writableArtifact, t("reviewSaved"))) {
      resetDraft();
      renderer.renderAnnotations();
    }
  }

  async function saveArtifact(writableArtifact, message) {
    try {
      const payload = await request("/annotations", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(writableArtifact),
      });
      state.artifact = artifact.ensureV2Artifact(payload.artifact);
      clearPendingSpans();
      renderer.renderAnnotations();
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
    const writableArtifact = artifact.clone(state.artifact);
    writableArtifact.annotations = currentAnnotations().filter((item) => item.id !== state.editingId);
    if (await saveArtifact(writableArtifact, t("reviewDeleted"))) {
      resetDraft();
      renderer.renderAnnotations();
    }
  }

  function editAnnotation(annotation) {
    state.editingId = annotation.id;
    state.selectedQuote = artifact.annotationQuote(annotation) || "";
    state.selectedSourceRange = sourceLocator.sourceRangeForAnnotation(annotation);
    state.documentMode = sourceLocator.isGlobalAnnotation(annotation);
    state.draftComment = annotation.comment || "";
    clearPendingSpans();
    renderer.renderAnnotations();
    sourceLocator.locateAnnotation(annotation);
    focusEditor();
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
      renderer.renderAnnotations();
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
      if (annotation) {
        renderer.activateCard(annotation.id);
        sourceLocator.locateAnnotation(annotation);
      }
      return;
    }

    const marker = event.target.closest("[data-mdfh-review-anchor-id]");
    if (marker) {
      const annotation = currentAnnotations().find((item) => item.id === marker.dataset.mdfhReviewAnchorId);
      if (annotation) {
        renderer.focusCard(annotation.id);
      }
    }
  }

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
    state.artifact = artifact.ensureV2Artifact(payload.artifact);
    if (!preserveEditor) {
      renderer.renderAnnotations();
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

  const sourceLocator = window.mdfhReviewSourceLocator.create({
    content,
    t,
    toast,
    annotationQuote: artifact.annotationQuote,
    cssEscape,
  });
  const renderer = window.mdfhReviewCommentsRenderer.create({
    content,
    article,
    els,
    state,
    t,
    applyTranslations,
    escapeHtml,
    escapeAttr,
    cssEscape,
    artifact,
    sourceLocator,
    getPageAnnotations: pageAnnotations,
    getCurrentAnnotations: currentAnnotations,
  });

  document.body.classList.add("mdfh-review-mode");
  renderer.prepareReviewLayout();

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
  window.addEventListener("mdfh:localechange", () => {
    applyTranslations(document);
    renderer.renderAnnotations();
  });
  window.addEventListener("resize", () => renderer.renderAnnotations());
  content.querySelectorAll("img").forEach((image) => {
    image.addEventListener("load", () => renderer.renderAnnotations(), { once: true });
  });

  request("/state")
    .then((payload) => handleStatePayload(payload, { initial: true }))
    .catch((error) => toast(error.message));

  window.setInterval(() => {
    request("/state")
      .then((payload) => handleStatePayload(payload, { initial: false }))
      .catch((error) => toast(error.message));
  }, 1500);
})();
