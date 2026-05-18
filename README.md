# md-for-human

Render agent-authored Markdown into a navigable static HTML reading site.

[中文 README](README.zh-CN.md)

`md-for-human` keeps Markdown as the editable source and produces HTML as the
readable artifact. It supports folder and single-file inputs, sidebar navigation,
page tables of contents, previous/next links, local Markdown link rewriting,
referenced asset copying, code highlighting, verification, and a manifest for
agent handoff.

It does not rewrite, summarize, or embellish the Markdown.

## Install

Create and activate the project environment:

```bash
conda env create -f environment.yml
conda activate md-for-human
```

Refresh an editable install only inside an activated conda or virtualenv:

```bash
python -m pip install -e ".[dev]" --no-build-isolation
```

Do not run editable install against system Python.

## Usage

Build from a directory and open the result:

```bash
md-for-human path/to/agent-output
```

Build from one Markdown file and open the result:

```bash
md-for-human path/to/notes.md -o /tmp/notes-site
```

Run without activating the environment:

```bash
conda run -n md-for-human md-for-human path/to/agent-output
```

Build and verify the sample fixture without opening a browser:

```bash
md-for-human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --verify --no-open
```

Use `--no-open` for headless runs, `--verify` for structural checks, and
`--fail-on-warning` for strict automation.

## Output Contract

Successful builds print:

```text
Built site at: ...
Output directory: ...
Pages: ...
Assets copied: ...
Warnings: ...
Browser opened: yes/no
```

When `--verify` is used, the summary also includes `Verification: passed` or
`Verification: failed`.

Every build writes `.md-for-human/manifest.json` inside the output directory:

```json
{
  "entry_page": "index.html",
  "pages": ["index.html", "guide/setup.html"],
  "copied_assets": ["images/diagram.png"],
  "warnings": []
}
```

For single-file inputs, `entry_page` uses the source file basename instead of
`index.html`.

## Agent Skill

The agent-facing protocol lives in [`SKILL.md`](SKILL.md). Codex and Claude skill
entrypoints in `.codex/skills/md-for-human/` and `.claude/skills/md-for-human/`
point to that file.

## Development

Canonical checks:

```bash
ruff check .
mypy --strict src
python -m pytest -q
python -m md_for_human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --verify --no-open
md-for-human --help
```

The package uses a `src/` layout. The top-level `md_for_human/` package is a
bootstrap shim so `python -m md_for_human` works from a checkout before install.

## Safety

The CLI rejects output paths that are the input path, inside the input tree, or
an ancestor of the input. Custom output paths require `--overwrite`.

Only referenced local assets are copied. Missing, symlinked, out-of-root, and
non-file assets produce warnings.

## License

MIT. See [LICENSE](LICENSE).
