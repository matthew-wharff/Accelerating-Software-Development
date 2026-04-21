"""Integration tests for agents/github_agent.py.

These tests make real GitHub API calls and create a real repo in the
authenticated user's account. The repo is deleted in the finally block
so no manual cleanup is needed.

Run with:
    pytest tests/test_github_node.py -v -m integration
"""

from __future__ import annotations

import sys
import os
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any

import github as gh

import config
from agents.github_agent import run_github, _repo_slug


# ---------------------------------------------------------------------------
# Unit tests (no API calls)
# ---------------------------------------------------------------------------


def test_repo_slug_basic():
    assert _repo_slug("My Todo App") == "my-todo-app"


def test_repo_slug_special_chars():
    assert _repo_slug("Hello, World! (v2)") == "hello-world-v2"


def test_repo_slug_truncates():
    brief = "a" * 60
    assert len(_repo_slug(brief)) <= 40


def test_repo_slug_empty():
    assert _repo_slug("") == "project"
    assert _repo_slug("   ") == "project"


def test_repo_slug_numbers_preserved():
    assert _repo_slug("FastAPI v2 REST API") == "fastapi-v2-rest-api"


# ---------------------------------------------------------------------------
# Integration tests (real GitHub API)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_github_node_creates_real_repo():
    """Confirm run_github creates a real repo with files committed and an open PR."""
    client = gh.Github(auth=gh.Auth.Token(config.GITHUB_PAT))
    user: Any = client.get_user()
    repo = None

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output" / "test-ai-scaffold"
        output_dir.mkdir(parents=True)

        src_file = output_dir / "main.py"
        src_file.write_text('print("Hello from AI pipeline")\n', encoding="utf-8")

        devops_file = output_dir / "Dockerfile"
        devops_file.write_text("FROM python:3.11-slim\nCOPY . .\n", encoding="utf-8")

        brief = "test ai scaffold pipeline integration"
        generated = [str(src_file)]
        devops = [str(devops_file)]

        try:
            repo_url = run_github(
                project_brief=brief,
                generated_file_paths=generated,
                devops_config_paths=devops,
            )

            assert repo_url.startswith("https://github.com/"), (
                f"Expected GitHub URL, got: {repo_url}"
            )

            repo_name = repo_url.rstrip("/").split("/")[-1]
            repo = user.get_repo(repo_name)

            assert repo is not None, "Repo should exist on GitHub"
            assert repo.html_url == repo_url

            branch_contents = repo.get_contents("", ref="scaffold/initial")
            file_names = [f.name for f in branch_contents]
            assert "main.py" in file_names or any(f.name for f in branch_contents), (
                "At least one file should be committed to scaffold/initial"
            )

            open_prs = list(repo.get_pulls(state="open", base="main"))
            assert len(open_prs) == 1, f"Expected 1 open PR, got {len(open_prs)}"
            assert open_prs[0].title == "Initial scaffold from AI pipeline"
            assert open_prs[0].head.ref == "scaffold/initial"

        finally:
            if repo is not None:
                repo.delete()


@pytest.mark.integration
def test_github_node_collision_appends_timestamp():
    """Confirm that if a repo already exists, a timestamp is appended."""
    client = gh.Github(auth=gh.Auth.Token(config.GITHUB_PAT))
    user: Any = client.get_user()

    repos_to_delete = []
    slug = "test-collision-repo-ci"

    try:
        first_repo = user.create_repo(slug, auto_init=True)
        repos_to_delete.append(first_repo)

        brief = "test collision repo ci"
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output" / slug.replace("-", "_")
            output_dir.mkdir(parents=True)
            f = output_dir / "hello.py"
            f.write_text("# hello\n", encoding="utf-8")

            repo_url = run_github(
                project_brief=brief,
                generated_file_paths=[str(f)],
                devops_config_paths=[],
            )

        repo_name = repo_url.rstrip("/").split("/")[-1]
        assert repo_name != slug, "Collision repo should have a different name"
        assert repo_name.startswith(slug), (
            f"Collision repo name should start with original slug, got: {repo_name}"
        )

        second_repo = user.get_repo(repo_name)
        repos_to_delete.append(second_repo)

    finally:
        for r in repos_to_delete:
            try:
                r.delete()
            except Exception:
                pass
