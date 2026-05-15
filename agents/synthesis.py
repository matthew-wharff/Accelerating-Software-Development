"""Synthesis agent — context firewall between critics and the revision cycle.

Reads the three critic report files from disk, consolidates them into a single
structured SYNTHESIS_REPORT.md written to /context/, and returns the path plus
a boolean indicating whether blocking issues were found.

The Architect receives only the synthesis report path — never raw critic outputs.
The Coder never sees unfiltered critic feedback.
"""

from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from scripts.instrumentation import instrumented_call
from scripts.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-20250514"

_SYSTEM_PROMPT = (
    "You are a tech lead consolidating PR review feedback from three reviewers. "
    "Remove duplicate observations. Resolve conflicts by prioritizing security > correctness > style. "
    "Order items by severity within each priority tier. "
    "Output a concise, structured action list — not raw reviewer transcripts."
)

_OUTPUT_FORMAT = """\
Respond with ONLY the following markdown structure — no preamble, no commentary outside it:

# Synthesis Report

## High Priority Fixes
- <item or "None">

## Medium Priority Fixes
- <item or "None">

## Low Priority Fixes
- <item or "None">

## Blocking Issues
has_blocking_issues: true|false
"""


def _call_claude(
    system_prompt: str, user_prompt: str, run_dir: str | None = None
) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = instrumented_call(
        client,
        agent="synthesis",
        phase="consolidate_feedback",
        run_dir=run_dir,
        model=MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )
    for block in response.content:
        if isinstance(block, anthropic.types.TextBlock):
            return block.text
    return ""


def _read_report(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Synthesis: report file not found, skipping: %s", path)
        return ""


def _parse_blocking(text: str) -> bool:
    """Extract has_blocking_issues value from synthesis output."""
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("has_blocking_issues:"):
            value = stripped.split(":", 1)[1].strip()
            return value == "true"
    # Treat any high-priority content as blocking if flag is missing
    return "## high priority fixes" in text.lower() and "none" not in text.lower()


def run_synthesis(
    test_feedback_path: str | None,
    security_feedback_path: str | None,
    quality_feedback_path: str | None,
    out_path: str,
    run_dir: str | None = None,
) -> tuple[str, bool]:
    """Consolidate critic reports into a single SYNTHESIS_REPORT.md.

    Reads each report file from disk, calls Claude Sonnet to de-duplicate and
    prioritize findings, then writes the result to out_path (pre-set by workspace_node).
    Raw critic outputs never leave this function — only the synthesis path is
    returned.

    Args:
        test_feedback_path: Absolute path to the test writer report, or None.
        security_feedback_path: Absolute path to the security reviewer report, or None.
        quality_feedback_path: Absolute path to the code quality report, or None.
        out_path: Absolute path where SYNTHESIS_REPORT.md should be written.

    Returns:
        A tuple of (absolute path to SYNTHESIS_REPORT.md as str, has_blocking_issues bool).

    Raises:
        anthropic.APIError: If the Claude API call fails.
        OSError: If writing SYNTHESIS_REPORT.md fails.
    """
    logger.info("synthesis: reading critic reports")

    test_content = _read_report(test_feedback_path)
    security_content = _read_report(security_feedback_path)
    quality_content = _read_report(quality_feedback_path)

    user_prompt = (
        "## Test Writer Report\n\n"
        f"{test_content or '(no report)'}\n\n"
        "## Security Reviewer Report\n\n"
        f"{security_content or '(no report)'}\n\n"
        "## Code Quality Report\n\n"
        f"{quality_content or '(no report)'}\n\n"
        f"{_OUTPUT_FORMAT}"
    )

    logger.info("synthesis: calling Claude to consolidate feedback")
    try:
        raw = _call_claude(_SYSTEM_PROMPT, user_prompt, run_dir=run_dir)
    except anthropic.APIError as e:
        logger.error("synthesis: Claude API call failed: %s", e)
        raise

    has_blocking = _parse_blocking(raw)

    out_path_obj = Path(out_path)
    try:
        out_path_obj.write_text(raw, encoding="utf-8")
    except OSError as e:
        logger.error("synthesis: failed to write SYNTHESIS_REPORT.md: %s", e)
        raise

    logger.info(
        "synthesis: report written to %s (has_blocking_issues=%s)",
        out_path,
        has_blocking,
    )
    return out_path, has_blocking
