(() => {
  function createReviewSourceLocator({ content, t, toast, annotationQuote, cssEscape }) {
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

    function markRange(range) {
      const spans = wrapSegments(segmentsForRange(range), { pending: true });
      window.getSelection()?.removeAllRanges();
      return spans;
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

    function unwrapSpans(spans) {
      spans.forEach((span) => unwrapSpan(span));
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
        .filter((item) => (
          item.range &&
          item.range.start_line <= sourceRange.start_line &&
          item.range.end_line >= sourceRange.start_line
        ))
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

    return Object.freeze({
      isRangeInsideReviewBody,
      markRange,
      unwrapSpans,
      unwrapSpan,
      unwrapSavedMarkers,
      findQuoteRanges,
      wrapSegments,
      rowForAnnotation,
      firstReviewRow,
      firstMarkerForAnnotation,
      offsetForAnnotation,
      offsetForMarker,
      locateAnnotation,
      sourceRangeForSelection,
      sourceRangeForElement,
      sourceRangeForAnnotation,
      parseSourceRange,
      normalizeSourceRange,
      sourceRangeLabel,
      firstElementForSourceRange,
      isGlobalAnnotation,
    });
  }

  window.mdfhReviewSourceLocator = Object.freeze({
    create: createReviewSourceLocator,
  });
})();
