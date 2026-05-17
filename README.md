# md-for-human

**Agents write Markdown. Humans read HTML. md-for-human bridges the gap.**

[中文 README](README.zh-CN.md)

Markdown as source. HTML as artifact. Deterministic rendering in between.

`md-for-human` treats Markdown as the durable agent-authored source of truth, and HTML as a
deterministic human-readable artifact. Agents keep writing the format they are best at editing,
diffing, reviewing, and reusing. Humans get a navigable HTML reading site with typography,
navigation, local link rewriting, asset handling, verification, and a machine-checkable manifest.

Stop spending agent tokens on HTML.

## Why This Exists

This is not a "Markdown vs HTML" project. It is a source/artifact boundary:

- **Markdown is the source of truth**: editable, diffable, reviewable, easy for agents to continue
  consuming and improving.
- **HTML is the rendered artifact**: readable, navigable, shareable, and suitable for visual
  inspection by humans.
- **The renderer is the compiler**: deterministic, scriptable, cheap to rerun, and easy to verify.

Letting an agent directly produce polished HTML mixes content expression and presentation in one
generation step. That can waste tokens, but the larger risk is semantic drift: the model may
reorganize, compress, decorate, or reinterpret the source while trying to make it look good.

`md-for-human` takes the opposite stance:

> No reinterpretation by default. No semantic drift. Render the Markdown you wrote.

## What It Does

Given a Markdown file or folder, `md-for-human` builds a static HTML reading site:

- folder/site rendering
- browser preview by default
- sidebar navigation and page table of contents
- previous/next page browsing
- local Markdown link rewriting
- referenced asset copying with safety checks
- syntax highlighting for code blocks
- structural verification with `--verify`
- warning-aware automation with `--fail-on-warning`
- `.md-for-human/manifest.json` for agent audit and handoff

It does not rewrite your Markdown, summarize it, embellish it, or ask an agent to redesign it.

## Install

Use the project conda environment when creating a fresh setup:

```bash
conda env create -f environment.yml
conda activate md-for-human
```

In an existing local development environment, refresh the editable install from this repository root:

```bash
python -m pip install -e . --no-build-isolation
```

## Usage

Build a site from the sample fixture:

```bash
md-for-human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --verify --no-open
```

Build from a directory and open the result:

```bash
md-for-human path/to/agent-output
```

Build from one Markdown file:

```bash
md-for-human path/to/notes.md -o /tmp/notes-site --no-open
```

Run through conda without activating the environment:

```bash
conda run -n md-for-human md-for-human path/to/agent-output --no-open
```

## Agent-Friendly Output

Successful builds print a stable summary:

```text
Built site at: ...
Output directory: ...
Pages: ...
Assets copied: ...
Warnings: ...
Browser opened: yes/no
Verification: passed
```

Every build also writes `.md-for-human/manifest.json` inside the output directory:

```json
{
  "entry_page": "index.html",
  "pages": ["index.html", "guide/setup.html"],
  "copied_assets": ["images/diagram.png"],
  "warnings": []
}
```

Use `--verify` for structural checks and `--fail-on-warning` when warnings should make automation
fail.

## Skill Integration

This repository includes a Codex/agent skill at
[`.codex/skills/md-for-human/SKILL.md`](.codex/skills/md-for-human/SKILL.md).

Use the skill when an agent needs to turn Markdown deliverables into a human-readable HTML site.
The skill is the agent-facing protocol; JSON/manifest output is only supporting evidence for
verification and handoff.

## Development

Canonical checks:

```bash
python -m pytest -q
python -m md_for_human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --verify --no-open
md-for-human --help
```

The package uses a `src/` layout. The top-level `md_for_human/` package is a local bootstrap shim
so `python -m md_for_human` works from a checkout before installation.

## Safety Notes

Existing default output directories are replaced automatically. Existing custom output paths
require `--overwrite` and are deleted only after validation. The CLI rejects output paths that are
the input directory, inside the input directory, an ancestor of the input directory, the input
Markdown file, or an ancestor of the input Markdown file. It also protects against final-output
symlink deletion and symlinked parent aliases that would point back into the input tree.

Referenced assets are copied only when they resolve safely inside the input tree. Missing,
symlinked, out-of-root, and non-file assets produce warnings.

## License

MIT. See [LICENSE](LICENSE).
