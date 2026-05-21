from __future__ import annotations

import json
import re
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from scripts.instrumentation import instrumented_call
from scripts.logger import get_logger
from state.schema import TaskEntry

logger = get_logger(__name__)

MODEL = "claude-sonnet-4-20250514"
MODEL_HAIKU = "claude-haiku-4-5-20251001"

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


def _call_claude(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    thinking_budget: int = 0,
    *,
    phase: str,
    run_dir: str | None,
    model: str = MODEL,
) -> str:
    """Call Claude with an ephemeral-cached system prompt and return raw text.

    When thinking_budget > 0, extended thinking is enabled. Thinking blocks
    appear before the text block in the response, so extraction searches for
    the first TextBlock rather than assuming content[0].

    Args:
        system_prompt: The system instruction, cached ephemerally.
        user_prompt: The user turn content.
        max_tokens: Maximum tokens for the response (must exceed thinking_budget).
        thinking_budget: Token budget for extended thinking; 0 disables it.
        phase: Label routed through ``instrumented_call`` so the JSONL ledger
            distinguishes the four Architect passes from one another.
        run_dir: Run workspace root; metrics are appended under it. ``None``
            disables disk persistence (used by stand-alone smoke runs).
        model: Override the model id. Defaults to ``MODEL`` (Sonnet) but the
            evaluate path passes Haiku to keep critic cost down.

    Returns:
        Raw text content from the first TextBlock in the response.

    Raises:
        anthropic.APIError: If the API call fails.
        ValueError: If no TextBlock is found in the response.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    kwargs: dict = {
        "model": model,
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
        response = instrumented_call(
            client, agent="architect", phase=phase, run_dir=run_dir, **kwargs
        )
    except anthropic.APIError as e:
        logger.error("Claude API call failed: %s", e)
        raise

    for block in response.content:
        if isinstance(block, anthropic.types.TextBlock):
            return block.text

    raise ValueError(
        f"No TextBlock found in response; block types: {[type(b).__name__ for b in response.content]}"
    )


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


def run_architect(clarified_brief: str, conventions: str, run_dir: str) -> dict:
    """Run the two-pass Architect pipeline and write four artifacts to run_dir/context/.

    Pass 1 generates ARCHITECT_SPEC.md and INTERFACES.py in sequence.
    Pass 2 reads both Pass 1 outputs from disk and uses them to generate
    shared_dependencies.md and task_queue.json. Re-reading from disk (rather
    than passing in-memory strings) catches encoding issues early and ensures
    Pass 2 is grounded in exactly what was committed.

    Args:
        clarified_brief: The project brief after Spec Clarifier processing.
        conventions: Content of CONVENTIONS.md, injected into every call.
        run_dir: Absolute path to the run workspace created by workspace_node.

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
    context_dir = Path(run_dir) / "context"

    # ── Pass 1, Call 1: ARCHITECT_SPEC.md ──────────────────────────────────
    logger.info("Architect Pass 1 — generating ARCHITECT_SPEC.md")

    spec_user_prompt = (
        f"## Project Conventions\n\n{conventions}\n\n"
        f"## Clarified Project Brief\n\n{clarified_brief}\n\n"
        "Produce ARCHITECT_SPEC.md now."
    )
    spec_text = _call_claude(
        SYSTEM_PROMPT_SPEC,
        spec_user_prompt,
        max_tokens=8192,
        thinking_budget=5000,
        phase="spec_generation",
        run_dir=run_dir,
    )
    spec_path = context_dir / "ARCHITECT_SPEC.md"
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
        SYSTEM_PROMPT_INTERFACES,
        interfaces_user_prompt,
        max_tokens=4096,
        thinking_budget=2000,
        phase="interfaces_generation",
        run_dir=run_dir,
    )
    interfaces_text = _strip_markdown_fence(interfaces_text, "python")
    interfaces_path = context_dir / "INTERFACES.py"
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
        SYSTEM_PROMPT_SHARED_DEPS,
        shared_deps_user_prompt,
        max_tokens=6144,
        thinking_budget=3500,
        phase="shared_deps_generation",
        run_dir=run_dir,
    )
    shared_deps_path = context_dir / "shared_dependencies.md"
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
        SYSTEM_PROMPT_TASK_QUEUE,
        task_queue_user_prompt,
        max_tokens=16384,
        phase="task_queue_generation",
        run_dir=run_dir,
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

    task_queue_path = context_dir / "task_queue.json"
    task_queue_path.write_text(json.dumps(task_queue, indent=2), encoding="utf-8")
    logger.info("Architect wrote task_queue.json (%d tasks)", len(task_queue))

    return {
        "architect_spec_path": str(spec_path),
        "interfaces_path": str(interfaces_path),
        "shared_deps_path": str(shared_deps_path),
        "task_queue_path": str(task_queue_path),
        "task_queue": task_queue,
    }


SYSTEM_PROMPT_EVALUATE = """\
You are a strict code review oracle. You receive a task specification excerpt, \
the expected interface contract from shared_dependencies.md, and the public \
interface signature that was actually extracted from the generated file.

PASS if ALL of the following are true:
- Every public symbol required by the task description and shared_dependencies.md \
  is declared in the extracted interface.
- Function and method signatures match the expected types (parameter names, type \
  annotations, return type).
- No required symbol is missing or renamed.

FAIL if ANY of the following are true:
- A required function, class, or constant is absent.
- A type annotation does not match the contract (e.g. returns str instead of int).
- The interface is empty and the task was not a stub.

Respond with EXACTLY two lines — no preamble, no explanation, no markdown:
Line 1: PASS  OR  FAIL
Line 2: One sentence reason (25 words max). If PASS, write "Interface satisfies all contracts."\
"""

SYSTEM_PROMPT_REDECOMPOSE = """\
You are a principal software architect performing emergency task decomposition.

A single coding task has failed validation 3 times in a row. You must split it \
into exactly 2 smaller, independently-implementable subtasks that together \
accomplish everything the original task required.

Rules:
- Each subtask must have a unique target_file.
- If the original task produces one file, the natural split is: \
  (1) data models / pure logic, (2) integration / I/O layer.
- Each subtask description must be self-contained (3-4 sentences). Do NOT \
  reference the other subtask by name — the Coder cannot see sibling tasks.
- dependency_paths in subtask 2 should include the target_file of subtask 1 if \
  subtask 2 depends on it.
- interface_refs must only list names that exist in the original task's interface_refs.
- Preserve the original task_id prefix with letter suffixes: \
  if original was "task_005", produce "task_005a" and "task_005b".

Return ONLY a raw JSON array of exactly 2 objects. First char `[`, last char `]`.
Each object has exactly these keys: task_id, target_file, description, \
interface_refs, dependency_paths.\
"""


def run_architect_evaluate(
    task: TaskEntry,
    interface_signature: str,
    spec_path: str,
    shared_deps_path: str,
    run_dir: str | None = None,
) -> tuple[bool, str]:
    """Evaluate whether a generated file's interface satisfies its task contract.

    Uses Haiku for cost efficiency. Checks extracted public interface against the
    task description and shared_dependencies.md contracts. Does not re-read full
    source code — operates on compact signatures only.

    Args:
        task: The TaskEntry that was just executed by the Coder.
        interface_signature: Extracted public interface returned by run_coder_task.
        spec_path: Absolute path to architect_spec.md on disk (reserved for future use).
        shared_deps_path: Absolute path to shared_dependencies.md on disk.
        run_dir: Run workspace root for instrumentation. ``None`` disables
            metric persistence (used by stand-alone smoke runs).

    Returns:
        Tuple of (passed, correction_notes). passed is True if the interface
        satisfies the contract. correction_notes is empty when passed is True.

    Raises:
        anthropic.APIError: If the Haiku API call fails.
        OSError: If shared_deps_path cannot be read.
    """
    shared_deps_content = Path(shared_deps_path).read_text(encoding="utf-8")

    user_prompt = (
        f"## Task Description\n\n{task['description']}\n\n"
        f"## Expected Interface (from shared_dependencies.md)\n\n"
        f"{shared_deps_content}\n\n"
        f"## Extracted Interface Signature (from generated file)\n\n"
        f"File: {task['target_file']}\n\n"
        f"{interface_signature}\n\n"
        "Evaluate whether the extracted interface satisfies the contracts above."
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        response = instrumented_call(
            client,
            agent="architect_evaluate",
            phase="evaluate",
            run_dir=run_dir,
            model=MODEL_HAIKU,
            max_tokens=128,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT_EVALUATE,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIError as exc:
        logger.error(
            "run_architect_evaluate: Haiku API call failed for %s: %s",
            task["target_file"],
            exc,
        )
        raise

    raw_text = ""
    for block in response.content:
        if isinstance(block, anthropic.types.TextBlock):
            raw_text = block.text.strip()
            break

    lines = raw_text.splitlines()
    verdict = lines[0].strip().upper() if lines else "FAIL"
    reason = lines[1].strip() if len(lines) > 1 else "Evaluation response malformed."

    passed = verdict == "PASS"
    correction_notes = "" if passed else reason

    logger.info(
        "run_architect_evaluate: %s → %s | %s",
        task["target_file"],
        verdict,
        reason,
    )
    return passed, correction_notes


def run_architect_redecompose(
    failing_task: TaskEntry,
    spec_path: str,
    shared_deps_path: str,
    run_dir: str | None = None,
) -> list[TaskEntry]:
    """Re-decompose a repeatedly-failing task into 2 smaller subtasks.

    Called when task_failure_count reaches 3. Uses Sonnet for the structural
    reasoning required to split a task while preserving interface contracts.
    Writes nothing to disk — the caller splices the returned entries into state.

    Args:
        failing_task: The TaskEntry that has exceeded the failure threshold.
        spec_path: Absolute path to architect_spec.md on disk.
        shared_deps_path: Absolute path to shared_dependencies.md on disk.

    Returns:
        List of exactly 2 TaskEntry objects with task_ids suffixed "a" and "b".

    Raises:
        anthropic.APIError: If the Sonnet API call fails.
        json.JSONDecodeError: If the response is not valid JSON.
        ValueError: If the response does not contain exactly 2 valid TaskEntry objects.
        OSError: If spec_path or shared_deps_path cannot be read.
    """
    spec_content = Path(spec_path).read_text(encoding="utf-8")
    shared_deps_content = Path(shared_deps_path).read_text(encoding="utf-8")

    user_prompt = (
        f"## Failing Task\n\n"
        f"task_id: {failing_task['task_id']}\n"
        f"target_file: {failing_task['target_file']}\n"
        f"description: {failing_task['description']}\n"
        f"interface_refs: {failing_task['interface_refs']}\n"
        f"dependency_paths: {failing_task['dependency_paths']}\n\n"
        f"## ARCHITECT_SPEC.md\n\n{spec_content}\n\n"
        f"## shared_dependencies.md\n\n{shared_deps_content}\n\n"
        "Split the failing task into exactly 2 smaller subtasks. "
        "Return ONLY the raw JSON array."
    )

    raw_json = _call_claude(
        SYSTEM_PROMPT_REDECOMPOSE,
        user_prompt,
        max_tokens=1024,
        phase="redecompose",
        run_dir=run_dir,
    )
    cleaned = _strip_markdown_fence(raw_json, "json")

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error(
            "run_architect_redecompose: JSON parse failed for %s: %s\nRaw: %s",
            failing_task["task_id"],
            exc,
            cleaned[:400],
        )
        raise

    if not isinstance(parsed, list) or len(parsed) != 2:
        raise ValueError(
            f"run_architect_redecompose: expected list of 2, got "
            f"{type(parsed).__name__} length "
            f"{len(parsed) if isinstance(parsed, list) else 'N/A'}"
        )

    subtasks: list[TaskEntry] = []
    for i, entry in enumerate(parsed):
        missing = _REQUIRED_TASK_KEYS - entry.keys()
        if missing:
            raise ValueError(
                f"run_architect_redecompose: subtask[{i}] missing keys: {missing}"
            )
        subtasks.append(TaskEntry(**entry))

    logger.info(
        "run_architect_redecompose: split %s → [%s, %s]",
        failing_task["task_id"],
        subtasks[0]["task_id"],
        subtasks[1]["task_id"],
    )
    return subtasks


SYSTEM_PROMPT_REVISION = """\
You are a principal software architect performing a targeted revision pass.

A synthesis report has identified blocking issues in a generated codebase. \
Your job is to produce the smallest possible set of coding tasks that will \
resolve every blocking issue — without re-implementing files that are not implicated.

Rules:
- Only create tasks for files explicitly mentioned under "High Priority Fixes".
- Each task description must begin with "Fix: " and describe the specific problem \
  to resolve. Include 2-3 sentences on exactly what to change.
- Set dependency_paths to a list containing the absolute disk path of the file \
  being revised, so the Coder reads the existing implementation before overwriting it.
- Do NOT invent new files. Every target_file must appear in the provided file registry.
- Assign task_ids with a "rev{N}_" prefix where N is the revision number, \
  e.g. "rev1_task_001".
- interface_refs may be [] if the interface contract is unchanged.
- Return ONLY a raw JSON array. First char `[`, last char `]`.

Each entry must have exactly these keys:
{
  "task_id":          string,
  "target_file":      string,
  "description":      string,
  "interface_refs":   [string],
  "dependency_paths": [string]
}\
"""


def run_architect_revision(
    synthesis_report_path: str,
    architect_spec_path: str,
    shared_deps_path: str,
    generated_file_paths: list[str],
    revision_number: int,
    run_dir: str | None = None,
) -> list[TaskEntry]:
    """Produce targeted revision tasks from a synthesis report.

    Reads SYNTHESIS_REPORT.md and the stable context files, then asks Claude
    to create the smallest possible set of TaskEntry objects covering only the
    files implicated by blocking issues. Does not re-queue files that passed.

    Args:
        synthesis_report_path: Absolute path to SYNTHESIS_REPORT.md on disk.
        architect_spec_path: Absolute path to ARCHITECT_SPEC.md on disk.
        shared_deps_path: Absolute path to shared_dependencies.md on disk.
        generated_file_paths: Absolute paths of all files written so far.
        revision_number: Current revision cycle number (1 or 2).

    Returns:
        List of TaskEntry objects for the targeted revision. May be empty if
        the model finds no actionable tasks after filtering hallucinated files.

    Raises:
        anthropic.APIError: If the Claude API call fails.
        json.JSONDecodeError: If the response is not valid JSON.
        ValueError: If the response fails task key validation.
        OSError: If synthesis_report_path cannot be read.
    """
    synthesis_content = Path(synthesis_report_path).read_text(encoding="utf-8")

    spec_content = ""
    if architect_spec_path:
        try:
            spec_content = Path(architect_spec_path).read_text(encoding="utf-8")
        except OSError:
            logger.warning(
                "run_architect_revision: could not read spec at %s", architect_spec_path
            )

    shared_deps_content = ""
    try:
        shared_deps_content = Path(shared_deps_path).read_text(encoding="utf-8")
    except OSError:
        logger.warning(
            "run_architect_revision: could not read shared_deps at %s", shared_deps_path
        )

    # Build registry of relative names so the model knows what files exist.
    registry_lines = [Path(p).name for p in generated_file_paths]
    file_registry = "\n".join(registry_lines) if registry_lines else "(none)"

    user_prompt = (
        f"## Synthesis Report (Revision {revision_number})\n\n"
        f"{synthesis_content}\n\n"
        f"## Architect Spec (for context)\n\n"
        f"{spec_content}\n\n"
        f"## Shared Dependencies (for context)\n\n"
        f"{shared_deps_content}\n\n"
        f"## Generated File Registry (ONLY these files may be assigned tasks)\n\n"
        f"{file_registry}\n\n"
        "Produce revision tasks now. Return ONLY the raw JSON array."
    )

    raw_json = _call_claude(
        SYSTEM_PROMPT_REVISION,
        user_prompt,
        max_tokens=2048,
        phase=f"revision_{revision_number}",
        run_dir=run_dir,
    )
    cleaned = _strip_markdown_fence(raw_json, "json")

    try:
        tasks = _parse_task_queue_json(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error(
            "run_architect_revision: parse failed for revision %d: %s\nRaw: %s",
            revision_number,
            exc,
            cleaned[:400],
        )
        raise

    # Filter tasks referencing files that don't exist to guard against hallucination.
    known_names = {Path(p).name for p in generated_file_paths}
    filtered: list[TaskEntry] = []
    for task in tasks:
        target_name = Path(task["target_file"]).name
        if target_name in known_names:
            filtered.append(task)
        else:
            logger.warning(
                "run_architect_revision: dropping task %s — target_file %r not in registry",
                task["task_id"],
                task["target_file"],
            )

    logger.info(
        "run_architect_revision: produced %d revision tasks for revision %d",
        len(filtered),
        revision_number,
    )
    return filtered


