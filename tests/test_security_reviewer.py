"""Unit tests for agents/security_reviewer.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.security_reviewer import run_security_reviewer
from tests.conftest import make_text_response


def _seed(tmp_path: Path) -> tuple[Path, Path, Path]:
    run_dir = tmp_path / "run"
    (run_dir / "code").mkdir(parents=True)
    (run_dir / "context").mkdir()
    (run_dir / "reports").mkdir()
    src = run_dir / "code" / "auth.py"
    src.write_text(
        "def login(user, pwd):\n    return f'SELECT * FROM users WHERE u={user}'\n",
        encoding="utf-8",
    )
    deps = run_dir / "context" / "shared_dependencies.md"
    deps.write_text("# Shared Deps\n", encoding="utf-8")
    return run_dir, src, deps


def test_run_security_reviewer_valid_input_writes_report(anthropic_mock, tmp_path):
    findings = [
        {
            "severity": "high",
            "issue": "SQL injection via f-string",
            "location": "auth.py:login",
            "remediation": "use parameterised queries",
        }
    ]
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps(findings)
    )
    run_dir, src, deps = _seed(tmp_path)

    out_path = run_security_reviewer(
        generated_file_paths=[str(src)],
        shared_deps_path=str(deps),
        run_dir=str(run_dir),
    )
    assert Path(out_path).exists()
    body = Path(out_path).read_text(encoding="utf-8")
    assert "Security Review Report" in body
    assert "SQL injection" in body


def test_run_security_reviewer_empty_file_list_writes_empty_report(
    anthropic_mock, tmp_path
):
    anthropic_mock.messages.create.return_value = make_text_response("[]")
    run_dir, _, deps = _seed(tmp_path)

    out_path = run_security_reviewer(
        generated_file_paths=[],
        shared_deps_path=str(deps),
        run_dir=str(run_dir),
    )
    assert Path(out_path).exists()
    assert "No security issues" in Path(out_path).read_text(encoding="utf-8")


def test_run_security_reviewer_missing_shared_deps_uses_fallback(
    anthropic_mock, tmp_path
):
    """Agent must tolerate a missing shared_deps_path — it logs and uses a fallback."""
    anthropic_mock.messages.create.return_value = make_text_response("[]")
    run_dir, src, _ = _seed(tmp_path)

    out_path = run_security_reviewer(
        generated_file_paths=[str(src)],
        shared_deps_path=str(tmp_path / "ghost.md"),
        run_dir=str(run_dir),
    )
    assert Path(out_path).exists()


def test_run_security_reviewer_malformed_response_logs_finding(
    anthropic_mock, tmp_path
):
    anthropic_mock.messages.create.return_value = make_text_response("not json")
    run_dir, src, deps = _seed(tmp_path)

    out_path = run_security_reviewer(
        generated_file_paths=[str(src)],
        shared_deps_path=str(deps),
        run_dir=str(run_dir),
    )
    body = Path(out_path).read_text(encoding="utf-8")
    assert "manual" in body.lower() or "failed to parse" in body.lower()
