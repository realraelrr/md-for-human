# md-for-human

Render agent-authored Markdown into a navigable static HTML reading site.

[中文 README](README.zh-CN.md)

`md-for-human` is an agent output bridge: LLM agents keep Markdown as the source
of truth, while humans get a local static site that is easier to scan, share,
and verify.

`md-for-human` keeps Markdown as the editable source and produces HTML as the
readable artifact. It supports folder and single-file inputs, sidebar navigation,
page tables of contents, previous/next links, local Markdown link rewriting,
referenced asset copying from Markdown and raw HTML, code highlighting, verification,
and a manifest for agent handoff.

It does not rewrite, summarize, or embellish the Markdown.

## Install

Current install paths:

| Use case | Command | Status |
| --- | --- | --- |
| Recommended local use | `conda env create -f environment.yml` then `conda activate md-for-human` | Supported from a repository checkout |
| Development install | `python -m pip install -e ".[dev]" --no-build-isolation` | Supported inside an activated conda or virtualenv |
| Run without activation | `conda run -n md-for-human md-for-human ...` | Supported after environment creation |
| PyPI / pipx / uv tool | `pipx install md-for-human` or `uv tool install md-for-human` | Not available until the project is published to PyPI |

Create and activate the project environment from a checkout:

```bash
conda env create -f environment.yml
conda activate md-for-human
```

Refresh an editable install only inside an activated conda or virtualenv:

```bash
python -m pip install -e ".[dev]" --no-build-isolation
```

Do not run editable install against system Python.

The PyPI project URL currently returns 404:
<https://pypi.org/pypi/md-for-human/json>.

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

Validate review annotations written by a human or agent against an existing generated site:

```bash
md-for-human --validate-review /tmp/md-for-human-sample-site
```

Build and start local review mode with source hot reload:

```bash
md-for-human path/to/agent-output -o /tmp/md-for-human-review --review --overwrite
```

When `--review` builds to an existing custom output directory, add `--overwrite`.
Reviewing an existing generated site with `--review OUTPUT_DIR` does not rebuild
and does not require `--overwrite`.

Start a local browser review UI for an existing generated site without source hot reload:

```bash
md-for-human --review /tmp/md-for-human-sample-site
```

Use `--no-open` for headless runs, `--verify` for structural checks, and
`--fail-on-warning` for strict automation. Use `--strict` for agent handoff; it
combines `--verify --fail-on-warning --no-open`.

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
  "manifest_schema_version": "mdfh-manifest-v1",
  "tool_name": "md-for-human",
  "tool_version": "0.2.0",
  "entry_page": "index.html",
  "pages": ["index.html", "guide/setup.html"],
  "documents": [
    {
      "page": "index.html",
      "source_path": "README.md",
      "source_line_count": 42,
      "source_sha256": "..."
    },
    {
      "page": "guide/setup.html",
      "source_path": "guide/setup.md",
      "source_line_count": 18,
      "source_sha256": "..."
    }
  ],
  "copied_assets": ["images/diagram.png"],
  "warnings": []
}
```

For single-file inputs, `entry_page` uses the source file basename instead of
`index.html`. The full manifest and review artifact contract is documented in
[`docs/protocol.md`](docs/protocol.md).

## Review Artifacts

Review annotations are optional sidecar artifacts under `.md-for-human/review/`.
They do not modify source Markdown or generated HTML. `review.md` is the
generated summary agents should read first; `annotations.json` is the
machine-readable fact source when exact coordinates are needed.

The v2 protocol is intentionally small: each annotation records a Markdown
location and one free-text comment. Agents should treat
`source_path + source_range` as the primary locator. Whole-page comments use
`source_range: {"start_line": 0, "end_line": 0}`. Full field definitions,
validation rules, and agent consumption rules live in
[`docs/protocol.md`](docs/protocol.md).

Validate review artifacts with:

```bash
md-for-human --validate-review path/to/output
```

Add `--fail-on-warning` only when non-core diagnostics should fail automation.

Use the browser review UI when a human wants paper-style annotations:

```bash
md-for-human path/to/input -o path/to/output --review
```

`--review OUTPUT_DIR` remains available for existing generated sites, but it
cannot hot reload source changes because the server does not know the source
root in that mode.

The review server binds to `127.0.0.1`, injects the review UI at request time,
and leaves generated HTML files unchanged. API routes live under
`/__mdfh_review/`, require a per-session token, do not enable CORS, and only
write `.md-for-human/review/annotations.json` plus the derived `review.md`.
Review HTML responses use a nonce-based Content Security Policy that allows only
md-for-human's own inline scripts and styles to run; Markdown raw HTML remains
rendered for inspection, but raw Markdown scripts, inline event handlers, and
`javascript:` links are blocked in review mode. Plain static builds do not add
that CSP and continue to preserve raw HTML as authored. The UI uses an
underline/highlight anchor plus inline and unplaced comment controls. Rendered
Markdown blocks carry `data-mdfh-source-lines`, letting the browser save the
selected Markdown line range. The server rejects schema, source-path, and
source-range hard failures before writing. Missing or repeated quote anchors do
not block handoff when a valid source range is present because line numbers are
the primary locator.
When a reviewed Markdown source changes, active comments for the previous source
hash move to `.md-for-human/review/archive.json` and are removed from the active
`review.md`.

## Visual Evidence

These screenshots are generated from the sample fixture with the same strict
sample command documented below.

![Reading site](docs/assets/reading-site.png)

![Review mode](docs/assets/review-mode.png)

## Agent Skill

The agent-facing runbook lives in [`SKILL.md`](SKILL.md). The protocol contract
lives in [`docs/protocol.md`](docs/protocol.md). Codex and Claude skill
entrypoints in `.codex/skills/md-for-human/` and `.claude/skills/md-for-human/`
point to `SKILL.md`.

## Development

Canonical checks:

```bash
ruff check .
mypy --strict src
python -m pytest -q
python -m md_for_human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --strict
md-for-human --help
```

The package uses a `src/` layout. The top-level `md_for_human/` package is a
bootstrap shim so `python -m md_for_human` works from a checkout before install.

## Safety

The CLI rejects output paths that are the input path, inside the input tree, or
an ancestor of the input. Custom output paths require `--overwrite`.

Only referenced local assets are copied. Markdown links/images and raw HTML
`href`/`src` targets are included. Missing, symlinked, out-of-root, and non-file
assets produce warnings.

Plain static HTML output is trusted local content, not an HTML sanitizer. Do not
open generated sites from untrusted Markdown unless using review mode or an
external sandbox.

## License

MIT. See [LICENSE](LICENSE).
