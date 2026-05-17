from importlib import import_module
from pathlib import Path


def test_sample_site_fixture_is_available(sample_site_copy):
    assert (sample_site_copy / "README.md").exists()
    assert (sample_site_copy / "guide" / "intro.md").exists()


def test_package_import_is_available():
    module = import_module("md_for_human")
    assert module.__name__ == "md_for_human"


def test_pyproject_declares_runtime_render_dependencies():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    contents = pyproject.read_text(encoding="utf-8")

    assert 'name = "md-for-human"' in contents
    assert 'md-for-human = "md_for_human.cli:main"' in contents
    assert '"markdown-it-py>=3.0,<4"' in contents
    assert '"pygments>=2.17,<3"' in contents


def test_pyproject_declares_static_quality_tools():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    contents = pyproject.read_text(encoding="utf-8")

    assert '"ruff>=0.8,<1"' in contents
    assert '"mypy>=1.13,<2"' in contents


def test_agent_skill_entrypoints_share_root_skill_document():
    project_root = Path(__file__).resolve().parents[1]
    root_skill = project_root / "SKILL.md"
    root_contents = root_skill.read_text(encoding="utf-8")

    for relative_path in (
        ".codex/skills/md-for-human/SKILL.md",
        ".claude/skills/md-for-human/SKILL.md",
    ):
        skill_entrypoint = project_root / relative_path
        assert skill_entrypoint.read_text(encoding="utf-8") == root_contents
