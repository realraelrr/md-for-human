---
name: md-for-human
description: Use when a user asks to render agent-authored Markdown, notes, reports, plans, handoffs, wiki exports, or documentation folders into a human-friendly HTML reading site.
---

# md-for-human

Render Markdown into a navigable static HTML site. Keep the Markdown as source; do not
rewrite, summarize, or restyle the content unless the user explicitly asks.

## Run

1. Pick a Markdown file or directory.
2. Choose an output directory outside the input tree, usually
   `${TMPDIR:-/tmp}/md-for-human-preview`.
3. Unless the user explicitly says they are opening the document only for
   reading, start review mode directly. This builds the site, opens the local
   review UI, and enables source hot reload:

```bash
md-for-human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --review --overwrite
```

4. If the user explicitly asks only to read the document, build a plain static
   preview instead:

```bash
md-for-human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --overwrite
```

If `md-for-human` is not found, use the conda environment directly:

```bash
conda run -n md-for-human md-for-human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --review --overwrite
```

Inside this repository checkout, the module command is also valid:

```bash
python -m md_for_human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --overwrite
```

Use `--no-open` only for headless work, CI, artifact-only handoff, or browser-open
failures. Add `--verify` when structural checks matter. Prefer `--strict` for
agent handoff because it combines `--verify --fail-on-warning --no-open`.

## Review Artifacts

Agents can review generated sites without launching a browser by writing the v2
review artifact and validating it:

1. Build the site with `--strict` or build normally and keep the output directory.
2. Read `OUTPUT_DIR/.md-for-human/manifest.json`.
3. Write `OUTPUT_DIR/.md-for-human/review/annotations.json`.
4. Run:

```bash
md-for-human --validate-review OUTPUT_DIR
```

Use `--fail-on-warning` only for automation that deliberately treats non-core
diagnostics as blocking.

Humans can create the same artifact through the local browser review UI:

```bash
md-for-human --review OUTPUT_DIR
```

The UI is a protocol client over the generated site. It lets the reviewer select
rendered text, write one free-text comment, and save to the same
`annotations.json`. The only visual marker is an underline/highlight anchor plus
the right comment rail. Behind that visual anchor, the UI records the full
Markdown source line range covered by the selection when available. If no text is
selected, the UI writes a whole-document comment with
`source_range: {"start_line": 0, "end_line": 0}`.

The review server binds to `127.0.0.1`, uses a per-session token for
`/__mdfh_review/` API calls, does not enable CORS, and only writes
`.md-for-human/review/annotations.json` plus generated `review.md`. It never
rewrites source Markdown or generated HTML. Review HTML responses use a
nonce-based Content Security Policy so only md-for-human's own inline scripts
and styles can execute; Markdown raw scripts, inline event handlers, and
`javascript:` links remain visible in the rendered document but are blocked by
the browser in review mode. Plain static builds do not add this CSP.

`annotations.json` is the fact source; `review.md` is generated from it. Do not
edit `review.md` manually. Agents should read `review.md` first. Read
`annotations.json` only when exact source coordinates are needed.

For v2, the agent-facing fields are intentionally small:

```json
{
  "source_path": "guide/setup.md",
  "source_range": {"start_line": 12, "end_line": 14},
  "comment": "Explain the exact setup command and failure mode."
}
```

Use 1-based closed Markdown line numbers for normal comments. Use
`source_range: {"start_line": 0, "end_line": 0}` for a whole-document comment.
Do not split edit intent into action fields; write deletion, insertion,
replacement, and rationale in the natural-language `comment`.

The tool fills bookkeeping fields such as `id`, `schema_version`,
`source_manifest`, and `source_sha256` during `--validate-review` or browser
save. Browser-created comments may include `meta.quote` for human visual
context. Agents can ignore `meta`; `source_path + source_range` is the primary
locator. Manifest `documents[]` entries include `source_line_count`, and review
validation rejects ranges that point past the source Markdown. Review mode
archives old active comments when the source Markdown changes.

## Setup

Create the project environment if it is missing:

```bash
conda env create -f environment.yml
```

Refresh the editable install only inside an activated conda or virtualenv environment:

```bash
python -m pip install -e ".[dev]" --no-build-isolation
```

Do not run editable install against system Python. Dependencies such as `markdown-it-py`
and `pygments` come from the conda environment or editable install.

## Check

Before claiming completion:

- command exited successfully
- stdout includes `Built site at: ...`
- reported entry page exists and starts with `<!DOCTYPE html>`
- entry page contains site navigation
- `.md-for-human/manifest.json` exists in the output directory
- manifest `documents` maps reviewable pages to source paths, source line counts, and source sha256 values
- `--verify` passed if you used it, or `--strict` passed for agent handoff
- `--validate-review` passed if you are handing back review annotations
- artifacts created by `--review` and artifacts created by agents use the same schema

Use the reported entry page or manifest `entry_page`; directory builds usually use
`index.html`, while single-file builds use the source file basename.

## Recovery

- Report warnings instead of hiding them.
- If `--fail-on-warning` makes the command fail, say the site was generated but rejected by
  the strict warning policy.
- If verification fails, inspect the reported missing page, asset, or link before reporting
  success.
- If macOS browser opening emits `osascript` or `Connection Invalid` noise but the command
  exits successfully and prints `Built site at: ...`, treat the build as successful, mention
  the browser-open caveat, and use `--no-open` for restricted reruns.
- If the command is missing, try `python -m md_for_human`, then create or refresh the
  `md-for-human` environment.

## Reply

```text
Entry page: ...
Output directory: ...
Browser opened: yes/no
Warnings: none / ...
Verification: passed / not run / failed (...)
```

Do not paste generated HTML. Do not claim visual quality unless you actually opened or
visually inspected the page.

## If You Modify The Tool

Run:

```bash
python -m pytest -q
python -m md_for_human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --strict
md-for-human --help
```

## Safety

- Never put output inside the input tree.
- Prefer `${TMPDIR:-/tmp}/...` for previews; macOS sandboxes may block plain `/tmp`.
- Use `--overwrite` only for output directories created for this conversion.
- The tool copies referenced local assets only; unreferenced files are not copied.
  Markdown links/images and raw HTML `href`/`src` targets are included.
