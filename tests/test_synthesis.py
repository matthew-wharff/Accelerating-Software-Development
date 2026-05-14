"""Unit tests for agents/synthesis.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.synthesis import run_synthesis
from tests.conftest import make_text_response


SYNTHESIS_BODY_NO_BLOCK = (
    "# Synthesis Report\n\n"
    "## High Priority Fixes\n- None\n\n"
    "## Medium Priority Fixes\n- Refactor X\n\n"
    "## Low Priority Fixes\n- None\n\n"
    "## Blocking Issues\nhas_blocking_issues: false\n"
)

SYNTHESIS_BODY_BLOCKING = (
    "# Synthesis Report\n\n"
    "## High Priority Fixes\n- Fix SQL injection in auth.py\n\n"
    "## Medium Priority Fixes\n- None\n\n"
    "## Low Priority Fixes\n- None\n\n"
    "## Blocking Issues\nhas_blocking_issues: true\n"
)


def _seed(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    reports = tmp_path / "reports"
    reports.mkdir()
    test_path = reports / "test_feedback.md"
    sec_path = reports / "security_report.md"
    qual_path = reports / "quality_report.md"
    test_path.write_text("test feedback\n", encoding="utf-8")
    sec_path.write_text("security feedback\n", encoding="utf-8")
    qual_path.write_text("quality feedback\n", encoding="utf-8")
    out = tmp_path / "context"
    out.mkdir()
    return test_path, sec_path, qual_path, out / "SYNTHESIS_REPORT.md"


def test_run_synthesis_valid_input_writes_report_no_blocking(
    anthropic_mock, tmp_path
):
    anthropic_mock.messages.create.return_value = make_text_response(
        SYNTHESIS_BODY_NO_BLOCK
    )
    test_p, sec_p, qual_p, out = _seed(tmp_path)

    path, has_blocking = run_synthesis(
        test_feedback_path=str(test_p),
        security_feedback_path=str(sec_p),
        quality_feedback_path=str(qual_p),
        out_path=str(out),
    )

    assert Path(path).exists()
    assert has_blocking is False
    assert "Synthesis Report" in Path(path).read_text(encoding="utf-8")


def test_run_synthesis_blocking_flag_parsed_true(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.return_value = make_text_response(
        SYNTHESIS_BODY_BLOCKING
    )
    test_p, sec_p, qual_p, out = _seed(tmp_path)

    _, has_blocking = run_synthesis(
        test_feedback_path=str(test_p),
        security_feedback_path=str(sec_p),
        quality_feedback_path=str(qual_p),
        out_path=str(out),
    )
    assert has_blocking is True


def test_run_synthesis_empty_paths_handled(anthropic_mock, tmp_path):
    """All None paths should not crash — agent injects '(no report)' placeholders."""
    anthropic_mock.messages.create.return_value = make_text_response(
        SYNTHESIS_BODY_NO_BLOCK
    )
    out = tmp_path / "context"
    out.mkdir()
    path, _ = run_synthesis(
        test_feedback_path=None,
        security_feedback_path=None,
        quality_feedback_path=None,
        out_path=str(out / "SYNTHESIS_REPORT.md"),
    )
    assert Path(path).exists()


def test_run_synthesis_missing_files_handled_gracefully(anthropic_mock, tmp_path):
    """Non-existent paths should be skipped, not crash."""
    anthropic_mock.messages.create.return_value = make_text_response(
        SYNTHESIS_BODY_NO_BLOCK
    )
    out = tmp_path / "context"
    out.mkdir()

    path, _ = run_synthesis(
        test_feedback_path=str(tmp_path / "ghost1.md"),
        security_feedback_path=str(tmp_path / "ghost2.md"),
        quality_feedback_path=str(tmp_path / "ghost3.md"),
        out_path=str(out / "SYNTHESIS_REPORT.md"),
    )
    assert Path(path).exists()
