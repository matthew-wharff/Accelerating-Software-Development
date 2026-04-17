from __future__ import annotations

import json
import re
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from scripts.logger import get_logger
from state.schema import TaskEntry

logger = get_logger(__name__)

CONTEXT_DIR = Path(__file__).parent.parent / "context"
MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT_SPEC = """\
You are a principal software architect. Your single job is to produce a complete, \
unambiguous project specification that a team of junior developers could implement \
without ever asking a clarifying question.

Your output is ARCHITECT_SPEC.md — a markdown document with exactly these sections, \
in this order:

## 1. Project Overview
One paragraph. What it does, who uses it, the top-level success criterion.

## 2. Technology Stack
Table: Layer | Technology | Version | Rationale.
Include: language, framework, database, ORM/query builder, auth mechanism, \
testing library, linter/formatter, containerisation.

## 3. File and Module Layout
Complete file tree with one-line purpose comment per file.
Every file that will be created must appear here. No placeholders.

## 4. API Contracts
For each HTTP endpoint: method, path, request body (JSON schema inline), \
response body (JSON schema inline), status codes, auth requirement.
If the project has no HTTP API, write "N/A — not a web service."

## 5. Data Models
For each persistent entity: field name, type, constraints, relationships, indexes.
Use a table. Include primary keys, foreign keys, unique constraints.

## 6. Environment Variables
Table: Variable | Type | Required | Default | Description.
Every env var the application reads, including secrets.

## 7. Implementation Steps
Ordered numbered list. Each step is one file or one tightly-scoped concern.
Steps must be in topological order — no step may depend on a later step.
Each step: step number, target file, 2–3 sentence description of what to implement.

## 8. Open Questions
Any decision the Architect cannot resolve from the brief alone.
If none, write "None."

Rules:
- Output raw markdown only — no preamble, no apology, no commentary outside the sections.
- Never use the phrase "it depends" — make a concrete decision and note the rationale.
- Never leave a section empty. If not applicable, explain why briefly.
- Treat ambiguity as a decision opportunity, not a blocker.\
"""

SYSTEM_PROMPT_INTERFACES = """\
You are a principal software architect writing Python interface definitions.

Your output is INTERFACES.py — a single Python source file that defines ALL \
public contracts BEFORE any implementation exists. Downstream code generators \
will import from this file. It must be importable as-is.

Rules for INTERFACES.py:
1. Include: Protocol classes, Abstract Base Classes (ABC), Pydantic BaseModel \
   subclasses, TypedDicts, FastAPI route signatures as stub functions \
   (body = ...), SQLAlchemy/SQLModel table schemas.
2. Do NOT include: any business logic, any function bodies beyond `...` or \
   `raise NotImplementedError`, any import that is not part of the interface.
3. Group definitions with a comment header per domain area \
   (e.g. # --- Models ---, # --- Services ---, # --- Routes ---).
4. Every class and stub function must have a one-line docstring.
5. Every attribute must have a type annotation.
6. Use `from __future__ import annotations` as the first import.
7. Import only: stdlib typing, abc, pydantic, fastapi, sqlmodel/sqlalchemy — \
   nothing from the project being generated.

Return ONLY the raw Python source — no markdown fences, no explanations.\
"""

SYSTEM_PROMPT_SHARED_DEPS = """\
You are a principal software architect writing a cross-file coherence manifest.

Your output is shared_dependencies.md — the single source of truth for every \
contract that crosses a file boundary. Coder agents will receive this file on \
every invocation to avoid drift between files.

The file has exactly these sections with exactly these markdown headers \
(preserve them — downstream tooling matches on them):

# Shared Dependencies

## Shared Types & Models
Every Pydantic model, TypedDict, dataclass, and Protocol used in more than one file.
Format per entry:
**`ClassName`** (`source_module`)
Fields: field_name: type, ...

## Exported Function Signatures
Every function exported from one module and imported by another.
Format per entry:
**`function_name`** (`source_module`) → `return_type`
Args: param_name: type, ...

## API Contracts
Every HTTP endpoint. One subsection per endpoint.
Format: ### METHOD /path
Request: {json schema}
Response: {json schema}
Status codes: 200 OK / 422 Unprocessable / 401 Unauthorized / ...

## Data Schemas
Every database table or persistent data structure.
Format: table/collection name, engine, columns as a markdown table.

## Environment Variables
Every env var the application reads.
| Variable | Type | Required | Default | Description |

Always include the three pipeline env vars already present:
| `ANTHROPIC_API_KEY` | string | yes | — | Anthropic API key |
| `E2B_API_KEY` | string | yes | — | e2b sandbox execution |
| `GITHUB_PAT` | string | yes | — | GitHub PAT (repo scope) |

## File Registry
| File Path | Module | Exported Interface |
|---|---|---|
One row per file from the module layout. Exported Interface = the names \
(not signatures) of all public symbols this file will export.

Rules:
- Output raw markdown only.
- Be exhaustive — missing an entry here causes a Coder to write an incompatible \
  function signature in a different file.
- If a section is empty because the project has no web API, write "N/A" under \
  the header and explain in one sentence.\
"""

SYSTEM_PROMPT_TASK_QUEUE = """\
You are a build system planner. Your output is a JSON array — nothing else.

You will receive a project spec, interface definitions, and a shared dependencies \
manifest. From these you will produce a topologically sorted task queue: an ordered \
list where every file can be implemented using only files that appear earlier in \
the list.

Each entry in the array must have exactly these fields:
{
  "task_id":           string,   // "task_001", "task_002", ... zero-padded to 3 digits
  "target_file":       string,   // relative path within output/, e.g. "models/user.py"
  "description":       string,   // 3-5 sentences. What to implement, not how.
                                 // Include: which interfaces to satisfy,
                                 //          which data models to create,
                                 //          which endpoints to wire up.
                                 // Do NOT include: implementation details,
                                 //                 framework-specific boilerplate.
  "interface_refs":    [string], // Names of Protocol/ABC/TypedDict from INTERFACES.py
                                 // that this file must implement or satisfy.
  "dependency_paths":  [string]  // Relative paths (within output/) of files that must
                                 // exist before this file can be implemented.
                                 // Empty list [] for files with no code dependencies.
}

Topological ordering rules:
1. Configuration and constants files come first (no dependencies).
2. Data model files come before the services that use them.
3. Service/business logic files come before the API layer.
4. The entry point (main.py / app.py) comes last.
5. Test files are NOT included — the Test Writer generates those.

Critical constraints:
- Every file from the "File and Module Layout" section of ARCHITECT_SPEC.md must \
  appear exactly once, EXCEPT test files.
- dependency_paths must only reference files that appear earlier in the array.
- interface_refs must only reference names that appear in INTERFACES.py.
- Return ONLY the raw JSON array — no preamble, no markdown, no commentary.
  The first character of your response must be `[` and the last must be `]`.\
"""

_REQUIRED_TASK_KEYS = {
    "task_id",
    "target_file",
    "description",
    "interface_refs",
    "dependency_paths",
}


def _call_claude(system_prompt: str, user_prompt: str, max_tokens: int, thinking_budget: int = 0) -> str:
    """Call Claude with an ephemeral-cached system prompt and return raw text.

    When thinking_budget > 0, extended thinking is enabled. Thinking blocks
    appear before the text block in the response, so extraction searches for
    the first TextBlock rather than assuming content[0].

    Args:
        system_prompt: The system instruction, cached ephemerally.
        user_prompt: The user turn content.
        max_tokens: Maximum tokens for the response (must exceed thinking_budget).
        thinking_budget: Token budget for extended thinking; 0 disables it.

    Returns:
        Raw text content from the first TextBlock in the response.

    Raises:
        anthropic.APIError: If the API call fails.
        ValueError: If no TextBlock is found in the response.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    kwargs: dict = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": user_prompt}],
    }
    if thinking_budget > 0:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    try:
        response = client.messages.create(**kwargs)
    except anthropic.APIError as e:
        logger.error("Claude API call failed: %s", e)
        raise

    for block in response.content:
        if isinstance(block, anthropic.types.TextBlock):
            return block.text

    raise ValueError(f"No TextBlock found in response; block types: {[type(b).__name__ for b in response.content]}")


def _strip_markdown_fence(text: str, lang: str = "") -> str:
    """Remove a single leading/trailing markdown code fence if present.

    Args:
        text: Raw text that may be wrapped in a markdown fence.
        lang: Optional fence language tag to match (e.g. "python", "json").

    Returns:
        Text with fence stripped, or unchanged text if no fence found.
    """
    pattern = rf"^\s*```{re.escape(lang)}\s*\n(.*?)\n\s*```\s*$"
    match = re.match(pattern, text.strip(), re.DOTALL)
    if match:
        return match.group(1)
    return text


def _parse_task_queue_json(raw_json: str) -> list[TaskEntry]:
    """Parse and validate the task queue JSON from the Architect's fourth call.

    Args:
        raw_json: JSON string expected to be a list of task objects.

    Returns:
        List of TaskEntry TypedDicts in topological order.

    Raises:
        json.JSONDecodeError: If the text is not valid JSON.
        ValueError: If required keys are missing or types are wrong.
    """
    parsed = json.loads(raw_json)
    if not isinstance(parsed, list):
        raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")

    for i, entry in enumerate(parsed):
        missing = _REQUIRED_TASK_KEYS - entry.keys()
        if missing:
            raise ValueError(f"task_queue[{i}] missing keys: {missing}")
        if not isinstance(entry["interface_refs"], list):
            raise ValueError(f"task_queue[{i}].interface_refs must be a list")
        if not isinstance(entry["dependency_paths"], list):
            raise ValueError(f"task_queue[{i}].dependency_paths must be a list")

    return [TaskEntry(**entry) for entry in parsed]


def run_architect(clarified_brief: str, conventions: str) -> dict:
    """Run the two-pass Architect pipeline and write four artifacts to /context/.

    Pass 1 generates ARCHITECT_SPEC.md and INTERFACES.py in sequence.
    Pass 2 reads both Pass 1 outputs from disk and uses them to generate
    shared_dependencies.md and task_queue.json. Re-reading from disk (rather
    than passing in-memory strings) catches encoding issues early and ensures
    Pass 2 is grounded in exactly what was committed.

    Args:
        clarified_brief: The project brief after Spec Clarifier processing.
        conventions: Content of CONVENTIONS.md, injected into every call.

    Returns:
        Dict with keys:
            architect_spec_path (str): Absolute path to ARCHITECT_SPEC.md.
            interfaces_path (str): Absolute path to INTERFACES.py.
            shared_deps_path (str): Absolute path to shared_dependencies.md.
            task_queue_path (str): Absolute path to task_queue.json.
            task_queue (list[TaskEntry]): Parsed task entries for LangGraph state.

    Raises:
        anthropic.APIError: If any Claude API call fails.
        json.JSONDecodeError: If the task_queue.json response is malformed.
        ValueError: If parsed outputs fail validation.
    """
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Pass 1, Call 1: ARCHITECT_SPEC.md ──────────────────────────────────
    logger.info("Architect Pass 1 — generating ARCHITECT_SPEC.md")

    spec_user_prompt = (
        f"## Project Conventions\n\n{conventions}\n\n"
        f"## Clarified Project Brief\n\n{clarified_brief}\n\n"
        "Produce ARCHITECT_SPEC.md now."
    )
    spec_text = _call_claude(SYSTEM_PROMPT_SPEC, spec_user_prompt, max_tokens=8192, thinking_budget=5000)
    spec_path = CONTEXT_DIR / "ARCHITECT_SPEC.md"
    spec_path.write_text(spec_text, encoding="utf-8")
    logger.info("Architect wrote ARCHITECT_SPEC.md (%d chars)", len(spec_text))

    # ── Pass 1, Call 2: INTERFACES.py ──────────────────────────────────────
    logger.info("Architect Pass 1 — generating INTERFACES.py")

    interfaces_user_prompt = (
        f"## Project Conventions\n\n{conventions}\n\n"
        f"## ARCHITECT_SPEC.md\n\n{spec_text}\n\n"
        "Produce INTERFACES.py now. Remember: interfaces only, no implementations."
    )
    interfaces_text = _call_claude(
        SYSTEM_PROMPT_INTERFACES, interfaces_user_prompt, max_tokens=4096, thinking_budget=2000
    )
    interfaces_text = _strip_markdown_fence(interfaces_text, "python")
    interfaces_path = CONTEXT_DIR / "INTERFACES.py"
    interfaces_path.write_text(interfaces_text, encoding="utf-8")
    logger.info("Architect wrote INTERFACES.py (%d chars)", len(interfaces_text))

    # ── Pass 2: Re-read from disk to ground context ─────────────────────────
    logger.info("Architect Pass 2 — reading Pass 1 artifacts from disk")
    architect_spec_content = spec_path.read_text(encoding="utf-8")
    interfaces_content = interfaces_path.read_text(encoding="utf-8")

    # ── Pass 2, Call 3: shared_dependencies.md ─────────────────────────────
    logger.info("Architect Pass 2 — generating shared_dependencies.md")

    shared_deps_user_prompt = (
        f"## Project Conventions\n\n{conventions}\n\n"
        f"## ARCHITECT_SPEC.md\n\n{architect_spec_content}\n\n"
        f"## INTERFACES.py\n\n{interfaces_content}\n\n"
        "Produce shared_dependencies.md now. The existing template has placeholder text — "
        "replace it entirely with concrete content derived from the spec and interfaces above."
    )
    shared_deps_text = _call_claude(
        SYSTEM_PROMPT_SHARED_DEPS, shared_deps_user_prompt, max_tokens=6144, thinking_budget=3500
    )
    shared_deps_path = CONTEXT_DIR / "shared_dependencies.md"
    shared_deps_path.write_text(shared_deps_text, encoding="utf-8")
    logger.info(
        "Architect wrote shared_dependencies.md (%d chars)", len(shared_deps_text)
    )

    # ── Pass 2, Call 4: task_queue.json ────────────────────────────────────
    logger.info("Architect Pass 2 — generating task_queue.json")

    shared_deps_content = shared_deps_path.read_text(encoding="utf-8")
    task_queue_user_prompt = (
        f"## ARCHITECT_SPEC.md\n\n{architect_spec_content}\n\n"
        f"## INTERFACES.py\n\n{interfaces_content}\n\n"
        f"## shared_dependencies.md\n\n{shared_deps_content}\n\n"
        "Produce the task_queue JSON array now. "
        "Remember: topological order, raw JSON only, first char `[`, last char `]`."
    )
    task_queue_raw = _call_claude(
        SYSTEM_PROMPT_TASK_QUEUE, task_queue_user_prompt, max_tokens=4096
    )

    try:
        task_queue: list[TaskEntry] = _parse_task_queue_json(task_queue_raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(
            "task_queue parse failed: %s\nRaw output (first 500 chars): %s",
            e,
            task_queue_raw[:500],
        )
        raise

    task_queue_path = CONTEXT_DIR / "task_queue.json"
    task_queue_path.write_text(json.dumps(task_queue, indent=2), encoding="utf-8")
    logger.info("Architect wrote task_queue.json (%d tasks)", len(task_queue))

    return {
        "architect_spec_path": str(spec_path),
        "interfaces_path": str(interfaces_path),
        "shared_deps_path": str(shared_deps_path),
        "task_queue_path": str(task_queue_path),
        "task_queue": task_queue,
    }


if __name__ == "__main__":
    conventions_path = Path(__file__).parent.parent / "context" / "CONVENTIONS.md"
    conventions_content = conventions_path.read_text(encoding="utf-8")

    sample_brief = (
        "Build a FastAPI REST API for a simple task manager. "
        "Users can create, list, update, and delete tasks. "
        "Each task has a title, description, status (todo/in_progress/done), "
        "and an owner. Use SQLite with SQLModel. Auth via JWT bearer tokens. "
        "Include an async background job that marks overdue tasks as expired."
    )

    result = run_architect(sample_brief, conventions_content)
    for key, value in result.items():
        if key != "task_queue":
            print(f"{key}: {value}")
    print(f"task_queue: {len(result['task_queue'])} tasks")
    for task in result["task_queue"]:
        print(f"  {task['task_id']}: {task['target_file']}")
