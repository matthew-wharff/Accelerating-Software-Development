"""Time and cost instrumentation for Anthropic API calls.

Wraps every ``client.messages.create()`` call across the pipeline with
``time.perf_counter`` and ``response.usage`` capture. Each call appends a
single JSON line to ``<run_dir>/reports/api_metrics.jsonl`` and emits a
structured log line. At the end of a run, ``summarize_run`` reads the
JSONL, groups by agent, and applies the per-model pricing table from
``config.MODEL_PRICING`` to produce a phase-2 cost baseline.

Cost model (matches https://platform.claude.com/docs/en/about-claude/pricing):

- Standard input tokens billed at ``MODEL_PRICING[model]["input"]``.
- 5-minute cache writes billed at ``MODEL_PRICING[model]["cache_write_5m"]``
  (1.25x input).
- Cache reads billed at ``MODEL_PRICING[model]["cache_read"]`` (0.1x input).
- Output tokens billed at ``MODEL_PRICING[model]["output"]``.

The ``cache_creation_input_tokens`` count returned by the SDK already
excludes the regular ``input_tokens``, so the three input buckets do not
overlap and are summed.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from config import MODEL_PRICING
from scripts.logger import get_logger

logger = get_logger(__name__)

METRICS_FILENAME = "api_metrics.jsonl"
SUMMARY_FILENAME = "api_metrics_summary.md"


@dataclass(frozen=True)
class ApiCallMetric:
    """One row in the per-run metrics ledger.

    Attributes:
        ts: ISO-8601 UTC timestamp the call returned.
        agent: Logical agent that issued the call (e.g. ``"coder"``).
        phase: Sub-step within the agent (e.g. ``"code_generation"``).
        model: Model id passed to the API.
        duration_seconds: Wall-clock duration of the API call.
        input_tokens: Uncached input tokens billed at the base rate.
        output_tokens: Output tokens billed at the output rate.
        cache_creation_input_tokens: Tokens written to the 5-minute cache.
        cache_read_input_tokens: Tokens served from a prior cache write.
    """

    ts: str
    agent: str
    phase: str
    model: str
    duration_seconds: float
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int


def metrics_path_for(run_dir: str | Path) -> Path:
    """Return the canonical metrics JSONL path for a run directory.

    Args:
        run_dir: Absolute path to the run workspace.

    Returns:
        ``<run_dir>/reports/api_metrics.jsonl`` as a Path. Not created.
    """
    return Path(run_dir) / "reports" / METRICS_FILENAME


def _append_metric(run_dir: str | Path, metric: ApiCallMetric) -> None:
    """Append a single metric record as a JSON line.

    POSIX append semantics are atomic for writes under PIPE_BUF (4 KB),
    so parallel critic invocations can write to the same file without
    a lock as long as each line fits in one ``write()`` syscall.

    Args:
        run_dir: Absolute path to the run workspace.
        metric: The record to append.
    """
    target = metrics_path_for(run_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(metric), separators=(",", ":")) + "\n"
    with target.open("a", encoding="utf-8") as fh:
        fh.write(line)


def instrumented_call(
    client: anthropic.Anthropic,
    *,
    agent: str,
    phase: str,
    run_dir: str | Path | None,
    **kwargs: Any,
) -> Any:
    """Call ``client.messages.create(**kwargs)`` and record duration + usage.

    The response object is returned unchanged so existing callers do not
    need to be rewritten beyond the function-name swap. When ``run_dir``
    is ``None`` the metric is logged but not persisted — useful for tests
    and ad-hoc smoke runs outside the pipeline.

    Args:
        client: Initialised Anthropic SDK client.
        agent: Logical agent making the call.
        phase: Sub-step label within the agent.
        run_dir: Run workspace root, or ``None`` to skip disk persistence.
        **kwargs: Forwarded verbatim to ``client.messages.create``.

    Returns:
        The raw ``Message`` response from the SDK.

    Raises:
        anthropic.APIError: Re-raised after the duration is recorded so
            failed calls still surface in logs (though they are not
            written to the JSONL because there is no ``usage`` payload).
    """
    model = kwargs.get("model", "unknown")
    t0 = time.perf_counter()
    try:
        response = client.messages.create(**kwargs)
    except anthropic.APIError:
        duration = time.perf_counter() - t0
        logger.error(
            "api_call_failed agent=%s phase=%s model=%s duration=%.3fs",
            agent,
            phase,
            model,
            duration,
        )
        raise
    duration = time.perf_counter() - t0

    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_creation = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)

    metric = ApiCallMetric(
        ts=datetime.now(timezone.utc).isoformat(),
        agent=agent,
        phase=phase,
        model=model,
        duration_seconds=round(duration, 3),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
    )

    logger.info(
        "api_call agent=%s phase=%s model=%s duration=%.2fs "
        "in=%d out=%d cache_write=%d cache_read=%d",
        agent,
        phase,
        model,
        duration,
        input_tokens,
        output_tokens,
        cache_creation,
        cache_read,
    )

    if run_dir is not None:
        try:
            _append_metric(run_dir, metric)
        except OSError as exc:
            logger.warning(
                "instrumentation: could not append metric to %s: %s",
                metrics_path_for(run_dir),
                exc,
            )

    return response


def calculate_cost_usd(metric: dict[str, Any] | ApiCallMetric) -> float:
    """Compute USD cost for a single metric record.

    Unknown model ids cost zero so missing pricing entries do not crash
    a run — the surface is the log warning, which prompts an update to
    ``MODEL_PRICING``.

    Args:
        metric: Either an ``ApiCallMetric`` or a dict with the same keys.

    Returns:
        Cost in USD for that single API call.
    """
    if isinstance(metric, ApiCallMetric):
        data = asdict(metric)
    else:
        data = metric

    pricing = MODEL_PRICING.get(data["model"])
    if pricing is None:
        logger.warning(
            "instrumentation: no pricing for model %r — cost reported as $0.00",
            data["model"],
        )
        return 0.0

    per_mtok = 1_000_000
    return (
        data["input_tokens"] * pricing["input"] / per_mtok
        + data["output_tokens"] * pricing["output"] / per_mtok
        + data["cache_creation_input_tokens"] * pricing["cache_write_5m"] / per_mtok
        + data["cache_read_input_tokens"] * pricing["cache_read"] / per_mtok
    )


def _empty_bucket() -> dict[str, Any]:
    """Return a fresh per-agent aggregation bucket."""
    return {
        "calls": 0,
        "duration_seconds": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "cost_usd": 0.0,
        "models": set(),
    }


def summarize_run(run_dir: str | Path) -> dict[str, Any]:
    """Aggregate the metrics JSONL for one run into per-agent totals.

    Reads ``<run_dir>/reports/api_metrics.jsonl`` line-by-line, groups
    records by ``agent``, sums token counts and durations, and applies
    ``calculate_cost_usd`` per record so cache-read vs. cache-write
    pricing is preserved in the totals.

    Args:
        run_dir: Absolute path to the run workspace.

    Returns:
        Dict with three keys:
            ``by_agent``: ``{agent_name: aggregated_bucket}``.
            ``total``: overall aggregated bucket across every agent.
            ``records``: list of every metric dict in chronological order.

        The aggregated bucket contains ``calls``, ``duration_seconds``,
        token counts split four ways, ``cost_usd``, and ``models`` (a
        sorted list of model ids that contributed).
    """
    path = metrics_path_for(run_dir)
    if not path.exists():
        logger.info("instrumentation: no metrics file at %s", path)
        return {"by_agent": {}, "total": _finalise_bucket(_empty_bucket()), "records": []}

    by_agent: dict[str, dict[str, Any]] = {}
    total = _empty_bucket()
    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as fh:
        for line_number, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "instrumentation: skipping malformed metric line %d in %s: %s",
                    line_number,
                    path,
                    exc,
                )
                continue
            cost = calculate_cost_usd(record)
            record["cost_usd"] = round(cost, 6)
            records.append(record)

            bucket = by_agent.setdefault(record["agent"], _empty_bucket())
            for target in (bucket, total):
                target["calls"] += 1
                target["duration_seconds"] += record["duration_seconds"]
                target["input_tokens"] += record["input_tokens"]
                target["output_tokens"] += record["output_tokens"]
                target["cache_creation_input_tokens"] += record[
                    "cache_creation_input_tokens"
                ]
                target["cache_read_input_tokens"] += record["cache_read_input_tokens"]
                target["cost_usd"] += cost
                target["models"].add(record["model"])

    return {
        "by_agent": {name: _finalise_bucket(b) for name, b in by_agent.items()},
        "total": _finalise_bucket(total),
        "records": records,
    }


def _finalise_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    """Convert a working bucket into a JSON-serialisable summary."""
    return {
        "calls": bucket["calls"],
        "duration_seconds": round(bucket["duration_seconds"], 3),
        "input_tokens": bucket["input_tokens"],
        "output_tokens": bucket["output_tokens"],
        "cache_creation_input_tokens": bucket["cache_creation_input_tokens"],
        "cache_read_input_tokens": bucket["cache_read_input_tokens"],
        "cost_usd": round(bucket["cost_usd"], 6),
        "models": sorted(bucket["models"]),
    }


def write_summary(run_dir: str | Path) -> Path:
    """Render a markdown cost report at ``<run_dir>/reports/api_metrics_summary.md``.

    Designed to be called once per run after the pipeline completes. The
    file shows total cost, per-agent breakdown ordered by spend, and the
    raw call count per phase so it is obvious which agent dominates.

    Args:
        run_dir: Absolute path to the run workspace.

    Returns:
        Absolute path to the written markdown summary.
    """
    summary = summarize_run(run_dir)
    total = summary["total"]

    lines: list[str] = [
        "# API Metrics Summary",
        "",
        f"_Run directory:_ `{run_dir}`",
        f"_Generated:_ {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Totals",
        "",
        f"- API calls: **{total['calls']}**",
        f"- Wall-clock duration: **{total['duration_seconds']:.2f}s**",
        f"- Input tokens (uncached): **{total['input_tokens']:,}**",
        f"- Cache write tokens: **{total['cache_creation_input_tokens']:,}**",
        f"- Cache read tokens: **{total['cache_read_input_tokens']:,}**",
        f"- Output tokens: **{total['output_tokens']:,}**",
        f"- **Cost: ${total['cost_usd']:.4f}**",
        "",
        "## Per Agent",
        "",
        "| Agent | Calls | Duration (s) | Input | Cache W | Cache R | Output | Cost (USD) | Models |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    by_agent_sorted = sorted(
        summary["by_agent"].items(), key=lambda kv: kv[1]["cost_usd"], reverse=True
    )
    for agent_name, bucket in by_agent_sorted:
        lines.append(
            "| {agent} | {calls} | {dur:.2f} | {ti:,} | {cw:,} | {cr:,} | {to:,} "
            "| ${cost:.4f} | {models} |".format(
                agent=agent_name,
                calls=bucket["calls"],
                dur=bucket["duration_seconds"],
                ti=bucket["input_tokens"],
                cw=bucket["cache_creation_input_tokens"],
                cr=bucket["cache_read_input_tokens"],
                to=bucket["output_tokens"],
                cost=bucket["cost_usd"],
                models=", ".join(bucket["models"]) or "—",
            )
        )

    lines += ["", "## Pricing applied", ""]
    for model, prices in MODEL_PRICING.items():
        lines.append(
            f"- `{model}`: input ${prices['input']}/MTok · "
            f"cache write 5m ${prices['cache_write_5m']}/MTok · "
            f"cache read ${prices['cache_read']}/MTok · "
            f"output ${prices['output']}/MTok"
        )

    out_path = Path(run_dir) / "reports" / SUMMARY_FILENAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("instrumentation: wrote summary to %s", out_path)
    return out_path
