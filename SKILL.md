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
3. For interactive preview, let the tool open the browser:

```bash
md-for-human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --overwrite
```

If `md-for-human` is not found, use the conda environment directly:

```bash
conda run -n md-for-human md-for-human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --overwrite
```

Inside this repository checkout, the module command is also valid:

```bash
python -m md_for_human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --overwrite
```

Use `--no-open` only for headless work, CI, artifact-only handoff, or browser-open
failures. Add `--verify` when structural checks matter. Prefer `--strict` for
agent handoff because it combines `--verify --fail-on-warning --no-open`.

## Review Artifacts

Agents can review generated sites without launching a browser by writing the v1
review artifact and validating it:

1. Build the site with `--strict` or build normally and keep the output directory.
2. Read `OUTPUT_DIR/.md-for-human/manifest.json`.
3. Write `OUTPUT_DIR/.md-for-human/review/annotations.json`.
4. Run:

```bash
md-for-human --validate-review OUTPUT_DIR
```

Use `--fail-on-warning` when ambiguous anchors should reject the handoff.

Humans can create the same artifact through the local browser review UI:

```bash
md-for-human --review OUTPUT_DIR
```

The UI is a protocol client over the generated site. It lets the reviewer select
rendered text, choose `comment`, `suggest_delete`, `suggest_insert`, or
`suggest_replace`, fill the required note, and save to the same
`annotations.json`. For `suggest_insert`, the selected text is only the insertion
anchor; the inserted text goes in `suggested_text`, with `placement` set to
`before` or `after`.

The review server binds to `127.0.0.1`, uses a per-session token for
`/__mdfh_review/` API calls, does not enable CORS, and only writes
`.md-for-human/review/annotations.json` plus generated `review.md`. It never
rewrites source Markdown or generated HTML.

`annotations.json` is the fact source; `review.md` is generated from it. Do not
edit `review.md` manually. The v1 annotation types are `comment`, `suggest_delete`,
`suggest_insert`, and `suggest_replace`. Every annotation must include `id`,
`type`, `page`, `source_path`, `quote`, `note`, `created_at`, and `updated_at`.
`suggest_insert` also needs `placement` and `suggested_text`; its `quote` is only
the insertion anchor, not text to edit or remove. `suggest_replace` also needs
`suggested_text`.

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
- manifest `documents` maps reviewable pages to source paths and source sha256 values
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
