"""Unit tests for scripts/instrumentation.py.

Covers the full cycle: ``instrumented_call`` records a metric per API call,
``summarize_run`` aggregates the JSONL ledger, ``calculate_cost_usd``
applies the per-model pricing table from ``config.MODEL_PRICING``, and
``write_summary`` renders a readable markdown report.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import anthropic
import pytest

from config import MODEL_PRICING
from scripts.instrumentation import (
    ApiCallMetric,
    METRICS_FILENAME,
    SUMMARY_FILENAME,
    calculate_cost_usd,
    instrumented_call,
    metrics_path_for,
    summarize_run,
    write_summary,
)
from tests.conftest import make_text_response


def test_metrics_path_for_returns_canonical_subpath(tmp_path: Path) -> None:
    assert metrics_path_for(tmp_path) == tmp_path / "reports" / METRICS_FILENAME


def test_instrumented_call_persists_metric_and_returns_response(
    anthropic_mock, tmp_path: Path
) -> None:
    anthropic_mock.messages.create.return_value = make_text_response(
        "ok", input_tokens=1234, output_tokens=567
    )

    response = instrumented_call(
        anthropic_mock,
        agent="coder",
        phase="code_generation",
        run_dir=tmp_path,
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": "hi"}],
    )

    # Response surface is unchanged.
    assert response.content[0].text == "ok"

    ledger = metrics_path_for(tmp_path)
    assert ledger.exists()
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["agent"] == "coder"
    assert record["phase"] == "code_generation"
    assert record["model"] == "claude-sonnet-4-20250514"
    assert record["input_tokens"] == 1234
    assert record["output_tokens"] == 567
    assert record["duration_seconds"] >= 0


def test_instrumented_call_appends_one_line_per_call(
    anthropic_mock, tmp_path: Path
) -> None:
    anthropic_mock.messages.create.side_effect = [
        make_text_response("a", input_tokens=10, output_tokens=20),
        make_text_response("b", input_tokens=30, output_tokens=40),
    ]

    for phase in ("call_a", "call_b"):
        instrumented_call(
            anthropic_mock,
            agent="coder",
            phase=phase,
            run_dir=tmp_path,
            model="claude-sonnet-4-20250514",
        )

    lines = metrics_path_for(tmp_path).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["phase"] == "call_a"
    assert json.loads(lines[1])["phase"] == "call_b"


def test_instrumented_call_no_run_dir_skips_disk_persistence(
    anthropic_mock, tmp_path: Path
) -> None:
    """run_dir=None means we still log, but the JSONL is not created."""
    anthropic_mock.messages.create.return_value = make_text_response("ok")
    instrumented_call(
        anthropic_mock,
        agent="coder",
        phase="standalone",
        run_dir=None,
        model="claude-sonnet-4-20250514",
    )
    # No reports dir should be created when run_dir is None.
    assert not (tmp_path / "reports").exists()


def test_instrumented_call_reraises_api_error(
    anthropic_mock, tmp_path: Path
) -> None:
    """Failed API calls bubble up; no metric line is appended."""
    request = MagicMock()
    body = {"error": {"message": "boom"}}
    anthropic_mock.messages.create.side_effect = anthropic.APIError(
        message="boom", request=request, body=body
    )

    with pytest.raises(anthropic.APIError):
        instrumented_call(
            anthropic_mock,
            agent="coder",
            phase="fail",
            run_dir=tmp_path,
            model="claude-sonnet-4-20250514",
        )
    assert not metrics_path_for(tmp_path).exists()


def test_calculate_cost_usd_sonnet_matches_pricing_table() -> None:
    """1M uncached input + 1M output of Sonnet 4 = $3 + $15 = $18."""
    metric = ApiCallMetric(
        ts="2026-05-13T00:00:00+00:00",
        agent="coder",
        phase="code_generation",
        model="claude-sonnet-4-20250514",
        duration_seconds=1.0,
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    assert calculate_cost_usd(metric) == pytest.approx(
        MODEL_PRICING["claude-sonnet-4-20250514"]["input"]
        + MODEL_PRICING["claude-sonnet-4-20250514"]["output"]
    )


def test_calculate_cost_usd_haiku_cheaper_than_sonnet() -> None:
    """Critic models on Haiku cost an order of magnitude less for the same volume."""
    sonnet_metric = {
        "agent": "x", "phase": "x", "ts": "x", "duration_seconds": 0,
        "model": "claude-sonnet-4-20250514",
        "input_tokens": 100_000, "output_tokens": 100_000,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
    }
    haiku_metric = {**sonnet_metric, "model": "claude-haiku-4-5-20251001"}

    sonnet_cost = calculate_cost_usd(sonnet_metric)
    haiku_cost = calculate_cost_usd(haiku_metric)
    assert haiku_cost > 0
    assert sonnet_cost > 3 * haiku_cost


def test_calculate_cost_usd_unknown_model_returns_zero() -> None:
    metric = {
        "agent": "x", "phase": "x", "ts": "x", "duration_seconds": 0,
        "model": "made-up-model",
        "input_tokens": 1_000_000, "output_tokens": 1_000_000,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
    }
    assert calculate_cost_usd(metric) == 0.0


def test_calculate_cost_usd_applies_cache_pricing() -> None:
    """Cache reads cost 10% of base input; cache writes cost 125%."""
    pricing = MODEL_PRICING["claude-sonnet-4-20250514"]
    metric = {
        "agent": "x", "phase": "x", "ts": "x", "duration_seconds": 0,
        "model": "claude-sonnet-4-20250514",
        "input_tokens": 0, "output_tokens": 0,
        "cache_creation_input_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
    }
    expected = pricing["cache_write_5m"] + pricing["cache_read"]
    assert calculate_cost_usd(metric) == pytest.approx(expected)


def test_summarize_run_empty_when_no_ledger(tmp_path: Path) -> None:
    summary = summarize_run(tmp_path)
    assert summary["records"] == []
    assert summary["by_agent"] == {}
    assert summary["total"]["calls"] == 0


def _seed_ledger(run_dir: Path, records: list[dict]) -> None:
    """Helper: write a sequence of metric records to the canonical JSONL path."""
    ledger = metrics_path_for(run_dir)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )


def test_summarize_run_groups_by_agent_and_totals_match(tmp_path: Path) -> None:
    _seed_ledger(
        tmp_path,
        [
            {
                "ts": "t1", "agent": "coder", "phase": "code_generation",
                "model": "claude-sonnet-4-20250514", "duration_seconds": 1.5,
                "input_tokens": 5_000, "output_tokens": 1_000,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            },
            {
                "ts": "t2", "agent": "coder", "phase": "interface_extraction",
                "model": "claude-sonnet-4-20250514", "duration_seconds": 0.5,
                "input_tokens": 500, "output_tokens": 100,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            },
            {
                "ts": "t3", "agent": "security_reviewer", "phase": "review:foo.py",
                "model": "claude-haiku-4-5-20251001", "duration_seconds": 0.8,
                "input_tokens": 2_000, "output_tokens": 300,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            },
        ],
    )

    summary = summarize_run(tmp_path)

    coder = summary["by_agent"]["coder"]
    sec = summary["by_agent"]["security_reviewer"]
    total = summary["total"]

    assert coder["calls"] == 2
    assert coder["input_tokens"] == 5_500
    assert coder["output_tokens"] == 1_100
    assert sec["calls"] == 1
    assert sec["input_tokens"] == 2_000
    assert total["calls"] == 3
    assert total["input_tokens"] == 7_500
    assert total["output_tokens"] == 1_400
    # Cost sum equals component costs.
    assert total["cost_usd"] == pytest.approx(
        coder["cost_usd"] + sec["cost_usd"]
    )


def test_summarize_run_skips_malformed_lines(tmp_path: Path) -> None:
    ledger = metrics_path_for(tmp_path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    valid_record = {
        "ts": "t1", "agent": "coder", "phase": "code_generation",
        "model": "claude-sonnet-4-20250514", "duration_seconds": 1.0,
        "input_tokens": 10, "output_tokens": 5,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
    }
    ledger.write_text(
        json.dumps(valid_record) + "\n{not valid json}\n\n", encoding="utf-8"
    )
    summary = summarize_run(tmp_path)
    assert summary["total"]["calls"] == 1


def test_write_summary_emits_markdown_with_per_agent_table(tmp_path: Path) -> None:
    _seed_ledger(
        tmp_path,
        [
            {
                "ts": "t1", "agent": "coder", "phase": "code_generation",
                "model": "claude-sonnet-4-20250514", "duration_seconds": 1.5,
                "input_tokens": 1_000_000, "output_tokens": 1_000_000,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            },
            {
                "ts": "t2", "agent": "security_reviewer", "phase": "review:foo.py",
                "model": "claude-haiku-4-5-20251001", "duration_seconds": 0.5,
                "input_tokens": 2_000, "output_tokens": 300,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            },
        ],
    )

    out = write_summary(tmp_path)

    assert out.exists()
    assert out.name == SUMMARY_FILENAME
    body = out.read_text(encoding="utf-8")
    assert "# API Metrics Summary" in body
    assert "## Per Agent" in body
    assert "coder" in body
    assert "security_reviewer" in body
    # Sonnet should be listed first because it dominates cost.
    assert body.index("coder") < body.index("security_reviewer")
