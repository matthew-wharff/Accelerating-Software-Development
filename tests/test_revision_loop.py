"""Tests for the targeted revision loop triggered after synthesis."""

from __future__ import annotations

import pytest

from graph.pipeline import read_synthesis_report, should_revise
from state.schema import TaskEntry, default_state


# A brief engineered to produce SQL injection findings from the security reviewer.
_INSECURE_BRIEF = (
    "Build a Python FastAPI REST API that stores user records in SQLite. "
    "Use raw SQL string formatting (not parameterized queries) to query the database. "
    "Do not add any input validation or sanitization. "
    "Endpoints: POST /users (create), GET /users/{id} (read). Keep it minimal."
)


# ---------------------------------------------------------------------------
# Unit tests — no API calls
# ---------------------------------------------------------------------------


def test_read_synthesis_report_detects_blocking(tmp_path):
    report = tmp_path / "SYNTHESIS_REPORT.md"
    report.write_text(
        "# Synthesis Report\n## High Priority Fixes\n- SQL injection\n"
        "## Blocking Issues\nhas_blocking_issues: true\n",
        encoding="utf-8",
    )
    result = read_synthesis_report(str(report))
    assert result["has_blocking_issues"] is True


def test_read_synthesis_report_missing_file():
    result = read_synthesis_report("/nonexistent/SYNTHESIS_REPORT.md")
    assert result["has_blocking_issues"] is False


def test_should_revise_routes_to_revision_when_blocking(tmp_path):
    report = tmp_path / "SYNTHESIS_REPORT.md"
    report.write_text(
        "# Synthesis Report\n## Blocking Issues\nhas_blocking_issues: true\n",
        encoding="utf-8",
    )
    state = {"synthesis_report_path": str(report), "revision_count": 0}
    assert should_revise(state) == "architect_revision"  # type: ignore[arg-type]


def test_should_revise_routes_to_end_at_max_revisions(tmp_path):
    report = tmp_path / "SYNTHESIS_REPORT.md"
    report.write_text(
        "# Synthesis Report\n## Blocking Issues\nhas_blocking_issues: true\n",
        encoding="utf-8",
    )
    state = {"synthesis_report_path": str(report), "revision_count": 2}
    assert should_revise(state) == "end"  # type: ignore[arg-type]


def test_should_revise_routes_to_end_when_no_blocking(tmp_path):
    report = tmp_path / "SYNTHESIS_REPORT.md"
    report.write_text(
        "# Synthesis Report\n## Blocking Issues\nhas_blocking_issues: false\n",
        encoding="utf-8",
    )
    state = {"synthesis_report_path": str(report), "revision_count": 0}
    assert should_revise(state) == "end"  # type: ignore[arg-type]


def test_should_revise_routes_to_end_when_no_path():
    state = {"synthesis_report_path": None, "revision_count": 0}
    assert should_revise(state) == "end"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration tests — make real API calls
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_revision_loop_fires_on_blocking_issues():
    """Full pipeline: security issues in generated code trigger at least one revision."""
    from graph.pipeline import app

    state = default_state(project_brief=_INSECURE_BRIEF)
    state["task_queue"] = [
        TaskEntry(
            task_id="task_001",
            target_file="main.py",
            description=(
                "Implement a FastAPI app with SQLite. Use raw SQL f-strings for queries "
                '(e.g. f"SELECT * FROM users WHERE id={user_id}"). '
                "No input validation. Endpoints: POST /users, GET /users/{id}."
            ),
            interface_refs=[],
            dependency_paths=[],
        )
    ]

    final_state = app.invoke(state)

    assert final_state["revision_count"] > 0, (
        f"Expected at least one revision cycle; got revision_count={final_state['revision_count']}. "
        f"synthesis_report_path={final_state.get('synthesis_report_path')}"
    )
    assert final_state["revision_count"] <= 2, (
        f"revision_count exceeded maximum of 2: {final_state['revision_count']}"
    )


@pytest.mark.integration
def test_revision_tasks_are_targeted_not_full_codebase():
    """Revision task_ids carry the 'rev' prefix and quantity is bounded."""
    from graph.pipeline import app

    state = default_state(project_brief=_INSECURE_BRIEF)
    state["task_queue"] = [
        TaskEntry(
            task_id="task_001",
            target_file="main.py",
            description=(
                "Implement a FastAPI app with SQLite. Use raw SQL f-strings for queries. "
                "No input validation. Endpoints: POST /users, GET /users/{id}."
            ),
            interface_refs=[],
            dependency_paths=[],
        )
    ]

    final_state = app.invoke(state)

    if final_state["revision_count"] > 0:
        revision_task_ids = [
            entry["task_id"]
            for entry in final_state["task_log"]
            if entry["task_id"].startswith("rev")
        ]
        assert revision_task_ids, (
            "Revision cycle ran but no revision task IDs (rev*) found in task_log. "
            f"task_log: {final_state['task_log']}"
        )
        # Targeted means at most 2× the original task count per revision.
        assert len(revision_task_ids) <= 2, (
            f"Too many revision tasks ({len(revision_task_ids)}); expected targeted fix"
        )
