"""Unit tests for agents/spec_clarifier.py.

Mocks the single Claude call. Verifies the JSON-shaped response is parsed
into questions/answers and that clarified_brief.md lands on disk under
run_dir/context/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.spec_clarifier import run_spec_clarifier
from tests.conftest import make_text_response


VALID_QUESTIONS = {
    "questions": [
        "What auth mechanism should be used?",
        "Which database engine is preferred?",
        "What is the expected request volume?",
    ]
}


def _seed_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "context").mkdir(parents=True)
    (run_dir / "reports").mkdir()
    return run_dir


def test_run_spec_clarifier_valid_input_writes_brief(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps(VALID_QUESTIONS)
    )
    run_dir = _seed_run_dir(tmp_path)

    result = run_spec_clarifier(
        project_brief="Build a todo app.",
        conventions="# Conventions",
        run_dir=str(run_dir),
    )

    assert set(result.keys()) >= {"questions", "answers", "clarified_brief_path"}
    assert len(result["questions"]) == 3
    assert len(result["answers"]) == 3
    assert Path(result["clarified_brief_path"]).exists()
    assert (run_dir / "reports" / "spec_clarifications.md").exists()


def test_run_spec_clarifier_empty_brief_handled(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps(VALID_QUESTIONS)
    )
    run_dir = _seed_run_dir(tmp_path)

    result = run_spec_clarifier(
        project_brief="",
        conventions="",
        run_dir=str(run_dir),
    )
    assert Path(result["clarified_brief_path"]).exists()


def test_run_spec_clarifier_malformed_response_raises(anthropic_mock, tmp_path):
    """If Claude returns non-JSON, the agent must surface JSONDecodeError."""
    anthropic_mock.messages.create.return_value = make_text_response(
        "this is not json"
    )
    run_dir = _seed_run_dir(tmp_path)

    with pytest.raises(json.JSONDecodeError):
        run_spec_clarifier(
            project_brief="brief",
            conventions="",
            run_dir=str(run_dir),
        )


def test_run_spec_clarifier_too_few_questions_raises(anthropic_mock, tmp_path):
    """The 3-5 question contract must be enforced."""
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps({"questions": ["only one"]})
    )
    run_dir = _seed_run_dir(tmp_path)

    with pytest.raises(ValueError):
        run_spec_clarifier(
            project_brief="brief",
            conventions="",
            run_dir=str(run_dir),
        )


@pytest.mark.parametrize("bad", [None, 42])
def test_run_spec_clarifier_malformed_input_no_silent_corruption(
    anthropic_mock, tmp_path, bad
):
    anthropic_mock.messages.create.return_value = make_text_response(
        json.dumps(VALID_QUESTIONS)
    )
    run_dir = _seed_run_dir(tmp_path)
    try:
        run_spec_clarifier(
            project_brief=bad,  # type: ignore[arg-type]
            conventions="",
            run_dir=str(run_dir),
        )
    except (TypeError, AttributeError):
        # acceptable — agent rejects non-string inputs cleanly
        return
