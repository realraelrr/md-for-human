---
name: md-for-human
description: Use when a user asks to render agent-authored Markdown, notes, reports, plans, handoffs, wiki exports, or documentation folders into a human-friendly HTML reading or review site.
---

# md-for-human

Render Markdown into a local HTML site while keeping Markdown as the source of
truth. Do not rewrite, summarize, or restyle the content unless the user asks.

## Choose Mode

- Use **review mode** when the human may comment, approve, or hand feedback back
  to an agent.
- Use **plain static mode** when the user only wants to read, preview, export, or
  share trusted local content.
- Use **strict mode** for CI, headless handoff, or when returning artifacts to an
  agent without opening a browser.

## Commands

Pick an output directory outside the input tree, usually
`${TMPDIR:-/tmp}/md-for-human-preview`.

Review mode:

```bash
md-for-human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --review --overwrite
```

Plain static mode:

```bash
md-for-human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --overwrite
```

Strict/headless mode:

```bash
md-for-human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --overwrite --strict
```

Validate existing review annotations:

```bash
md-for-human --validate-review path/to/output
```

If `md-for-human` is missing, try the repo/module path, then the conda env:

```bash
python -m md_for_human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --overwrite
conda run -n md-for-human md-for-human path/to/input -o "${TMPDIR:-/tmp}/md-for-human-preview" --review --overwrite
```

## Review Artifacts

Review mode writes `.md-for-human/review/annotations.json` and generated
`review.md`. Agents should read `review.md` first and use `annotations.json`
only when exact source coordinates are needed.

The locator is `source_path + source_range`; `meta.quote` is visual context.
For the full manifest and review artifact contract, read `docs/protocol.md`.

## Verify

Before reporting success, check:

- command exited successfully
- stdout includes `Built site at: ...`
- output is outside the input tree
- `.md-for-human/manifest.json` exists
- `--strict` or `--verify` passed when this is an agent handoff
- `--validate-review` passed when returning review annotations

If you modify md-for-human itself, run the project checks from `README.md`.

## Safety

- Never place output inside the input tree.
- Use `--overwrite` only for output directories created for this conversion.
- Plain static HTML preserves raw HTML and is trusted local content, not a
  sanitizer. Use review mode or an external sandbox for untrusted Markdown.
- Report warnings; do not hide them.

## Reply

```text
Entry page: ...
Output directory: ...
Browser opened: yes/no
Warnings: none / ...
Verification: passed / not run / failed (...)
```

Do not paste generated HTML. Do not claim visual quality unless you actually
opened or inspected the page.
