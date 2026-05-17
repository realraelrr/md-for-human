---
name: md-for-human
description: Use this whenever a user wants Markdown produced by agents, notes, reports, plans, handoffs, wiki exports, or documentation folders rendered into a human-friendly HTML reading site. Trigger for "make this markdown easier to read", "render these docs", "convert this md folder to HTML", "humanize these notes", or any long Markdown deliverable that would be clearer in a browser.
---

# md-for-human

Use this skill to preserve Markdown content while presenting it as a navigable HTML site for human
reading. Do not rewrite the source Markdown unless the user explicitly asks.

## Quick Workflow

1. Identify the Markdown file or directory to render.
2. Choose an output directory outside the input tree, usually `/tmp/md-for-human-preview`.
3. For interactive preview, let `md-for-human` open the browser by default. Use `--no-open`
   only for headless work, CI, or artifact-only handoff.
4. Add `--verify` when you need structural checks, and `--fail-on-warning` for strict delivery.
5. Report the entry page, output directory, browser-open state, and warnings.

## Command Selection

Prefer the console command:

```bash
md-for-human path/to/agent-output -o /tmp/md-for-human-preview --overwrite --no-open
```

If the command is unavailable but you are in the repository checkout, use the module command:

```bash
python -m md_for_human path/to/agent-output -o /tmp/md-for-human-preview --overwrite --no-open
```

If no Python is active, use the conda environment:

```bash
conda run -n md-for-human md-for-human path/to/agent-output -o /tmp/md-for-human-preview --overwrite --no-open
```

If that environment does not exist but another project environment exposes `md-for-human --help`,
use it and mention the choice in your handoff.

For stale imports or missing console scripts inside a checkout:

```bash
python -m pip install -e . --no-build-isolation
```

## Success Criteria

The task is complete when the command exits successfully, the entry page exists, structural checks
pass when requested, and the summary reports the expected page/asset/warning counts. A generated
manifest is written to `.md-for-human/manifest.json` inside the output directory.

## Post-Build Checks

Before telling the user the site is ready, verify:

- expected `.html` files exist
- `index.html` starts with `<!DOCTYPE html>` and contains site navigation
- local Markdown links point to `.html` pages
- referenced local assets exist in the output

The tool copies referenced local assets, not every unreferenced file in the source tree.

## Warnings And Recovery

- Normal preview: report warnings; do not hide them.
- Strict/automated handoff: use `--fail-on-warning`.
- If the command fails because warnings were treated as errors, say the site was generated but the
  command failed under strict warning policy.
- If verification fails, inspect the reported missing page/asset/link before claiming completion.
- If the console command is missing, try `python -m md_for_human`, then refresh the editable install.

## Final Reply Template

```text
Entry page: ...
Output directory: ...
Browser opened: yes/no
Warnings: none / ...
Verification: passed / not run / failed (...)
```

Do not paste generated HTML into the chat. Do not claim the visual design looks correct unless you
actually opened or visually inspected the page; structural verification is not visual inspection.

## Tool-Change Verification

If you modify `md-for-human` itself, run:

```bash
python -m pytest -q
python -m md_for_human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --verify --no-open
md-for-human --help
```

## Safety

- Never put the output path inside the input tree.
- Use `/tmp/...` for previews unless the user asks for a durable location.
- Use `--overwrite` only for output directories created for this conversion.
- Report warnings about out-of-tree links or skipped symlinks.
