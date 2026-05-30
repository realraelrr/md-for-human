(() => {
  function createReviewCommentsRenderer({
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
    getPageAnnotations,
    getCurrentAnnotations,
  }) {
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

    function renderAnnotations() {
      sourceLocator.unwrapSavedMarkers();
      clearCommentColumns();
      state.anchorState = new Map();
      const annotations = getPageAnnotations();
      annotations
        .filter((annotation) => artifact.annotationQuote(annotation))
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
        const row = sourceLocator.rowForAnnotation(annotation);
        if (!row) {
          return;
        }
        const status = state.anchorState.get(annotation.id);
        if (status && status.warning && !sourceLocator.sourceRangeForAnnotation(annotation)) {
          return;
        }
        addRowItem(itemsByRow, row, {
          kind: "card",
          annotation,
          offset: sourceLocator.offsetForAnnotation(annotation, row),
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
      const sourceRange = sourceLocator.sourceRangeForAnnotation(annotation);
      const lineLabel = sourceLocator.sourceRangeLabel(sourceRange);
      const anchorLabel = [lineLabel, artifact.annotationQuote(annotation) || t("reviewDocumentComment")].filter(Boolean).join(" · ");
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
      const lineLabel = sourceLocator.sourceRangeLabel(state.selectedSourceRange);
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
        return (
          artifact.annotationQuote(annotation) &&
          status &&
          status.warning &&
          !sourceLocator.sourceRangeForAnnotation(annotation)
        );
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
                <small>${escapeHtml(artifact.annotationQuote(annotation) || t("reviewDocumentComment"))}</small>
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
      const ranges = sourceLocator.findQuoteRanges(artifact.annotationQuote(annotation));
      if (ranges.length !== 1) {
        state.anchorState.set(annotation.id, {
          warning: ranges.length === 0 ? t("reviewUnderlineUnavailable") : t("reviewUnderlineAmbiguous"),
        });
        return;
      }
      sourceLocator.wrapSegments(ranges[0].segments, { annotationId: annotation.id });
      state.anchorState.set(annotation.id, {});
    }

    function currentEditorTarget() {
      if (!state.editingId && !state.selectedQuote && !state.documentMode) {
        return null;
      }
      if (state.documentMode) {
        return { row: sourceLocator.firstReviewRow(), offset: 0 };
      }
      const pending = state.pendingSpans.find(Boolean);
      if (pending) {
        const row = pending.closest("[data-mdfh-review-row]");
        return row ? { row, offset: sourceLocator.offsetForMarker(pending, row) } : null;
      }
      if (state.editingId) {
        const annotation = getCurrentAnnotations().find((item) => item.id === state.editingId);
        if (annotation && sourceLocator.isGlobalAnnotation(annotation)) {
          return { row: sourceLocator.firstReviewRow(), offset: 0 };
        }
        const sourceElement = annotation
          ? sourceLocator.firstElementForSourceRange(sourceLocator.sourceRangeForAnnotation(annotation))
          : null;
        if (sourceElement) {
          const row = sourceElement.closest("[data-mdfh-review-row]");
          return row ? { row, offset: sourceLocator.offsetForMarker(sourceElement, row) } : null;
        }
        const marker = sourceLocator.firstMarkerForAnnotation(state.editingId);
        const row = marker ? marker.closest("[data-mdfh-review-row]") : sourceLocator.firstReviewRow();
        return row ? { row, offset: marker ? sourceLocator.offsetForMarker(marker, row) : 0 } : null;
      }
      return null;
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

    return Object.freeze({
      prepareReviewLayout,
      renderAnnotations,
      activateCard,
      focusCard,
    });
  }

  window.mdfhReviewCommentsRenderer = Object.freeze({
    create: createReviewCommentsRenderer,
  });
})();
