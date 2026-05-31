# md-for-human Protocol

This document defines the agent handoff contract for generated sites and review
artifacts. Generated outputs without the current manifest metadata are not
supported by review validation; rebuild them with the current tool.

## Build Manifest v1

Every build writes `.md-for-human/manifest.json` inside the output directory.
The manifest schema is `mdfh-manifest-v1`.

```json
{
  "manifest_schema_version": "mdfh-manifest-v1",
  "tool_name": "md-for-human",
  "tool_version": "0.2.1",
  "entry_page": "index.html",
  "pages": ["index.html", "guide/setup.html"],
  "documents": [
    {
      "page": "index.html",
      "source_path": "README.md",
      "source_line_count": 42,
      "source_sha256": "..."
    }
  ],
  "copied_assets": ["images/diagram.png"],
  "warnings": []
}
```

Fields:

- `manifest_schema_version`: must be `mdfh-manifest-v1`.
- `tool_name`: must be `md-for-human`.
- `tool_version`: non-empty md-for-human package version that generated the site.
- `entry_page`: relative HTML page to open first.
- `pages`: relative HTML pages generated for the site.
- `documents`: reviewable Markdown documents mapped to generated pages.
- `documents[].page`: generated HTML page for the source document.
- `documents[].source_path`: relative Markdown source path.
- `documents[].source_line_count`: number of lines in the source Markdown.
- `documents[].source_sha256`: SHA-256 hash of the source Markdown bytes.
- `copied_assets`: referenced local assets copied into the output tree.
- `warnings`: build warnings that should be surfaced to agents and humans.

Synthetic landing pages may appear in `pages` but are not listed in
`documents` because they are not Markdown source files and are not valid review
targets.

## Review Annotation v2

Review artifacts live under `.md-for-human/review/`. `annotations.json` is the
machine-readable fact source; `review.md` is generated from it and should not be
edited manually. The review schema is `mdfh-review-v2`.

```json
{
  "schema_version": "mdfh-review-v2",
  "source_manifest": ".md-for-human/manifest.json",
  "annotations": [
    {
      "id": "ann_123",
      "source_path": "guide/setup.md",
      "source_range": {"start_line": 12, "end_line": 14},
      "source_sha256": "...",
      "comment": "Explain the exact setup command and failure mode.",
      "meta": {
        "quote": "Run the setup steps here."
      }
    }
  ]
}
```

Fields:

- `schema_version`: must be `mdfh-review-v2`.
- `source_manifest`: must be `.md-for-human/manifest.json`.
- `annotations`: list of review comments.
- `annotations[].id`: stable non-empty annotation id.
- `annotations[].source_path`: source Markdown path listed in manifest
  `documents`.
- `annotations[].source_range`: 1-based closed Markdown line range.
- `annotations[].source_sha256`: source hash used to archive stale comments.
- `annotations[].comment`: free-text human review instruction.
- `annotations[].meta.quote`: optional rendered quote for human visual context.

Use `source_range: {"start_line": 0, "end_line": 0}` for a whole-document
comment. Deletions, insertions, replacements, and rationale all belong in
`comment`; there are no action-specific fields.

Agents may write minimal annotation intent with only `source_path`,
`source_range`, and `comment`. `--validate-review` fills bookkeeping fields
such as `id`, `schema_version`, `source_manifest`, and `source_sha256`.

## Agent Consumption Rules

- Read `review.md` first for the human-facing summary.
- Read `annotations.json` when exact source coordinates are needed.
- Treat `source_path + source_range` as the primary locator.
- Treat `meta.quote` as optional visual context, not as the source of truth.
- Modify Markdown source files, then rebuild the site; do not edit generated
  HTML or generated `review.md`.
- When source Markdown changes, review mode archives active comments whose
  `source_sha256` no longer matches the manifest.

## Validation Rules

`--validate-review` fails on hard protocol errors:

- missing, invalid, or unsupported manifest metadata
- unsafe manifest page or source paths
- invalid manifest source hashes or line counts
- missing or unsupported review schema
- missing review source manifest pointer
- missing annotation ids, targets, ranges, or comments
- duplicate annotation ids
- annotation source paths not listed in manifest documents
- source ranges outside the source file line count

Missing or repeated quote anchors do not block handoff when a valid
`source_path + source_range` is present because line numbers are authoritative.

## Security Model

Plain static HTML output preserves raw HTML for faithful local rendering. It is
trusted local content, not an HTML sanitizer. Do not open generated sites from
untrusted Markdown unless using review mode or an external sandbox.

Review mode serves pages from `127.0.0.1`, uses a per-session token for
`/__mdfh_review/` API calls, does not enable CORS, and injects a nonce-based
Content Security Policy for HTML responses. Markdown raw scripts, inline event
handlers, and `javascript:` links remain visible in the rendered document but
are blocked by the browser in review mode.

## Non-Goals

md-for-human is an agent handoff tool, not a collaboration platform. Do not add:

- multi-user collaboration
- accounts
- rich text comments
- comment threads
- cloud sync
- permissions models
- built-in diffs
- patch application
