"""Unit tests for scripts/workspace.py."""

from scripts.workspace import create_run_workspace


def test_create_run_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    template_dir = tmp_path / "context"
    template_dir.mkdir()
    template_file = template_dir / "shared_dependencies.template.md"
    template_file.write_text("# Shared Dependencies\n\n_Template content._\n")

    run_dir = create_run_workspace("build a todo app")

    assert run_dir.exists()
    assert (run_dir / "context").is_dir()
    assert (run_dir / "code").is_dir()
    assert (run_dir / "reports").is_dir()

    copied = run_dir / "context" / "shared_dependencies.md"
    assert copied.exists()
    assert copied.read_text() == template_file.read_text()
