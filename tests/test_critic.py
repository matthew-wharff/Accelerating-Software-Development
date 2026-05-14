"""Tests for agents/critic.py.

Unit tests mock anthropic.Anthropic so they run in milliseconds. Integration
tests (marked with `integration`) make real API calls and are opt-in.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import critic
from agents.critic import run_critic
from tests.conftest import make_text_response

MVP02_OUTPUT = str(Path(__file__).parent.parent / "output" / "main.py")
CONVENTIONS_PATH = Path(__file__).parent.parent / "context" / "CONVENTIONS.md"


# ---------------------------------------------------------------------------
# Unit tests (mocked Anthropic — fast, no network)
# ---------------------------------------------------------------------------


def test_run_critic_valid_input_writes_feedback(anthropic_mock, tmp_path, monkeypatch):
    """Happy path: file exists, Claude returns markdown, feedback file lands on disk."""
    anthropic_mock.messages.create.return_value = make_text_response(
        "# Review\n\nLooks good — minor style nits.\n"
    )
    monkeypatch.setattr(critic, "OUTPUT_DIR", tmp_path)

    target = tmp_path / "main.py"
    target.write_text("print('hi')\n", encoding="utf-8")

    out_path = run_critic(str(target), conventions="# Conventions")
    assert Path(out_path).exists()
    assert "Review" in Path(out_path).read_text(encoding="utf-8")


def test_run_critic_empty_conventions_no_crash(anthropic_mock, tmp_path, monkeypatch):
    anthropic_mock.messages.create.return_value = make_text_response("ok")
    monkeypatch.setattr(critic, "OUTPUT_DIR", tmp_path)

    target = tmp_path / "main.py"
    target.write_text("", encoding="utf-8")

    out_path = run_critic(str(target), conventions="")
    assert Path(out_path).exists()


def test_run_critic_missing_file_raises(anthropic_mock):
    with pytest.raises(FileNotFoundError):
        run_critic("/nonexistent/path/missing.py", "")


@pytest.mark.parametrize("bad", [None, 42])
def test_run_critic_malformed_path_input_no_silent_corruption(anthropic_mock, bad):
    """None or int path inputs should fail clearly, not silently."""
    with pytest.raises((TypeError, FileNotFoundError, AttributeError)):
        run_critic(bad, conventions="")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration tests (real Anthropic API — opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_run_critic_returns_existing_feedback_file():
    conventions = CONVENTIONS_PATH.read_text(encoding="utf-8")
    result_path = run_critic(MVP02_OUTPUT, conventions)
    assert Path(result_path).exists(), "Feedback file was not created"
    assert Path(result_path).stat().st_size > 0, "Feedback file is empty"


@pytest.mark.integration
def test_run_critic_feedback_is_substantive():
    conventions = CONVENTIONS_PATH.read_text(encoding="utf-8")
    result_path = run_critic(MVP02_OUTPUT, conventions)
    feedback = Path(result_path).read_text(encoding="utf-8")
    assert len(feedback) > 100, "Feedback is unexpectedly short"
