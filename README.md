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

Validate review annotations written by a human or agent against an existing generated site:

```bash
md-for-human --validate-review /tmp/md-for-human-sample-site
```

Start a local browser review UI for an existing generated site:

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
  "entry_page": "index.html",
  "pages": ["index.html", "guide/setup.html"],
  "documents": [
    {
      "page": "index.html",
      "source_path": "README.md",
      "source_sha256": "..."
    },
    {
      "page": "guide/setup.html",
      "source_path": "guide/setup.md",
      "source_sha256": "..."
    }
  ],
  "copied_assets": ["images/diagram.png"],
  "warnings": []
}
```

For single-file inputs, `entry_page` uses the source file basename instead of
`index.html`.

## Review Artifacts

Review annotations are optional sidecar artifacts under `.md-for-human/review/`.
They do not modify source Markdown or generated HTML. `annotations.json` is the
machine-readable locator layer, and `review.md` is the generated summary agents
should read first.

The v2 protocol is intentionally small: each annotation records a location and a
free-text comment. The location is either a quote anchor in a reviewable page or
`scope: "document"` for a whole-page comment. Deletions, insertions,
replacements, and rationale all belong in the natural-language `comment`.
Legacy v1 artifacts remain validatable for read-only compatibility, but new
browser and agent workflows write `mdfh-review-v2`.

Validate review artifacts with:

```bash
md-for-human --validate-review path/to/output
```

Add `--fail-on-warning` when ambiguous or missing quote anchors should fail
automation.

Use the browser review UI when a human wants paper-style annotations:

```bash
md-for-human --review path/to/output
```

The review server binds to `127.0.0.1`, injects the review UI at request time,
and leaves generated HTML files unchanged. API routes live under
`/__mdfh_review/`, require a per-session token, do not enable CORS, and only
write `.md-for-human/review/annotations.json` plus the derived `review.md`.
The UI uses one marker, an underline/highlight anchor, plus a right comment rail.
The server rejects schema, page, and source-path hard failures before writing.
Missing or repeated quote anchors are saved as warnings so the communication
artifact remains available for agent handoff.

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

## License

MIT. See [LICENSE](LICENSE).
