(() => {
  const SCHEMA_VERSION = "mdfh-review-v2";

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function ensureV2Artifact(artifact) {
    if (artifact && artifact.schema_version === SCHEMA_VERSION) {
      artifact.annotations = Array.isArray(artifact.annotations) ? artifact.annotations : [];
      artifact.annotations = artifact.annotations.map((annotation) => normalizeAnnotation(annotation));
      return artifact;
    }
    return {
      schema_version: SCHEMA_VERSION,
      source_manifest: ".md-for-human/manifest.json",
      annotations: [],
    };
  }

  function annotations(artifact) {
    if (!artifact || !Array.isArray(artifact.annotations)) {
      return [];
    }
    return artifact.annotations;
  }

  function annotationsForPage(artifact, sourcePath) {
    return annotations(artifact).filter((annotation) => annotation.source_path === sourcePath);
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

  window.mdfhReviewArtifact = Object.freeze({
    schemaVersion: SCHEMA_VERSION,
    clone,
    ensureV2Artifact,
    annotations,
    annotationsForPage,
    annotationMeta,
    normalizeAnnotation,
    annotationQuote,
  });
})();
