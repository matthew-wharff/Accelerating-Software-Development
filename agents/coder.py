from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from scripts.file_writer import write_project_files
from scripts.logger import get_logger

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-20250514"
SHARED_DEPS_PATH = Path(__file__).parent.parent / "context" / "shared_dependencies.md"

_SYSTEM_PROMPT_EXTRACTOR = """\
You are a code analysis tool. Extract the public interface from Python source code.

Return ONLY a structured summary in this exact format:

### Functions
def function_name(param: type, ...) -> return_type
(one line per public function; omit private functions starting with _)

### Classes
class ClassName:
    attr: type
    def method(self, ...) -> return_type
(one block per public class; method signatures only, no bodies)

### Module-Level Constants
CONSTANT_NAME: type = value
(only if exported in __all__ or clearly public)

Rules:
- Include ALL public symbols.
- Exclude ALL private symbols (names starting with _).
- No function bodies. Signatures only.
- No docstrings. Names and types only.
- No markdown fences. Return raw text only.
- If the file has no public symbols, return the single line: # No public interface\
"""


def run_coder_task(
    task: dict,
    shared_deps: str,
    relevant_interfaces: str,
    prior_signatures: str,
    conventions: str,
) -> tuple[str, str]:
    """Generate one file via the Ralph Loop: generate → write → extract interface.

    Makes two sequential Claude API calls: the first generates the source code,
    the second extracts its public interface. Writes the file to disk immediately
    after generation. Appends the extracted interface to shared_dependencies.md.
    Implementation code never re-enters the context window after disk write.

    Args:
        task: Dict with required keys:
            task_id (str): Unique identifier for this task.
            target_file (str): Relative path of the file to generate (e.g. "api/routes.py").
            description (str): Plain-English description of what to implement.
            project_name (str): Used as the output subdirectory under /output/.
            Optional keys: interface_refs (list[str]), dependency_paths (list[str]).
        shared_deps: Full content of shared_dependencies.md.
        relevant_interfaces: Interface definitions from INTERFACES.py relevant to
            this task only (pass "" if none apply).
        prior_signatures: Public signatures of files this task depends on
            (function sigs and class headers only — never full implementations).
        conventions: Content of CONVENTIONS.md.

    Returns:
        Tuple of (file_path, extracted_public_interface) where file_path is the
        absolute path of the written file and extracted_public_interface is a
        compact signature summary suitable for injecting as prior_signatures in
        subsequent tasks.

    Raises:
        KeyError: If required task keys (task_id, target_file, description,
            project_name) are missing.
        anthropic.APIError: If the code generation API call fails.
        ValueError: If write_project_files rejects the filename.
        OSError: If the disk write fails.
    """
    task_id: str = task["task_id"]
    target_file: str = task["target_file"]
    description: str = task["description"]
    project_name: str = task["project_name"]

    logger.info("Coder starting task %s: %s", task_id, target_file)

    # --- Call 1: Code generation ---

    system_prompt = (
        "You are an expert software developer implementing a single file in a multi-file project.\n\n"
        "## Coding Conventions\n\n"
        f"{conventions}\n\n"
        "## Shared Dependencies Manifest\n\n"
        "The following manifest describes every cross-file contract in this project. "
        "Your implementation MUST be compatible with these contracts.\n\n"
        f"{shared_deps}\n\n"
        "Rules:\n"
        "- Implement ONLY the file specified in the task. Do not generate other files.\n"
        "- Satisfy all relevant interface contracts from the shared dependencies manifest.\n"
        "- Return ONLY raw source code — no markdown fences, no explanations, no preamble.\n"
        "- The first line of your response must be valid source code (an import, a comment, "
        "or a definition).\n"
        "- Follow ALL coding conventions listed above exactly."
    )

    user_prompt_parts = [
        "Implement the following file.\n\n",
        "## Task\n",
        f"Task ID: {task_id}\n",
        f"Target file: {target_file}\n",
        f"Description: {description}\n",
    ]
    if relevant_interfaces:
        user_prompt_parts.append(
            f"\n## Relevant Interfaces (signatures only — do NOT implement these, satisfy them)\n"
            f"{relevant_interfaces}\n"
        )
    if prior_signatures:
        user_prompt_parts.append(
            f"\n## Prior Dependency Signatures (public signatures only — never full source)\n"
            f"{prior_signatures}\n"
        )
    user_prompt_parts.append(
        f"\nReturn ONLY the complete source code for `{target_file}`. "
        "No markdown fences, no explanations, no preamble — raw source code only. "
        "The first line must be valid Python."
    )
    user_prompt = "".join(user_prompt_parts)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        gen_response = client.messages.create(
            model=MODEL,
            max_tokens=8192,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIError as e:
        logger.error("Coder generation API call failed for %s: %s", target_file, e)
        raise

    generated_code = ""
    for block in gen_response.content:
        if isinstance(block, anthropic.types.TextBlock):
            generated_code = block.text
            break

    if not generated_code:
        raise ValueError(f"No text content returned for {target_file}")

    logger.info("Coder received %d chars for %s", len(generated_code), target_file)

    # --- Write to disk immediately — implementation never re-enters context ---

    try:
        written_paths = write_project_files({target_file: generated_code}, project_name)
    except (ValueError, OSError) as e:
        logger.error("Coder disk write failed for %s: %s", target_file, e)
        raise

    file_path = written_paths[0]
    logger.info("Coder wrote %s", file_path)

    # --- Call 2: Interface extraction ---

    extraction_user_prompt = (
        f"Extract the public interface from this file.\n\n"
        f"## File: {target_file}\n\n"
        f"{generated_code}"
    )

    try:
        ext_response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT_EXTRACTOR,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": extraction_user_prompt}],
        )
        extracted_interface = ""
        for block in ext_response.content:
            if isinstance(block, anthropic.types.TextBlock):
                extracted_interface = block.text
                break
        if not extracted_interface:
            raise ValueError("Empty extraction response")
    except (anthropic.APIError, ValueError) as e:
        logger.warning(
            "Interface extraction failed for %s (non-fatal): %s", target_file, e
        )
        extracted_interface = f"# Interface extraction failed for {target_file}\n"

    # --- Append interface to shared_dependencies.md ---

    try:
        existing = SHARED_DEPS_PATH.read_text(encoding="utf-8")
        entry = f"\n\n---\n\n### `{target_file}`\n\n{extracted_interface}\n"
        SHARED_DEPS_PATH.write_text(existing.rstrip() + entry, encoding="utf-8")
        logger.info("Appended interface for %s to shared_dependencies.md", target_file)
    except OSError as e:
        logger.warning(
            "Could not append interface to shared_dependencies.md for %s (non-fatal): %s",
            target_file,
            e,
        )

    return file_path, extracted_interface


if __name__ == "__main__":
    conventions_path = Path(__file__).parent.parent / "context" / "CONVENTIONS.md"
    conventions_content = conventions_path.read_text(encoding="utf-8")
    shared_deps_content = SHARED_DEPS_PATH.read_text(encoding="utf-8")

    sample_task = {
        "task_id": "task_001",
        "target_file": "utils/greeter.py",
        "description": (
            "Implement a utility module with a single public function "
            "`greet(name: str) -> str` that returns 'Hello, {name}!'. "
            "Include a Google-style docstring and type annotations."
        ),
        "interface_refs": [],
        "dependency_paths": [],
        "project_name": "hello_ralph",
    }

    file_path, public_interface = run_coder_task(
        task=sample_task,
        shared_deps=shared_deps_content,
        relevant_interfaces="",
        prior_signatures="",
        conventions=conventions_content,
    )

    logger.info("Generated file at: %s", file_path)
    logger.info("Extracted interface:\n%s", public_interface)

    assert Path(file_path).exists(), f"Expected file on disk: {file_path}"
    assert public_interface.strip(), "Expected non-empty interface summary"
    logger.info("run_coder_task smoke test passed.")
