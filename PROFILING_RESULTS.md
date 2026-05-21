# Profiling Results — Phase 1B Cost Baseline (HRD-08)

This document captures the per-pipeline-run cost baseline required by HRD-08 in `context/DevAssistant_TaskList_v4.md`. Phase 2 cost projections start here.

Instrumentation source: `scripts/instrumentation.py` wraps every Anthropic call and emits per-run `api_metrics.jsonl` + `api_metrics_summary.md` to `output/<run_id>/reports/`.

Pricing source: `config.MODEL_PRICING` (per-MTok rates for `claude-sonnet-4-20250514` and `claude-haiku-4-5-20251001`).

---

## Measured Cost Per Run

[USER TO FILL — run the pipeline 3 times in dry_run mode with a representative brief, then read each `output/<run_id>/reports/api_metrics_summary.md` and fill the table below.]

| Run | Brief | Total tokens (in / out) | Total cost (USD) | Duration (s) | Highest-token agent |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| **Average** | — | | | | |

**Phase 2 cost baseline:** $[X] per run (average of 3 runs above).

---

## Highest-Token Agents

[USER TO FILL — from the three runs above, list the top 2 agents by token consumption. These are the optimization targets per HRD-09.]

1. **[agent name]** — avg [N] tokens/run. [Notes on why — e.g., long system prompt, large context payload, etc.]
2. **[agent name]** — avg [N] tokens/run. [Notes.]

---

## HRD-09 Optimization Notes

Prompt caching (`cache_control: {type: "ephemeral"}`) is applied across every agent that issues a Claude call — this is one HRD-09 technique already in place.

[USER TO FILL — if any other optimizations were applied during Phase 1B, document the before/after token delta here. If none, write "No additional optimizations beyond prompt caching in Phase 1B; revisit in Phase 2."]

---

## Items Intentionally Deferred to Phase 2

- **Circular dependency detection in `task_queue`** — currently silently accepted by `_parse_task_queue_json`. See `tests/test_edge_cases.py:386-409`.
- **XML fencing on user-controlled prompt segments** — Spec Clarifier + Coder are documented as residual injection surfaces in `SECURITY.md`. Out of scope for HRD-04.
- **Interface-ref filtering optimization** — `TODO` at `graph/pipeline.py:157`.
- **e2b sandbox memory limit** — not required by HRD-06; default base template in use.
- [USER: add any other deferred items.]
