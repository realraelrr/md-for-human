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
- `--verify` passed if you used it, or `--strict` passed for agent handoff

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
