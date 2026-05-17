# md-for-human

Turn agent-generated Markdown into human-friendly HTML reading sites.

Agents are good at producing Markdown, but long agent outputs can become hard for humans to scan,
compare, and understand in raw form. `md-for-human` takes a Markdown file or directory tree and
builds a polished static HTML site with navigation, readable typography, code highlighting, local
link rewriting, referenced assets, and previous/next browsing.

## Environment

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
md-for-human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --no-open
```

Build from a directory and open the result:

```bash
md-for-human path/to/agent-output
```

Build from one Markdown file:

```bash
md-for-human path/to/notes.md -o /tmp/notes-site --no-open
```

Without activating the environment, run through conda:

```bash
conda run -n md-for-human md-for-human path/to/agent-output --no-open
```

## Development

Canonical checks:

```bash
python -m pytest -q
python -m md_for_human tests/fixtures/sample_site -o /tmp/md-for-human-sample-site --overwrite --no-open
md-for-human --help
```

The package uses a `src/` layout. The top-level `md_for_human/` package is a local bootstrap shim
so `python -m md_for_human` works from a checkout before installation.

## Skill Integration

This repository includes a Codex/agent skill at
[`.codex/skills/md-for-human/SKILL.md`](.codex/skills/md-for-human/SKILL.md). Use that skill when
an agent needs to turn Markdown deliverables into a human-readable HTML site instead of treating
these notes as repository-level agent instructions.

## Safety Notes

Existing default output directories are replaced automatically. Existing custom output paths
require `--overwrite` and are deleted only after validation. The CLI rejects output paths that are
the input directory, inside the input directory, an ancestor of the input directory, the input
Markdown file, or an ancestor of the input Markdown file. It also protects against final-output
symlink deletion and symlinked parent aliases that would point back into the input tree.
