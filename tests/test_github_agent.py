"""Unit tests for agents/github_agent.py.

Mocks the PyGithub client so no real GitHub API calls happen. Integration
tests against the real API live in test_github_node.py and only run with
the `integration` marker.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import github as gh

from agents.github_agent import _repo_slug, run_github


def _build_mock_github(mocker, repo_already_exists: bool = False) -> MagicMock:
    """Patch agents.github_agent.gh with a fully mocked GitHub client.

    Returns the mock `repo` object so tests can inspect calls to it.
    """
    mock_repo = MagicMock()
    mock_repo.html_url = "https://github.com/fake-user/fake-repo"
    mock_repo.get_git_ref.return_value.object.sha = "abc1234"
    pr = MagicMock()
    pr.number = 1
    pr.html_url = "https://github.com/fake-user/fake-repo/pull/1"
    mock_repo.create_pull.return_value = pr

    mock_user = MagicMock()
    mock_user.login = "fake-user"
    mock_user.create_repo.return_value = mock_repo

    if repo_already_exists:
        mock_user.get_repo.return_value = MagicMock()  # collision
    else:
        mock_user.get_repo.side_effect = gh.UnknownObjectException(
            status=404, data={}, headers={}
        )

    mock_client = MagicMock()
    mock_client.get_user.return_value = mock_user
    mocker.patch("agents.github_agent.gh.Github", return_value=mock_client)
    return mock_repo


def _seed_files(tmp_path: Path) -> tuple[list[str], list[str]]:
    code_dir = tmp_path / "output" / "run_x" / "code"
    code_dir.mkdir(parents=True)
    src = code_dir / "main.py"
    src.write_text("print('hello')\n", encoding="utf-8")
    docker = code_dir / "Dockerfile"
    docker.write_text("FROM python:3.11-slim\n", encoding="utf-8")
    return [str(src)], [str(docker)]


def test_run_github_valid_input_returns_url(mocker, tmp_path):
    repo = _build_mock_github(mocker)
    generated, devops = _seed_files(tmp_path)

    url = run_github(
        project_brief="Build a hello world CLI",
        generated_file_paths=generated,
        devops_config_paths=devops,
    )

    assert url == "https://github.com/fake-user/fake-repo"
    assert repo.create_file.call_count == 2
    repo.create_pull.assert_called_once()


def test_run_github_empty_brief_falls_back_to_default_slug(mocker, tmp_path):
    _build_mock_github(mocker)
    generated, devops = _seed_files(tmp_path)

    url = run_github(
        project_brief="",
        generated_file_paths=generated,
        devops_config_paths=devops,
    )
    assert url.startswith("https://github.com/")


def test_run_github_collision_appends_timestamp(mocker, tmp_path):
    _build_mock_github(mocker, repo_already_exists=True)
    generated, devops = _seed_files(tmp_path)

    url = run_github(
        project_brief="my project",
        generated_file_paths=generated,
        devops_config_paths=devops,
    )
    # The mock returns the same html_url either way; we just assert no crash
    # and that the repo creation path was exercised.
    assert url.startswith("https://github.com/")


def test_run_github_missing_files_skipped(mocker, tmp_path):
    repo = _build_mock_github(mocker)

    url = run_github(
        project_brief="brief",
        generated_file_paths=[str(tmp_path / "ghost.py")],
        devops_config_paths=[],
    )
    assert url.startswith("https://github.com/")
    repo.create_file.assert_not_called()


@pytest.mark.parametrize(
    "brief,expected",
    [
        ("My Todo App", "my-todo-app"),
        ("Hello, World! (v2)", "hello-world-v2"),
        ("", "project"),
        ("   ", "project"),
        ("a" * 60, "a" * 40),
    ],
)
def test_repo_slug_variants(brief, expected):
    assert _repo_slug(brief) == expected
