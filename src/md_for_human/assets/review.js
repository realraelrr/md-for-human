(() => {
  const token = __MDFH_TOKEN__;
  const apiPrefix = __MDFH_API_PREFIX__;
  const content = document.querySelector("[data-mdfh-content='1']");
  if (!content) {
    return;
  }

  document.body.classList.add("mdfh-review-mode");
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

  const clone = (value) => JSON.parse(JSON.stringify(value));
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
      const message = (payload.errors || [payload.error || t("reviewRequestFailed")]).join("\n");
      throw new Error(message);
    }
    return payload;
  }

  function ensureV2Artifact(artifact) {
    if (artifact && artifact.schema_version === "mdfh-review-v2") {
      artifact.annotations = Array.isArray(artifact.annotations) ? artifact.annotations : [];
      artifact.annotations = artifact.annotations.map((annotation) => normalizeAnnotation(annotation));
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

  function currentAnnotations() {
    if (!state.artifact || !Array.isArray(state.artifact.annotations)) {
      return [];
    }
    return state.artifact.annotations;
  }

  function uniqueMessages(messages) {
    return Array.from(new Set((messages || []).filter(Boolean)));
  }

  function annotationMeta(annotation) {
    return annotation && annotation.meta && typeof annotation.meta === "object" ? annotation.meta : {};
  }

  function normalizeAnnotation(annotation) {
    const meta = Object.assign({}, annotationMeta(annotation));
    if (
      annotation &&
      Object.prototype.hasOwnProperty.call(annotation, "quote") &&
      !Object.prototype.hasOwnProperty.call(meta, "quote")
    ) {
      meta.quote = annotation.quote;
    }
    const normalized = {};
    ["id", "source_path", "source_range", "comment", "source_sha256"].forEach((field) => {
      if (annotation && Object.prototype.hasOwnProperty.call(annotation, field)) {
        normalized[field] = annotation[field];
      }
    });
    if (Object.keys(meta).length) {
      normalized.meta = meta;
    }
    return normalized;
  }

  function annotationQuote(annotation) {
    return annotationMeta(annotation).quote || annotation.quote || "";
  }

  function pageAnnotations() {
    return currentAnnotations().filter((annotation) => annotation.source_path === sourcePath);
  }

  function prepareReviewLayout() {
    if (!article || content.dataset.mdfhReviewPrepared === "1") {
      return;
    }
    const unplaced = els.unplaced || document.createElement("div");
    unplaced.className = "mdfh-review-unplaced";
    unplaced.dataset.mdfhReviewUnplaced = "1";
    unplaced.dataset.mdfhUi = "1";
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
    addColumnLabels();
    content.dataset.mdfhReviewPrepared = "1";
  }

  function addColumnLabels() {
    if (content.querySelector("[data-mdfh-review-column-labels]")) {
      return;
    }
    const labels = document.createElement("div");
    labels.className = "mdfh-review-column-labels";
    labels.dataset.mdfhReviewColumnLabels = "1";
    labels.dataset.mdfhUi = "1";

    const bodyLabel = document.createElement("div");
    bodyLabel.className = "mdfh-review-column-label mdfh-review-body-label";
    bodyLabel.dataset.i18n = "source";
    bodyLabel.textContent = t("source");

    const commentsLabel = document.createElement("div");
    commentsLabel.className = "mdfh-review-column-label mdfh-review-comments-label";
    commentsLabel.dataset.i18n = "reviewComments";
    commentsLabel.textContent = t("reviewComments");

    labels.append(bodyLabel, commentsLabel);
    content.insertBefore(labels, content.firstChild);
  }

  function resetDraft() {
    clearPendingSpans();
    state.selectedQuote = "";
    state.selectedSourceRange = null;
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

  function setTargetFromQuote(quote, sourceRange = null) {
    state.selectedQuote = quote.trim();
    state.selectedSourceRange = sourceRange;
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
    const sourceRange = sourceRangeForSelection(range);
    clearPendingSpans();
    markPendingRange(range);
    setTargetFromQuote(selectedText, sourceRange);
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
      toast(t("reviewLoading"));
      return;
    }
    const comment = currentEditorValue();
    if (!comment) {
      toast(t("reviewNeedComment"));
      return;
    }
    const artifact = clone(state.artifact);
    artifact.schema_version = "mdfh-review-v2";
    artifact.source_manifest = ".md-for-human/manifest.json";
    const annotations = Array.isArray(artifact.annotations) ? artifact.annotations : [];
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
    artifact.annotations = annotations
      .filter((item) => !annotation.id || item.id !== annotation.id)
      .concat(annotation);
    if (await saveArtifact(artifact, t("reviewSaved"))) {
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
    if (await saveArtifact(artifact, t("reviewDeleted"))) {
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
      .filter((annotation) => annotationQuote(annotation))
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
      if (status && status.warning && !sourceRangeForAnnotation(annotation)) {
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
    card.dataset.mdfhUi = "1";
    card.tabIndex = 0;
    const sourceRange = sourceRangeForAnnotation(annotation);
    const lineLabel = sourceRangeLabel(sourceRange);
    const anchorLabel = [lineLabel, annotationQuote(annotation) || t("reviewDocumentComment")].filter(Boolean).join(" · ");
    card.innerHTML = `
      <p>${escapeHtml(annotation.comment)}</p>
      <small>${escapeHtml(anchorLabel)}</small>
      <div class="mdfh-review-card-actions">
        <button type="button" data-mdfh-review-edit="${escapeAttr(annotation.id)}" data-i18n="reviewEdit">${escapeHtml(t("reviewEdit"))}</button>
      </div>
    `;
    applyTranslations(card);
    return card;
  }

  function createEditor() {
    const value = state.draftComment || "";
    const anchor = state.documentMode ? t("reviewDocumentComment") : state.selectedQuote;
    const lineLabel = sourceRangeLabel(state.selectedSourceRange);
    const editor = document.createElement("form");
    editor.className = "mdfh-review-editor";
    editor.dataset.mdfhReviewEditor = "1";
    editor.dataset.mdfhUi = "1";
    editor.innerHTML = `
      <div class="mdfh-review-anchor">${escapeHtml(anchor || t("reviewDocumentComment"))}</div>
      ${lineLabel ? `<small>${escapeHtml(lineLabel)}</small>` : ""}
      <textarea class="mdfh-review-comment-input" data-mdfh-review-comment-input
        placeholder="${escapeAttr(t("reviewPlaceholder"))}" data-i18n-placeholder="reviewPlaceholder">${escapeHtml(value)}</textarea>
      <div class="mdfh-review-editor-actions">
        <button type="submit" data-mdfh-review-save data-i18n="reviewSave">${escapeHtml(t("reviewSave"))}</button>
        ${state.editingId ? `<button type="button" data-mdfh-review-delete data-i18n="reviewDelete">${escapeHtml(t("reviewDelete"))}</button>` : ""}
        <button type="button" data-mdfh-review-cancel data-i18n="reviewCancel">${escapeHtml(t("reviewCancel"))}</button>
      </div>
    `;
    applyTranslations(editor);
    return editor;
  }

  function renderUnplacedComments(annotations) {
    if (!els.unplaced) {
      return;
    }
    const unplaced = annotations.filter((annotation) => {
      const status = state.anchorState.get(annotation.id);
      return annotationQuote(annotation) && status && status.warning && !sourceRangeForAnnotation(annotation);
    });
    if (unplaced.length === 0) {
      els.unplaced.hidden = true;
      els.unplaced.innerHTML = "";
      return;
    }
    els.unplaced.hidden = false;
    els.unplaced.innerHTML = `
      <p><strong data-i18n="reviewPageComments">${escapeHtml(t("reviewPageComments"))}</strong></p>
      <small data-i18n="reviewUnplacedHelp">${escapeHtml(t("reviewUnplacedHelp"))}</small>
      <div class="mdfh-review-unplaced-list">
        ${unplaced.map((annotation) => {
          return `
            <div class="mdfh-review-unplaced-item">
              <p>${escapeHtml(annotation.comment)}</p>
              <small>${escapeHtml(annotationQuote(annotation) || t("reviewDocumentComment"))}</small>
              <div class="mdfh-review-card-actions">
                <button type="button" data-mdfh-review-edit="${escapeAttr(annotation.id)}" data-i18n="reviewEdit">${escapeHtml(t("reviewEdit"))}</button>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
    applyTranslations(els.unplaced);
  }

  function markSavedQuote(annotation) {
    const ranges = findQuoteRanges(annotationQuote(annotation));
    if (ranges.length !== 1) {
      state.anchorState.set(annotation.id, {
        warning: ranges.length === 0 ? t("reviewUnderlineUnavailable") : t("reviewUnderlineAmbiguous"),
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
    const source = buildSearchSource();
    const canonicalSource = canonicalizeWithMap(source.text);
    const canonicalQuote = canonicalizeWithMap(quote);
    if (!canonicalQuote.text) {
      return [];
    }
    const ranges = [];
    let index = 0;
    while (true) {
      index = canonicalSource.text.indexOf(canonicalQuote.text, index);
      if (index === -1) {
        break;
      }
      const canonicalEnd = index + canonicalQuote.text.length;
      const rawStart = canonicalSource.map[index].start;
      const rawEnd = canonicalSource.map[canonicalEnd - 1].end;
      const segments = rawIndexToSegments(source.parts, rawStart, rawEnd);
      ranges.push({ start: rawStart, end: rawEnd, segments });
      index = canonicalEnd;
    }
    return ranges;
  }

  function buildSearchSource() {
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
    return { text, parts };
  }

  function rawIndexToSegments(parts, start, end) {
    return parts
      .filter((part) => part.end > start && part.start < end)
      .map((part) => ({
        node: part.node,
        start: Math.max(0, start - part.start),
        end: Math.min(part.end - part.start, end - part.start),
      }))
      .filter((segment) => segment.end > segment.start);
  }

  function canonicalizeWithMap(value) {
    const input = String(value || "");
    let text = "";
    const map = [];
    let pendingSpace = false;
    let pendingSpaceStart = 0;
    let pendingSpaceEnd = 0;
    graphemeClusters(input).forEach((clusterInfo) => {
      const char = clusterInfo.segment;
      if (/\s/u.test(char)) {
        if (!pendingSpace) {
          pendingSpaceStart = clusterInfo.start;
        }
        pendingSpace = true;
        pendingSpaceEnd = clusterInfo.end;
        return;
      }
      if (pendingSpace && text.length > 0) {
        const previous = text[text.length - 1];
        if (!isSpaceEquivalentPunctuation(char) && !isOpeningPunctuation(previous)) {
          text += " ";
          map.push({ start: pendingSpaceStart, end: pendingSpaceEnd });
        }
      }
      pendingSpace = false;
      Array.from(char.normalize("NFC")).forEach((canonicalChar) => {
        appendCanonicalChar(map, canonicalChar, clusterInfo.start, clusterInfo.end);
        text += canonicalChar;
      });
    });
    return { text, map };
  }

  function appendCanonicalChar(map, char, start, end) {
    for (let offset = 0; offset < char.length; offset += 1) {
      map.push({ start, end });
    }
  }

  function isSpaceEquivalentPunctuation(char) {
    return /[，。；：！？、）》】」』）,.!?;:%％]/u.test(char);
  }

  function isOpeningPunctuation(char) {
    return /[（《【「『(]/u.test(char);
  }

  function graphemeClusters(value) {
    if (window.Intl && Intl.Segmenter) {
      const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
      return Array.from(segmenter.segment(value)).map((item) => ({
        segment: item.segment,
        start: item.index,
        end: item.index + item.segment.length,
      }));
    }
    const clusters = [];
    let rawIndex = 0;
    while (rawIndex < value.length) {
      const start = rawIndex;
      let segment = value.slice(rawIndex, rawIndex + codeUnitLengthAt(value, rawIndex));
      rawIndex += segment.length;
      while (rawIndex < value.length) {
        const nextChar = value.slice(rawIndex, rawIndex + codeUnitLengthAt(value, rawIndex));
        if (!isCombiningMark(nextChar)) {
          break;
        }
        segment += nextChar;
        rawIndex += nextChar.length;
      }
      clusters.push({ segment, start, end: rawIndex });
    }
    return clusters;
  }

  function isCombiningMark(char) {
    return /[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\ufe20-\ufe2f]/u.test(char);
  }

  function codeUnitLengthAt(value, index) {
    const codePoint = value.codePointAt(index);
    return codePoint && codePoint > 0xffff ? 2 : 1;
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
    if (isGlobalAnnotation(annotation)) {
      return firstReviewRow();
    }
    const sourceElement = firstElementForSourceRange(sourceRangeForAnnotation(annotation));
    if (sourceElement) {
      return sourceElement.closest("[data-mdfh-review-row]");
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
      if (annotation && isGlobalAnnotation(annotation)) {
        return { row: firstReviewRow(), offset: 0 };
      }
      const sourceElement = annotation
        ? firstElementForSourceRange(sourceRangeForAnnotation(annotation))
        : null;
      if (sourceElement) {
        const row = sourceElement.closest("[data-mdfh-review-row]");
        return row ? { row, offset: offsetForMarker(sourceElement, row) } : null;
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
    if (isGlobalAnnotation(annotation)) {
      return 0;
    }
    const marker = firstMarkerForAnnotation(annotation.id);
    if (marker) {
      return offsetForMarker(marker, row);
    }
    const sourceElement = firstElementForSourceRange(sourceRangeForAnnotation(annotation));
    return sourceElement ? offsetForMarker(sourceElement, row) : 0;
  }

  function offsetForMarker(marker, row) {
    return Math.max(0, marker.getBoundingClientRect().top - row.getBoundingClientRect().top);
  }

  function editAnnotation(annotation) {
    state.editingId = annotation.id;
    state.selectedQuote = annotationQuote(annotation) || "";
    state.selectedSourceRange = sourceRangeForAnnotation(annotation);
    state.documentMode = isGlobalAnnotation(annotation);
    state.draftComment = annotation.comment || "";
    clearPendingSpans();
    renderAnnotations();
    locateAnnotation(annotation);
    focusEditor();
  }

  function locateAnnotation(annotation) {
    const sourceElement = firstElementForSourceRange(sourceRangeForAnnotation(annotation));
    if (sourceElement) {
      flashElement(sourceElement);
      return;
    }
    const quote = annotationQuote(annotation);
    if (quote) {
      locateQuote(quote, annotation.id);
      return;
    }
    const row = firstReviewRow();
    if (row) {
      flashElement(row);
    }
  }

  function locateQuote(quote, annotationId = "") {
    const ranges = findQuoteRanges(quote);
    if (ranges.length !== 1) {
      toast(ranges.length === 0 ? t("reviewUnderlineUnavailable") : t("reviewUnderlineAmbiguous"));
      return;
    }
    let target = annotationId ? firstMarkerForAnnotation(annotationId) : null;
    if (!target && window.find && window.find(quote)) {
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
        const node = selection.getRangeAt(0).startContainer;
        target = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
        selection.removeAllRanges();
      }
    }
    if (!target || !content.contains(target)) {
      toast(t("reviewQuoteUnresolved"));
      return;
    }
    const block = target.closest("p, li, blockquote, pre, h1, h2, h3, h4, h5, h6") || target;
    flashElement(block);
  }

  function flashElement(element) {
    element.scrollIntoView({ behavior: "smooth", block: "center" });
    element.classList.add("mdfh-review-flash");
    setTimeout(() => element.classList.remove("mdfh-review-flash"), 1600);
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

  function sourceRangeForSelection(range) {
    const startElement = elementForNode(range.startContainer);
    const endElement = elementForNode(range.endContainer);
    return mergeSourceRanges(
      sourceRangeForElement(startElement),
      sourceRangeForElement(endElement),
    );
  }

  function mergeSourceRanges(startRange, endRange) {
    if (!startRange) {
      return endRange;
    }
    if (!endRange) {
      return startRange;
    }
    return {
      start_line: Math.min(startRange.start_line, endRange.start_line),
      end_line: Math.max(startRange.end_line, endRange.end_line),
    };
  }

  function sourceRangeForElement(element) {
    if (!element || !element.closest) {
      return null;
    }
    const sourceElement = element.closest("[data-mdfh-source-lines]");
    if (!sourceElement || !content.contains(sourceElement)) {
      return null;
    }
    return parseSourceRange(sourceElement.dataset.mdfhSourceLines);
  }

  function sourceRangeForAnnotation(annotation) {
    return annotation ? parseSourceRange(annotation.source_range) : null;
  }

  function parseSourceRange(value) {
    if (!value) {
      return null;
    }
    if (typeof value === "string") {
      const match = value.match(/^(\d+):(\d+)$/);
      if (!match) {
        return null;
      }
      return normalizeSourceRange(Number(match[1]), Number(match[2]));
    }
    if (typeof value === "object") {
      return normalizeSourceRange(Number(value.start_line), Number(value.end_line));
    }
    return null;
  }

  function normalizeSourceRange(startLine, endLine) {
    if (!Number.isInteger(startLine) || !Number.isInteger(endLine)) {
      return null;
    }
    if (startLine === 0 && endLine === 0) {
      return { start_line: 0, end_line: 0 };
    }
    if (startLine <= 0 || endLine < startLine) {
      return null;
    }
    return { start_line: startLine, end_line: endLine };
  }

  function sourceRangeLabel(sourceRange) {
    if (!sourceRange) {
      return "";
    }
    if (sourceRange.start_line === 0 && sourceRange.end_line === 0) {
      return "L0";
    }
    if (sourceRange.start_line === sourceRange.end_line) {
      return `L${sourceRange.start_line}`;
    }
    return `L${sourceRange.start_line}-L${sourceRange.end_line}`;
  }

  function firstElementForSourceRange(sourceRange) {
    if (!sourceRange || (sourceRange.start_line === 0 && sourceRange.end_line === 0)) {
      return null;
    }
    const candidates = Array.from(content.querySelectorAll("[data-mdfh-source-lines]"))
      .map((element) => ({ element, range: parseSourceRange(element.dataset.mdfhSourceLines) }))
      .filter((item) => item.range && item.range.start_line <= sourceRange.start_line && item.range.end_line >= sourceRange.start_line)
      .sort((left, right) => sourceRangeSpan(left.range) - sourceRangeSpan(right.range));
    return candidates.length ? candidates[0].element : null;
  }

  function sourceRangeSpan(sourceRange) {
    return sourceRange ? sourceRange.end_line - sourceRange.start_line : Number.MAX_SAFE_INTEGER;
  }

  function isGlobalAnnotation(annotation) {
    const sourceRange = sourceRangeForAnnotation(annotation);
    return Boolean(
      annotation &&
      sourceRange &&
      sourceRange.start_line === 0 &&
      sourceRange.end_line === 0
    );
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
      if (annotation) {
        activateCard(annotation.id);
        locateAnnotation(annotation);
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
  window.addEventListener("mdfh:localechange", () => {
    applyTranslations(document);
    renderAnnotations();
  });
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
