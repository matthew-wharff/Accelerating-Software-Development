"""Smoke tests for PIPELINE_MODE — HRD-11.

Verifies that PIPELINE_MODE=dry_run prevents real GitHub side effects, and
that an unset PIPELINE_MODE defaults to dry_run (fail-safe).
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

from state.schema import default_state


_MINIMAL_BRIEF = "write a Python function that adds two numbers"


@pytest.mark.integration
def test_dry_run_does_not_create_github_repo(monkeypatch):
    """End-to-end: PIPELINE_MODE=dry_run must NOT call run_github.

    Headline HRD-11 regression test. Runs the graph with a minimal brief and
    asserts the GitHub repo-creation entry point is never invoked. Patches
    graph.pipeline.run_github (where it is used) rather than
    agents.github_agent.run_github so the patch intercepts the call site.
    """
    monkeypatch.setenv("PIPELINE_MODE", "dry_run")
    import config
    monkeypatch.setattr(config, "PIPELINE_MODE", "dry_run", raising=False)

    from graph.pipeline import app

    with patch("graph.pipeline.run_github") as mock_create:
        app.invoke(default_state(project_brief=_MINIMAL_BRIEF))

    assert mock_create.call_count == 0, (
        "PIPELINE_MODE=dry_run must not call the GitHub repo creation API"
    )


def test_pipeline_mode_defaults_to_dry_run(monkeypatch):
    """Unit: when PIPELINE_MODE is unset, config must default to 'dry_run'.

    Locks in the fix from Task 1 of the Phase 1B audit remediation.
    """
    monkeypatch.delenv("PIPELINE_MODE", raising=False)

    import config
    importlib.reload(config)

    assert config.PIPELINE_MODE == "dry_run"
