"""Security reviewer critic agent.

Applies an OWASP Top 10 mindset to generated files. Reads each file from
disk independently, calls claude-haiku-4-5-20251001 once per file, collects
structured findings, and writes a markdown report to
/output/{project_name}/security_report.md.
"""

import json
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from scripts.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """\
You are a security engineer conducting an OWASP Top 10 review of generated Python code.

Check for:
- Injection vulnerabilities: SQL injection, command injection, path traversal
- Broken authentication: no rate limiting, weak or predictable tokens, missing auth checks
- Sensitive data exposure: API keys or secrets in code, verbose error messages leaking internals
- Security misconfiguration: debug flags left on, permissive CORS, unsafe defaults
- Hardcoded secrets: passwords, tokens, keys assigned as string literals
- Insecure direct object references: user-controlled IDs used directly without authorization checks

Respond with ONLY a valid JSON array of findings. Each finding must have exactly these keys:
  "severity": "high" | "medium" | "low"
  "issue": short description of the vulnerability
  "location": filename and approximate line number or function name
  "remediation": concrete fix description

If no issues are found, respond with an empty array: []

Do not include any text outside the JSON array.
"""

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


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


def run_security_reviewer(
    generated_file_paths: list[str],
    shared_deps_path: str,
    run_dir: str,
    e2b_output: dict | None = None,
) -> str:
    """Review generated files for security issues and write a markdown report.

    Reads each file at generated_file_paths from disk, calls Haiku once per
    file with an OWASP-focused prompt, aggregates structured findings, and
    writes run_dir/reports/security_report.md.

    Args:
        generated_file_paths: Absolute paths to the Python files to review.
        shared_deps_path: Absolute path to shared_dependencies.md (provides
            env-var definitions and cross-file contracts as context).
        run_dir: Absolute path to the run workspace.

    Returns:
        Absolute path to the written security_report.md as a string.

    Raises:
        anthropic.APIError: If a Claude API call fails unrecoverably.
    """
    logger.info(
        "Security reviewer starting: %d files, run_dir=%s",
        len(generated_file_paths),
        run_dir,
    )

    try:
        shared_deps = Path(shared_deps_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(
            "shared_deps_path not found: %s — proceeding without it", shared_deps_path
        )
        shared_deps = "(shared_dependencies.md not available)"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    all_findings: list[dict] = []

    for file_path in generated_file_paths:
        source_path = Path(file_path)
        logger.info("Security reviewing: %s", file_path)

        try:
            source_code = source_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("File not found, skipping: %s", file_path)
            continue

        user_prompt = (
            f"File to review: `{source_path.name}`\n\n"
            f"## Shared Dependencies Context\n\n{shared_deps}\n\n"
            f"## File Contents\n\n```python\n{source_code}\n```\n\n"
            "Return ONLY a JSON array of findings as described in the system prompt."
            f"{_format_e2b_block(e2b_output)}"
        )

        try:
            response = client.messages.create(
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
                    "severity": "high",
                    "issue": "Security reviewer failed to parse Claude response — manual review required",
                    "location": source_path.name,
                    "remediation": "Manually inspect this file for OWASP Top 10 vulnerabilities",
                }
            ]

        for finding in findings:
            finding.setdefault("location", source_path.name)

        logger.debug("Found %d issues in %s", len(findings), source_path.name)
        all_findings.extend(findings)

    all_findings.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "low"), 2))

    report = _render_report(all_findings)

    output_path = Path(run_dir) / "reports" / "security_report.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    logger.info(
        "Security report written: %s (%d findings)",
        output_path,
        len(all_findings),
    )
    return str(output_path)


def _render_report(findings: list[dict]) -> str:
    """Render aggregated findings as a markdown security report.

    Args:
        findings: List of finding dicts sorted by severity.

    Returns:
        Formatted markdown string.
    """
    high = sum(1 for f in findings if f.get("severity") == "high")
    medium = sum(1 for f in findings if f.get("severity") == "medium")
    low = sum(1 for f in findings if f.get("severity") == "low")
    total = len(findings)

    lines = [
        "# Security Review Report",
        "",
        "## Summary",
        "",
        f"{total} finding{'s' if total != 1 else ''}: {high} high, {medium} medium, {low} low",
        "",
    ]

    if not findings:
        lines += ["No security issues detected.", ""]
        return "\n".join(lines)

    lines += ["## Findings", ""]

    for finding in findings:
        severity = finding.get("severity", "unknown").upper()
        issue = finding.get("issue", "")
        location = finding.get("location", "unknown")
        remediation = finding.get("remediation", "")

        lines += [
            f"### [{severity}] {issue} — {location}",
            "",
            f"**Issue:** {issue}",
            "",
            f"**Remediation:** {remediation}",
            "",
        ]

    return "\n".join(lines)
