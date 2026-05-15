"""End-to-end integration tests for the LangGraph pipeline.

These tests make real Anthropic and e2b API calls. They are marked with
``@pytest.mark.integration`` so the default ``pytest`` run skips them — opt
in with ``pytest -m integration`` to avoid burning tokens during rapid
iteration.

The brief is intentionally trivial ("a function that adds two numbers") so a
full run stays cheap. The assertions verify the graph terminates, generated
files land on disk, and the synthesis + revision loop behave correctly.

GitHub side effects are gated by ``PIPELINE_MODE`` — these tests force
``dry_run`` so no real repos are created.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from state.schema import default_state


_MINIMAL_BRIEF = "write a Python function that adds two numbers"


@pytest.fixture
def force_dry_run(monkeypatch):
    """Pin PIPELINE_MODE to dry_run so the github_node never publishes."""
    monkeypatch.setenv("PIPELINE_MODE", "dry_run")
    import config
    monkeypatch.setattr(config, "PIPELINE_MODE", "dry_run", raising=False)


@pytest.mark.integration
def test_pipeline_end_to_end_minimal_brief(force_dry_run):
    """Invoke the full graph with a trivial brief and verify terminal state.

    Checks the contract every downstream consumer relies on:
      - graph.invoke() returns without raising
      - generated_file_paths is non-empty and every path exists on disk
      - synthesis_report_path exists and parses as a structured report
      - revision_count is bounded by the loop cap (<= 2)
    """
    from graph.pipeline import app

    initial_state = default_state(project_brief=_MINIMAL_BRIEF)

    final_state = app.invoke(initial_state)

    generated = final_state.get("generated_file_paths") or []
    assert generated, (
        "generated_file_paths is empty — pipeline produced no code. "
        f"status={final_state.get('status')}"
    )

    for path in generated:
        assert Path(path).exists(), f"generated_file_paths includes missing file: {path}"

    synthesis_path = final_state.get("synthesis_report_path")
    assert synthesis_path, "synthesis_report_path is missing from final state"
    synthesis_file = Path(synthesis_path)
    assert synthesis_file.exists(), f"synthesis report not on disk: {synthesis_path}"

    report_text = synthesis_file.read_text(encoding="utf-8").strip()
    assert report_text, "synthesis report is empty"
    _assert_synthesis_report_is_structured(report_text, synthesis_path)

    revision_count = final_state.get("revision_count", 0)
    assert revision_count <= 2, (
        f"revision_count exceeded loop cap: {revision_count} (loop should terminate at 2)"
    )


def _assert_synthesis_report_is_structured(report_text: str, path: str) -> None:
    """Verify the synthesis report is parseable structured output.

    The Synthesis agent writes markdown with a ``has_blocking_issues:`` sentinel
    line that ``read_synthesis_report`` parses. If a future revision swaps the
    format to JSON, this helper accepts that too — what matters is that the
    consumer (the revision router) can extract a boolean decision.
    """
    try:
        parsed = json.loads(report_text)
    except json.JSONDecodeError:
        parsed = None

    if parsed is not None:
        assert "has_blocking_issues" in parsed, (
            f"JSON synthesis report at {path} missing has_blocking_issues key"
        )
        assert isinstance(parsed["has_blocking_issues"], bool), (
            f"JSON synthesis report at {path}: has_blocking_issues must be bool"
        )
        return

    lowered = report_text.lower()
    assert "has_blocking_issues:" in lowered, (
        f"synthesis report at {path} missing has_blocking_issues sentinel — "
        "the revision router cannot make a decision without it"
    )
    assert "# synthesis report" in lowered, (
        f"synthesis report at {path} missing top-level header"
    )
