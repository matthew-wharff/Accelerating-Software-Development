"""Code quality critic agent.

Evaluates generated files for maintainability and style using the same
CONVENTIONS.md the Coder received. Reads each file from disk independently,
calls claude-haiku-4-5-20251001 once per file, collects structured findings,
and writes /output/{project_name}/quality_report.md.
"""

import json
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from scripts.instrumentation import instrumented_call
from scripts.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """\
You are a senior engineer doing a PR review before merging to main. Check for: \
PEP 8 violations, missing docstrings on public functions/classes, functions longer \
than 50 lines (should be split), unhandled exceptions, magic numbers without \
constants, missing type annotations on function signatures, duplicate code that \
should be extracted. Be specific — reference the function or class name.

Respond with ONLY a valid JSON array of findings. Each finding must have exactly these keys:
  "category": "style" | "docs" | "edge-case" | "maintainability"
  "issue": short description of the problem
  "location": filename and function or class name (or approximate line number)
  "suggestion": concrete fix description

If no issues are found, respond with an empty array: []

Do not include any text outside the JSON array.
"""

_CATEGORY_ORDER = {"style": 0, "docs": 1, "edge-case": 2, "maintainability": 3}


def _format_e2b_block(e2b_output: dict | None) -> str:
    """Format sandbox runtime output as a markdown section for critic prompts.

    Args:
        e2b_output: Dict with stdout, stderr, exit_code keys, or None.

    Returns:
        Formatted markdown string, or empty string if no output available.
    """
    if not e2b_output:
        return ""
    stdout = e2b_output.get("stdout") or "(none)"
    stderr = e2b_output.get("stderr") or "(none)"
    exit_code = e2b_output.get("exit_code", "N/A")
    return (
        "\n---\n\n"
        "## Runtime Output (e2b sandbox)\n\n"
        f"**Exit code:** {exit_code}\n\n"
        f"**stdout:**\n```\n{stdout}\n```\n\n"
        f"**stderr:**\n```\n{stderr}\n```\n\n"
        "The code produced this output when run. Use it to inform your review.\n"
    )


def run_code_quality(
    generated_file_paths: list[str],
    conventions: str,
    run_dir: str,
    e2b_output: dict | None = None,
) -> str:
    """Review generated files for maintainability and style, write a markdown report.

    Reads each file at generated_file_paths from disk, calls Haiku once per file
    with the project conventions as context, aggregates structured findings, and
    writes run_dir/reports/quality_report.md.

    Args:
        generated_file_paths: Absolute paths to the Python files to review.
        conventions: Full text of CONVENTIONS.md — the same standards the Coder used.
        run_dir: Absolute path to the run workspace.

    Returns:
        Absolute path to the written quality_report.md as a string.

    Raises:
        anthropic.APIError: If a Claude API call fails unrecoverably.
    """
    logger.info(
        "Code quality reviewer starting: %d files, run_dir=%s",
        len(generated_file_paths),
        run_dir,
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    all_findings: list[dict] = []

    for file_path in generated_file_paths:
        source_path = Path(file_path)
        logger.info("Code quality reviewing: %s", file_path)

        try:
            source_code = source_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("File not found, skipping: %s", file_path)
            continue

        user_prompt = (
            f"File to review: `{source_path.name}`\n\n"
            f"## Project Conventions\n\n{conventions}\n\n"
            f"## File Contents\n\n```python\n{source_code}\n```\n\n"
            "Return ONLY a JSON array of findings as described in the system prompt."
            f"{_format_e2b_block(e2b_output)}"
        )

        try:
            response = instrumented_call(
                client,
                agent="code_quality",
                phase=f"review:{source_path.name}",
                run_dir=run_dir,
                model=MODEL,
                max_tokens=2048,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as e:
            logger.error("Claude API call failed for %s: %s", file_path, e)
            raise

        raw_text = ""
        for block in response.content:
            if isinstance(block, anthropic.types.TextBlock):
                raw_text = block.text
                break

        try:
            findings: list[dict] = json.loads(raw_text)
            if not isinstance(findings, list):
                raise ValueError("Expected a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error("Failed to parse findings for %s: %s", file_path, e)
            findings = [
                {
                    "category": "maintainability",
                    "issue": "Code quality reviewer failed to parse Claude response — manual review required",
                    "location": source_path.name,
                    "suggestion": "Manually inspect this file against CONVENTIONS.md",
                }
            ]

        for finding in findings:
            finding.setdefault("location", source_path.name)

        logger.debug("Found %d issues in %s", len(findings), source_path.name)
        all_findings.extend(findings)

    all_findings.sort(
        key=lambda f: _CATEGORY_ORDER.get(f.get("category", "maintainability"), 3)
    )

    report = _render_report(all_findings)

    output_path = Path(run_dir) / "reports" / "quality_report.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    logger.info(
        "Quality report written: %s (%d findings)",
        output_path,
        len(all_findings),
    )
    return str(output_path)


def _render_report(findings: list[dict]) -> str:
    """Render aggregated findings as a markdown quality report.

    Args:
        findings: List of finding dicts sorted by category.

    Returns:
        Formatted markdown string.
    """
    style = sum(1 for f in findings if f.get("category") == "style")
    docs = sum(1 for f in findings if f.get("category") == "docs")
    edge_case = sum(1 for f in findings if f.get("category") == "edge-case")
    maintainability = sum(1 for f in findings if f.get("category") == "maintainability")
    total = len(findings)

    lines = [
        "# Code Quality Report",
        "",
        "## Summary",
        "",
        f"{total} finding{'s' if total != 1 else ''}: "
        f"{style} style, {docs} docs, {edge_case} edge-case, {maintainability} maintainability",
        "",
    ]

    if not findings:
        lines += ["No quality issues detected.", ""]
        return "\n".join(lines)

    lines += ["## Findings", ""]

    for finding in findings:
        category = finding.get("category", "unknown").upper()
        issue = finding.get("issue", "")
        location = finding.get("location", "unknown")
        suggestion = finding.get("suggestion", "")

        lines += [
            f"### [{category}] {issue} — {location}",
            "",
            f"**Issue:** {issue}",
            "",
            f"**Suggestion:** {suggestion}",
            "",
        ]

    return "\n".join(lines)
