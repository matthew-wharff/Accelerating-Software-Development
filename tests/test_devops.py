"""Unit tests for agents/devops.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.devops import run_devops
from tests.conftest import make_text_response


VALID_DEVOPS_RESPONSE = {
    "Dockerfile": "FROM python:3.11-slim\n",
    ".github/workflows/ci.yml": "name: ci\n",
    ".env.example": "FOO=bar\n",
    "docker-compose.yml": "services:\n  app: {}\n",
}


def _seed(tmp_path: Path) -> tuple[Path, Path, Path]:
    run_dir = tmp_path / "run"
    (run_dir / "code").mkdir(parents=True)
    (run_dir / "context").mkdir()
    spec = run_dir / "context" / "ARCHITECT_SPEC.md"
    spec.write_text("# Spec\n", encoding="utf-8")
    deps = run_dir / "context" / "shared_dependencies.md"
    deps.write_text("# Shared Deps\n", encoding="utf-8")
    return run_dir, spec, deps


def test_run_devops_valid_input_writes_four_files(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps(VALID_DEVOPS_RESPONSE)
    )
    run_dir, spec, deps = _seed(tmp_path)

    paths = run_devops(
        architect_spec_path=str(spec),
        shared_deps_path=str(deps),
        run_dir=str(run_dir),
    )

    assert len(paths) == 4
    for p in paths:
        assert Path(p).exists(), f"{p} should be on disk"
    names = {Path(p).name for p in paths}
    assert {"Dockerfile", "ci.yml", ".env.example", "docker-compose.yml"} <= names


def test_run_devops_empty_inputs_handled(anthropic_mock, tmp_path):
    """Empty spec/deps files should not prevent the agent from running."""
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps(VALID_DEVOPS_RESPONSE)
    )
    run_dir = tmp_path / "run"
    (run_dir / "code").mkdir(parents=True)
    (run_dir / "context").mkdir()
    spec = run_dir / "context" / "ARCHITECT_SPEC.md"
    spec.write_text("", encoding="utf-8")
    deps = run_dir / "context" / "shared_dependencies.md"
    deps.write_text("", encoding="utf-8")

    paths = run_devops(
        architect_spec_path=str(spec),
        shared_deps_path=str(deps),
        run_dir=str(run_dir),
    )
    assert len(paths) == 4


def test_run_devops_malformed_json_raises(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.return_value = make_text_response("not json")
    run_dir, spec, deps = _seed(tmp_path)

    with pytest.raises(RuntimeError):
        run_devops(
            architect_spec_path=str(spec),
            shared_deps_path=str(deps),
            run_dir=str(run_dir),
        )


def test_run_devops_missing_keys_raises(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps({"Dockerfile": "FROM python:3.11"})
    )
    run_dir, spec, deps = _seed(tmp_path)

    with pytest.raises(RuntimeError, match="missing keys"):
        run_devops(
            architect_spec_path=str(spec),
            shared_deps_path=str(deps),
            run_dir=str(run_dir),
        )


def test_run_devops_missing_spec_file_raises(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps(VALID_DEVOPS_RESPONSE)
    )
    run_dir = tmp_path / "run"
    (run_dir / "code").mkdir(parents=True)

    with pytest.raises(OSError):
        run_devops(
            architect_spec_path=str(tmp_path / "ghost.md"),
            shared_deps_path=str(tmp_path / "ghost2.md"),
            run_dir=str(run_dir),
        )
