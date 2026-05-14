"""DevOps agent — generates infrastructure files from spec and dependency manifest.

Reads ARCHITECT_SPEC.md (for tech stack) and shared_dependencies.md (for env var
definitions). Makes a single Claude call and writes four files to
/output/{project_name}/: Dockerfile, .github/workflows/ci.yml, .env.example,
docker-compose.yml.

Does NOT receive generated source code — only the spec and dependency manifest.
"""

import json
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from scripts.file_writer import write_project_files
from scripts.instrumentation import instrumented_call
from scripts.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-20250514"

_SYSTEM_PROMPT = """\
You are a senior DevOps engineer. Produce production-quality infrastructure files.

Rules:
- Use multi-stage Docker builds: a `builder` stage that installs dependencies and a
  `runtime` stage that copies only the application code and installed packages. Keep the
  final image as small as possible.
- The CI pipeline must run the full test suite via pytest. Steps: checkout code, set up
  Python (match the version in the spec), install dependencies from requirements.txt, run
  pytest, report pass/fail.
- Never hardcode secrets. Reference them as environment variables (e.g. ${MY_SECRET} in
  Dockerfile/docker-compose, ${{ secrets.MY_SECRET }} in GitHub Actions).
- .env.example must list every environment variable the application needs with placeholder
  values and a short comment describing each.
- docker-compose.yml must wire the service together using env_file: .env so local
  development works without hardcoded values.

Respond with ONLY a valid JSON object with exactly these four keys:
  "Dockerfile"
  ".github/workflows/ci.yml"
  ".env.example"
  "docker-compose.yml"

Each value is the complete file content as a string. Do not include any text outside the
JSON object.
"""


def _parse_devops_json(raw: str) -> dict[str, str]:
    """Extract the JSON object from the model response.

    Args:
        raw: Raw text returned by the model.

    Returns:
        Dict mapping filename to file content.

    Raises:
        RuntimeError: If the response cannot be parsed as valid JSON.
    """
    text = raw.strip()
    # Strip optional markdown code fence
    if text.startswith("```"):
        first_newline = text.find("\n")
        last_fence = text.rfind("```")
        if first_newline != -1 and last_fence > first_newline:
            text = text[first_newline + 1 : last_fence].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"DevOps agent returned invalid JSON: {exc}\n\nRaw:\n{raw[:500]}"
        ) from exc

    required = {
        "Dockerfile",
        ".github/workflows/ci.yml",
        ".env.example",
        "docker-compose.yml",
    }
    missing = required - data.keys()
    if missing:
        raise RuntimeError(f"DevOps agent response missing keys: {missing}")
    return {k: data[k] for k in required}


def run_devops(
    architect_spec_path: str,
    shared_deps_path: str,
    run_dir: str,
) -> list[str]:
    """Generate infrastructure files from the architecture spec and dependency manifest.

    Reads ARCHITECT_SPEC.md and shared_dependencies.md from disk, makes a single
    Claude call, and writes four files into run_dir/code/.

    Args:
        architect_spec_path: Absolute path to ARCHITECT_SPEC.md.
        shared_deps_path: Absolute path to shared_dependencies.md.
        run_dir: Absolute path to the run workspace.

    Returns:
        List of absolute paths to the four written files.

    Raises:
        RuntimeError: If the model response cannot be parsed or required keys are absent.
        OSError: If input files cannot be read or output files cannot be written.
    """
    try:
        spec_text = Path(architect_spec_path).read_text(encoding="utf-8")
    except OSError as exc:
        logger.error(
            "run_devops: cannot read architect spec at %s: %s", architect_spec_path, exc
        )
        raise

    try:
        shared_deps_text = Path(shared_deps_path).read_text(encoding="utf-8")
    except OSError as exc:
        logger.error(
            "run_devops: cannot read shared deps at %s: %s", shared_deps_path, exc
        )
        raise

    user_prompt = (
        "## Architecture Spec\n\n"
        f"{spec_text}\n\n"
        "## Shared Dependencies & Environment Variables\n\n"
        f"{shared_deps_text}\n\n"
        "Generate the four infrastructure files described in the system prompt."
    )

    logger.info("run_devops: calling %s for run_dir '%s'", MODEL, run_dir)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = instrumented_call(
        client,
        agent="devops",
        phase="infra_generation",
        run_dir=run_dir,
        model=MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = message.content[0].text
    logger.debug("run_devops: received %d chars from model", len(raw))

    files = _parse_devops_json(raw)

    try:
        written_paths = write_project_files(files, Path(run_dir) / "code")
    except Exception as exc:
        logger.error("run_devops: failed to write output files: %s", exc)
        raise

    for path in written_paths:
        logger.info("run_devops: wrote %s", path)

    return written_paths
