"""Unit tests for agents/code_quality.py."""

from __future__ import annotations

import json
from pathlib import Path

from agents.code_quality import run_code_quality
from tests.conftest import make_text_response


def _seed(tmp_path: Path, source: str = "def foo():\n    return 1\n") -> tuple[Path, Path]:
    run_dir = tmp_path / "run"
    (run_dir / "code").mkdir(parents=True)
    (run_dir / "reports").mkdir()
    src = run_dir / "code" / "sample.py"
    src.write_text(source, encoding="utf-8")
    return run_dir, src


def test_run_code_quality_valid_input_writes_report(anthropic_mock, tmp_path):
    findings = [
        {
            "category": "style",
            "issue": "missing docstring",
            "location": "sample.py:foo",
            "suggestion": "add a one-line docstring",
        }
    ]
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps(findings)
    )
    run_dir, src = _seed(tmp_path)

    out_path = run_code_quality(
        generated_file_paths=[str(src)],
        conventions="# Conventions",
        run_dir=str(run_dir),
    )

    assert Path(out_path).exists()
    body = Path(out_path).read_text(encoding="utf-8")
    assert "Code Quality Report" in body
    assert "missing docstring" in body


def test_run_code_quality_empty_file_list_writes_empty_report(
    anthropic_mock, tmp_path
):
    anthropic_mock.messages.create.return_value = make_text_response("[]")
    run_dir, _ = _seed(tmp_path)

    out_path = run_code_quality(
        generated_file_paths=[],
        conventions="",
        run_dir=str(run_dir),
    )
    assert Path(out_path).exists()
    assert "No quality issues" in Path(out_path).read_text(encoding="utf-8")


def test_run_code_quality_malformed_response_logged_as_finding(
    anthropic_mock, tmp_path
):
    """Bad JSON from Claude should produce a 'manual review required' finding,
    not crash the agent."""
    anthropic_mock.messages.create.return_value = make_text_response("not json")
    run_dir, src = _seed(tmp_path)

    out_path = run_code_quality(
        generated_file_paths=[str(src)],
        conventions="",
        run_dir=str(run_dir),
    )
    body = Path(out_path).read_text(encoding="utf-8")
    assert "manual review" in body.lower()


def test_run_code_quality_missing_source_file_skipped(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.return_value = make_text_response("[]")
    run_dir = tmp_path / "run"
    (run_dir / "reports").mkdir(parents=True)

    out_path = run_code_quality(
        generated_file_paths=[str(tmp_path / "ghost.py")],
        conventions="",
        run_dir=str(run_dir),
    )
    assert Path(out_path).exists()
