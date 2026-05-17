---
name: md-for-human
description: Use this when the user wants agent-generated Markdown, notes, reports, plans, wiki exports, or documentation folders turned into a human-friendly HTML reading site. Trigger for phrases like "make this markdown easier to read", "render these agent docs", "convert this md folder to HTML", "humanize these notes", or when a deliverable is long Markdown that would be clearer as navigable HTML.
---

# md-for-human

Use this skill to convert agent-written Markdown into an HTML site that is easier for humans to
read, scan, and understand.

## When To Use

Use `md-for-human` when the user has Markdown artifacts such as:

- agent reports, plans, reviews, or handoffs
- long Markdown notes that need a readable presentation
- folders of generated docs with cross-links
- Markdown deliverables that should be opened in a browser

Do not use this skill for editing the Markdown content itself unless the user asks for rewriting.
The tool's job is presentation: preserve the source content and render it into navigable HTML.

## Expected Repository Setup

The tool is a Python package with:

- console command: `md-for-human`
- module command: `python -m md_for_human`
- source package: `src/md_for_human`

Prefer an activated project environment. If none is active, use the conda environment from the
repository:

```bash
conda env create -f environment.yml
conda run -n md-for-human md-for-human --help
```

For an existing checkout, refresh the editable install when imports or console scripts are stale:

```bash
python -m pip install -e . --no-build-isolation
```

## Workflow

1. Identify the Markdown file or directory the user wants rendered.
2. Choose an output directory outside the input tree, usually under `/tmp` for previews.
3. Run the converter with `--no-open` when working headlessly, or omit it when the user wants the
   browser opened automatically.
4. Report the generated entry page path and any warnings.
5. If changing the tool itself, run the verification commands before claiming completion.

## Commands

Preview a Markdown directory:

```bash
md-for-human path/to/agent-output -o /tmp/md-for-human-preview --overwrite --no-open
```

Preview a single Markdown file:

```bash
md-for-human path/to/report.md -o /tmp/report-html --overwrite --no-open
```

Run from source without relying on the console script:

```bash
python -m md_for_human path/to/agent-output -o /tmp/md-for-human-preview --overwrite --no-open
```

## Verification For Tool Changes

Run:

```bash
python -m pytest -q
python -m md_for_human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --no-open
md-for-human --help
```

Success means tests pass, the smoke site builds, and the CLI help displays `--output`,
`--no-open`, and `--overwrite`.

## Safety Rules

- Never choose an output path inside the input tree.
- Use `/tmp/...` for preview builds unless the user explicitly requests a durable output path.
- Use `--overwrite` only for output directories created for this conversion.
- Treat warnings about out-of-tree links or symlinks as useful handoff information.
