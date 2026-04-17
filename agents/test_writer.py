"""Test Writer critic agent for the multi-agent pipeline.

Generates pytest test suites for Coder-produced source files. Reads each
file from disk, calls claude-haiku-4-5-20251001 once per file, parses a JSON
response containing test content, and writes test files to
/output/{project_name}/tests/. File contents are never stored in state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from scripts.file_writer import write_project_files
from scripts.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-haiku-4-5-20251001"
SYSTEM_PROMPT = (
    "You are a QA engineer. Your job is to break this code. "
    "Write pytest tests that test: happy path for each endpoint/function, "
    "edge cases (empty inputs, None, 0), error cases (invalid data, missing fields), "
    "boundary conditions. Assume nothing about implementation quality — red-team it."
)


def _build_user_prompt(
    source_path: Path,
    source_code: str,
    interfaces_content: str,
    shared_deps_content: str,
    expected_test_filename: str,
) -> str:
    """Assemble the per-file user prompt for test generation.

    Args:
        source_path: Path object for the source file (used for name/stem).
        source_code: Raw source code read from disk.
        interfaces_content: Contents of INTERFACES.py.
        shared_deps_content: Contents of shared_dependencies.md.
        expected_test_filename: The exact JSON key Claude must use, e.g. test_foo.py.

    Returns:
        Formatted user prompt string.
    """
    return (
        f"Generate pytest tests for the file below. "
        f'Use exactly `"{expected_test_filename}"` as the key in your JSON response.\n\n'
        f"## Source File: {source_path.name}\n\n"
        f"```python\n{source_code}\n```\n\n"
        f"## Interface Definitions (INTERFACES.py)\n\n"
        f"```python\n{interfaces_content}\n```\n\n"
        f"## Shared Dependencies (shared_dependencies.md)\n\n"
        f"{shared_deps_content}\n\n"
        f"## pytest Requirements\n\n"
        f"- Use `@pytest.fixture` for any shared setup (e.g. a test client, DB session).\n"
        f"- Use `@pytest.mark.parametrize` for testing multiple input variants of the same logic.\n"
        f"- Name tests descriptively: `test_create_user_returns_201_on_valid_input`.\n"
        f"- Include at least one happy-path, one edge-case, and one error-case test per public function.\n"
        f"- Import the module under test as: `from {source_path.stem} import ...`\n"
        f"- Do NOT use `unittest.TestCase` — plain pytest functions only.\n\n"
        f"## Output Format\n\n"
        f"Return ONLY a JSON object — no markdown fences, no preamble:\n"
        f'{{"tests": {{"{expected_test_filename}": "...full pytest source..."}}}}'
    )


def _parse_tests_json(raw: str, expected_filename: str) -> dict[str, str]:
    """Parse Claude's JSON response into a {filename: content} dict.

    Strips optional markdown fences before parsing. Validates that the
    response contains a non-empty "tests" key.

    Args:
        raw: Raw text from the Claude response.
        expected_filename: The filename we asked Claude to use as a key.

    Returns:
        Dict mapping test filename(s) to their source content.

    Raises:
        json.JSONDecodeError: If the text is not valid JSON after fence stripping.
        ValueError: If the "tests" key is missing or the dict is empty.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(text)

    if "tests" not in data or not isinstance(data["tests"], dict):
        raise ValueError(
            f"Response missing 'tests' dict key; got keys: {list(data.keys())}"
        )
    if not data["tests"]:
        raise ValueError("Response 'tests' dict is empty")

    tests: dict[str, str] = data["tests"]
    if expected_filename not in tests:
        logger.warning(
            "test_writer: expected key '%s' not in response; got %s",
            expected_filename,
            list(tests.keys()),
        )
    return tests


def run_test_writer(
    generated_file_paths: list[str],
    interfaces_path: str,
    shared_deps_path: str,
    project_name: str,
) -> list[str]:
    """Generate pytest test files for each generated source file.

    Reads each source file from disk, calls claude-haiku-4-5-20251001 once per
    file, parses a JSON response containing test file content, and writes all
    test files to /output/{project_name}/tests/. Also writes a summary markdown
    file at /output/{project_name}/tests/TEST_SUMMARY.md. File contents are
    never stored in LangGraph state.

    Args:
        generated_file_paths: Absolute paths to the Coder-produced source files.
        interfaces_path: Absolute path to INTERFACES.py on disk.
        shared_deps_path: Absolute path to shared_dependencies.md on disk.
        project_name: Output subdirectory; test files land in
            /output/{project_name}/tests/.

    Returns:
        List of absolute paths to every file written, including TEST_SUMMARY.md.

    Raises:
        ValueError: If generated_file_paths is empty.
        FileNotFoundError: If interfaces_path or shared_deps_path do not exist.
        ValueError: If write_project_files fails due to bad inputs.
        OSError: If writing files to disk fails.
    """
    if not generated_file_paths:
        raise ValueError("generated_file_paths is empty — nothing to test")

    logger.info(
        "test_writer: starting for project '%s', %d source file(s)",
        project_name,
        len(generated_file_paths),
    )

    try:
        interfaces_content = Path(interfaces_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("test_writer: INTERFACES.py not found: %s", interfaces_path)
        raise

    try:
        shared_deps_content = Path(shared_deps_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error(
            "test_writer: shared_dependencies.md not found: %s", shared_deps_path
        )
        raise

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    accumulated_tests: dict[str, str] = {}
    skipped_files: list[str] = []

    for file_path_str in generated_file_paths:
        source_path = Path(file_path_str)
        expected_test_name = f"test_{source_path.stem}.py"
        logger.info(
            "test_writer: generating tests for %s → %s",
            source_path.name,
            expected_test_name,
        )

        try:
            source_code = source_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning(
                "test_writer: source file not found, skipping: %s", file_path_str
            )
            skipped_files.append(file_path_str)
            continue

        user_prompt = _build_user_prompt(
            source_path,
            source_code,
            interfaces_content,
            shared_deps_content,
            expected_test_name,
        )

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
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
            logger.error("test_writer: API call failed for %s: %s", source_path.name, e)
            skipped_files.append(file_path_str)
            continue

        first_block = response.content[0]
        if not isinstance(first_block, anthropic.types.TextBlock):
            logger.error(
                "test_writer: unexpected block type for %s: %s",
                source_path.name,
                type(first_block),
            )
            skipped_files.append(file_path_str)
            continue

        try:
            tests_dict = _parse_tests_json(first_block.text, expected_test_name)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(
                "test_writer: JSON parse failed for %s: %s", source_path.name, e
            )
            skipped_files.append(file_path_str)
            continue

        for filename, content in tests_dict.items():
            accumulated_tests[f"tests/{filename}"] = content

        logger.debug(
            "test_writer: %d test file(s) accumulated after %s",
            len(accumulated_tests),
            source_path.name,
        )

    summary_lines = [
        "# Test Writer Summary\n\n",
        f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n",
        f"Source files processed: {len(generated_file_paths)}\n\n",
        f"Test files generated: {len(accumulated_tests)}\n\n",
    ]
    if skipped_files:
        summary_lines.append(f"## Skipped ({len(skipped_files)} files)\n\n")
        for f in skipped_files:
            summary_lines.append(f"- {f}\n")
        summary_lines.append("\n")
    summary_lines.append("## Generated Test Files\n\n")
    for key in sorted(accumulated_tests.keys()):
        summary_lines.append(f"- {key}\n")
    accumulated_tests["tests/TEST_SUMMARY.md"] = "".join(summary_lines)

    if len(accumulated_tests) == 1:
        logger.warning(
            "test_writer: no tests were successfully generated (only summary written)"
        )

    try:
        written_paths = write_project_files(accumulated_tests, project_name)
    except (ValueError, OSError) as e:
        logger.error(
            "test_writer: file_writer failed for project '%s': %s", project_name, e
        )
        raise

    logger.info(
        "test_writer: wrote %d file(s) for project '%s'",
        len(written_paths),
        project_name,
    )
    return written_paths


if __name__ == "__main__":
    _repo = Path(__file__).parent.parent
    _sample = str(_repo / "output" / "hello_ralph" / "utils" / "greeter.py")
    _interfaces = str(_repo / "context" / "INTERFACES.py")
    _shared_deps = str(_repo / "context" / "shared_dependencies.md")

    written = run_test_writer(
        generated_file_paths=[_sample],
        interfaces_path=_interfaces,
        shared_deps_path=_shared_deps,
        project_name="hello_ralph",
    )
    for p in written:
        logger.info("Smoke test wrote: %s", p)
    assert written, "Expected at least one written path"
    logger.info("run_test_writer smoke test passed.")
