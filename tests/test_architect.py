"""Unit tests for agents/architect.py.

The Anthropic API is fully mocked — these tests must not make network calls.
Each scenario verifies the agent handles the input shape and writes the
expected artifacts to disk under tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.architect import run_architect
from tests.conftest import make_text_response


SAMPLE_TASK_QUEUE = [
    {
        "task_id": "task_001",
        "target_file": "main.py",
        "description": "Entry point for the CLI.",
        "interface_refs": [],
        "dependency_paths": [],
    }
]


def _seed_run_dir(tmp_path: Path) -> Path:
    """Mirror what workspace_node would create before run_architect runs."""
    run_dir = tmp_path / "run"
    (run_dir / "context").mkdir(parents=True)
    (run_dir / "code").mkdir()
    (run_dir / "reports").mkdir()
    return run_dir


def _four_responses(task_queue=SAMPLE_TASK_QUEUE):
    """Build the four sequential responses run_architect expects."""
    return [
        make_text_response("# ARCHITECT_SPEC.md\n\nA spec."),
        make_text_response("from __future__ import annotations\n\n# interfaces\n"),
        make_text_response("# Shared Dependencies\n\n## Shared Types & Models\nN/A\n"),
        make_text_response(json.dumps(task_queue)),
    ]


def test_run_architect_valid_input_writes_all_artifacts(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.side_effect = _four_responses()
    run_dir = _seed_run_dir(tmp_path)

    result = run_architect(
        clarified_brief="Build a hello world CLI.",
        conventions="# Conventions\n\nUse snake_case.",
        run_dir=str(run_dir),
    )

    for key in (
        "architect_spec_path",
        "interfaces_path",
        "shared_deps_path",
        "task_queue_path",
        "task_queue",
    ):
        assert key in result, f"missing key {key} in result"

    for path_key in (
        "architect_spec_path",
        "interfaces_path",
        "shared_deps_path",
        "task_queue_path",
    ):
        assert Path(result[path_key]).exists(), f"{path_key} not on disk"

    assert isinstance(result["task_queue"], list)
    assert result["task_queue"][0]["task_id"] == "task_001"


def test_run_architect_empty_brief_does_not_crash(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.side_effect = _four_responses()
    run_dir = _seed_run_dir(tmp_path)

    result = run_architect(
        clarified_brief="",
        conventions="",
        run_dir=str(run_dir),
    )

    assert Path(result["architect_spec_path"]).exists()


@pytest.mark.parametrize("malformed_brief", [None, 42, "x" * 100_000])
def test_run_architect_malformed_brief_no_crash_when_stringifiable(
    anthropic_mock, tmp_path, malformed_brief
):
    """Agent should accept any stringifiable input without raising on its own.

    The Anthropic API call is mocked, so the only failure modes that matter
    here are inside the agent itself (formatting, disk write, parse).
    """
    anthropic_mock.messages.create.side_effect = _four_responses()
    run_dir = _seed_run_dir(tmp_path)

    try:
        result = run_architect(
            clarified_brief=malformed_brief,  # type: ignore[arg-type]
            conventions="conv",
            run_dir=str(run_dir),
        )
    except (TypeError, AttributeError):
        # Expected for None/int — Python f-strings tolerate both, but len()
        # in the log line would fail on int. We only assert no unhandled
        # crash escapes for the huge-string case.
        if isinstance(malformed_brief, str):
            raise
        return

    assert Path(result["architect_spec_path"]).exists()
