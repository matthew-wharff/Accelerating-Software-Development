"""LangGraph pipeline definition — MVP architecture proof.

Wires two nodes in a linear graph: coder_node → critic_node.
Each node calls its agent, writes output to /output/, and returns
only file paths in state — never file contents.

Usage:
    python graph/pipeline.py        # runs hardcoded smoke test
    from graph.pipeline import app  # import compiled graph
"""

from __future__ import annotations

import time
from pathlib import Path

import anthropic
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

import re
from typing import Any

from agents.architect import (
    run_architect,
    run_architect_evaluate,
    run_architect_redecompose,
    run_architect_revision,
)
from agents.code_quality import run_code_quality
from agents.coder import run_coder_task
from agents.devops import run_devops
from agents.github_agent import run_github
from agents.security_reviewer import run_security_reviewer
from agents.spec_clarifier import run_spec_clarifier
from agents.synthesis import run_synthesis
from agents.test_writer import run_test_writer
from scripts.instrumentation import metrics_path_for, write_summary
from scripts.logger import get_logger
from scripts.workspace import create_run_workspace
import config
from state.schema import (
    E2bOutput,
    PipelineState,
    TaskEntry,
    TaskLogEntry,
)

CONVENTIONS_PATH = Path(__file__).parent.parent / "context" / "CONVENTIONS.md"

logger = get_logger(__name__)


def read_synthesis_report(path: str) -> dict:
    """Read SYNTHESIS_REPORT.md from disk and extract structured fields.

    Parses the ``has_blocking_issues:`` sentinel line written by the Synthesis
    agent. Returns a dict so the router can call this without touching state.
    Fails safe (returns False) on missing file or missing sentinel to avoid
    triggering unnecessary revisions.

    Args:
        path: Absolute path to SYNTHESIS_REPORT.md on disk.

    Returns:
        Dict with key ``has_blocking_issues`` (bool).
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        logger.warning(
            "read_synthesis_report: file not found at %s — defaulting to no blocking issues",
            path,
        )
        return {"has_blocking_issues": False}

    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("has_blocking_issues:"):
            value = stripped.split(":", 1)[1].strip()
            return {"has_blocking_issues": value == "true"}

    logger.warning(
        "read_synthesis_report: sentinel line not found in %s — defaulting to False",
        path,
    )
    return {"has_blocking_issues": False}


def _project_name_slug(brief: str) -> str:
    """Derive a safe directory name from the project brief.

    Args:
        brief: The plain-English project description from state.

    Returns:
        A lowercase, underscore-separated string of at most 40 characters,
        defaulting to ``"project"`` if ``brief`` is blank.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", brief.lower().strip()).strip("_")
    return slug[:40] or "project"


def coder_node(state: PipelineState) -> dict:
    """Execute the Coder agent for the current task in the queue.

    Reads the task at ``state["current_task_index"]``, delegates to
    ``run_coder``, and returns updated state fields containing only the
    new file path — never the generated source code itself.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict updating ``generated_file_paths``, ``task_log``,
        and ``current_task_index`` on success; ``{"status": "failed"}`` on
        any error.
    """
    task_queue = state["task_queue"]
    current_index = state["current_task_index"]

    if current_index >= len(task_queue):
        logger.error(
            "coder_node: current_task_index %d is out of bounds (queue length %d)",
            current_index,
            len(task_queue),
        )
        return {"status": "failed"}

    task: TaskEntry = task_queue[current_index]
    logger.info(
        "coder_node: starting task %s (%s)", task["task_id"], task["target_file"]
    )

    interface_refs = task.get("interface_refs", [])
    dependency_paths = task.get("dependency_paths", [])

    coder_task = {
        "task_id": task["task_id"],
        "target_file": task["target_file"],
        "description": task["description"],
        "interface_refs": interface_refs,
        "dependency_paths": dependency_paths,
    }

    correction = state.get("task_correction_instructions")
    if correction:
        coder_task["description"] = (
            coder_task["description"]
            + f"\n\n## Correction Instructions from Architect\n\n{correction}"
        )
        logger.info("coder_node: applying correction for task %s", task["task_id"])

    # Build relevant_interfaces: pass full INTERFACES.py when refs exist.
    # TODO: filter to only the named symbols from interface_refs (optimization).
    relevant_interfaces = ""
    interfaces_path = state.get("interfaces_path") or ""
    if interface_refs and interfaces_path and Path(interfaces_path).exists():
        relevant_interfaces = Path(interfaces_path).read_text(encoding="utf-8")

    # Build prior_signatures from completed task log entries this task depends on.
    prior_sig_parts: list[str] = []
    task_log = state.get("task_log", [])
    for dep_path in dependency_paths:
        for entry in task_log:
            if entry["file_path"].endswith(dep_path) and entry.get(
                "interface_signature"
            ):
                prior_sig_parts.append(f"# {dep_path}\n{entry['interface_signature']}")
                break
    prior_signatures = "\n\n".join(prior_sig_parts)

    try:
        conventions = CONVENTIONS_PATH.read_text(encoding="utf-8")
        shared_deps_path = state["shared_deps_path"]
        shared_deps = Path(shared_deps_path).read_text(encoding="utf-8")
        file_path, extracted_interface = run_coder_task(
            task=coder_task,
            shared_deps=shared_deps,
            shared_deps_path=shared_deps_path,
            relevant_interfaces=relevant_interfaces,
            prior_signatures=prior_signatures,
            conventions=conventions,
            run_dir=Path(state["run_dir"]),
        )
    except KeyError as exc:
        logger.error("coder_node: missing required task key: %s", exc)
        return {"status": "failed"}
    except anthropic.APIError as exc:
        logger.error(
            "coder_node: Claude API error for %s: %s", task["target_file"], exc
        )
        return {"status": "failed"}
    except (ValueError, OSError) as exc:
        logger.error(
            "coder_node: file_writer error for %s: %s", task["target_file"], exc
        )
        return {"status": "failed"}

    log_entry: TaskLogEntry = {
        "task_id": task["task_id"],
        "task_name": f"Implement {task['target_file']}",
        "status": "pending_evaluation",
        "file_path": file_path,
        "interface_signature": extracted_interface,
    }

    logger.info("coder_node: wrote %s", file_path)

    return {
        "generated_file_paths": state["generated_file_paths"] + [file_path],
        "task_log": state["task_log"] + [log_entry],
    }


def dispatch_critics(state: PipelineState) -> list[Send]:
    """Fan out to all three critic agents in parallel via Send API.

    Each Send delivers an isolated scoped state to its target node,
    preventing context bleed between critics.

    Args:
        state: The current pipeline state.

    Returns:
        List of Send objects routing to each critic node in parallel.
    """
    run_dir = state["run_dir"]
    shared_deps_path = state["shared_deps_path"]
    interfaces_path = state.get("interfaces_path") or ""
    conventions = CONVENTIONS_PATH.read_text(encoding="utf-8")
    generated_file_paths = state["generated_file_paths"]

    logger.info(
        "dispatch_critics: fanning out to 3 critics for %d files",
        len(generated_file_paths),
    )

    return [
        Send(
            "devops_node",
            {
                "architect_spec_path": state.get("architect_spec_path") or "",
                "shared_deps_path": shared_deps_path,
                "run_dir": run_dir,
            },
        ),
        Send(
            "test_writer_node",
            {
                "generated_file_paths": generated_file_paths,
                "interfaces_path": interfaces_path,
                "shared_deps_path": shared_deps_path,
                "run_dir": run_dir,
                "e2b_output": state.get("e2b_output"),
            },
        ),
        Send(
            "security_reviewer_node",
            {
                "generated_file_paths": generated_file_paths,
                "shared_deps_path": shared_deps_path,
                "run_dir": run_dir,
                "e2b_output": state.get("e2b_output"),
            },
        ),
        Send(
            "quality_reviewer_node",
            {
                "generated_file_paths": generated_file_paths,
                "conventions": conventions,
                "run_dir": run_dir,
                "e2b_output": state.get("e2b_output"),
            },
        ),
    ]


def test_writer_node(state: Any) -> dict:
    """Run the Test Writer critic against all generated files.

    Args:
        state: Scoped dict from Send — contains generated_file_paths,
            interfaces_path, shared_deps_path, run_dir.

    Returns:
        Partial state dict updating ``test_feedback_path``.
    """
    t0 = time.perf_counter()
    logger.info("test_writer_node: starting")
    try:
        written_paths = run_test_writer(
            generated_file_paths=state["generated_file_paths"],
            interfaces_path=state["interfaces_path"],
            shared_deps_path=state["shared_deps_path"],
            run_dir=state["run_dir"],
            e2b_output=state.get("e2b_output"),
        )
    except Exception as exc:
        logger.error("test_writer_node: failed: %s", exc)
        return {"test_feedback_path": None}
    summary_path = next(
        (p for p in written_paths if "TEST_SUMMARY" in p),
        written_paths[-1] if written_paths else None,
    )
    logger.info(
        "test_writer_node: done in %.2fs — %s", time.perf_counter() - t0, summary_path
    )
    return {"test_feedback_path": summary_path}


def security_reviewer_node(state: Any) -> dict:
    """Run the Security Reviewer critic against all generated files.

    Args:
        state: Scoped dict from Send — contains generated_file_paths,
            shared_deps_path, run_dir.

    Returns:
        Partial state dict updating ``security_feedback_path``.
    """
    t0 = time.perf_counter()
    logger.info("security_reviewer_node: starting")
    try:
        report_path = run_security_reviewer(
            generated_file_paths=state["generated_file_paths"],
            shared_deps_path=state["shared_deps_path"],
            run_dir=state["run_dir"],
            e2b_output=state.get("e2b_output"),
        )
    except Exception as exc:
        logger.error("security_reviewer_node: failed: %s", exc)
        return {"security_feedback_path": None}
    logger.info(
        "security_reviewer_node: done in %.2fs — %s",
        time.perf_counter() - t0,
        report_path,
    )
    return {"security_feedback_path": report_path}


def quality_reviewer_node(state: Any) -> dict:
    """Run the Code Quality critic against all generated files.

    Args:
        state: Scoped dict from Send — contains generated_file_paths,
            conventions, run_dir.

    Returns:
        Partial state dict updating ``quality_feedback_path``.
    """
    t0 = time.perf_counter()
    logger.info("quality_reviewer_node: starting")
    try:
        report_path = run_code_quality(
            generated_file_paths=state["generated_file_paths"],
            conventions=state["conventions"],
            run_dir=state["run_dir"],
            e2b_output=state.get("e2b_output"),
        )
    except Exception as exc:
        logger.error("quality_reviewer_node: failed: %s", exc)
        return {"quality_feedback_path": None}
    logger.info(
        "quality_reviewer_node: done in %.2fs — %s",
        time.perf_counter() - t0,
        report_path,
    )
    return {"quality_feedback_path": report_path}


def devops_node(state: Any) -> dict:
    """Run the DevOps agent to generate infrastructure files.

    Args:
        state: Scoped dict from Send — contains architect_spec_path,
            shared_deps_path, run_dir.

    Returns:
        Partial state dict updating ``devops_config_paths``.
    """
    t0 = time.perf_counter()
    logger.info("devops_node: starting")
    try:
        written_paths = run_devops(
            architect_spec_path=state.get("architect_spec_path") or "",
            shared_deps_path=state["shared_deps_path"],
            run_dir=state["run_dir"],
        )
    except Exception as exc:
        logger.error("devops_node: failed: %s", exc)
        return {"devops_config_paths": []}
    logger.info(
        "devops_node: done in %.2fs — %d files written",
        time.perf_counter() - t0,
        len(written_paths),
    )
    return {"devops_config_paths": written_paths}


def architect_dispatch_node(state: PipelineState) -> dict:
    """Evaluate the last Coder result and prepare the next task dispatch.

    On first entry (task_log empty) the evaluation step is skipped and the node
    simply signals readiness for the first Coder dispatch.

    Evaluation outcomes:
    - PASS: advances current_task_index, resets failure counter, clears corrections.
    - FAIL (failure_count < 3): increments failure counter, sets correction instructions.
    - FAIL (failure_count reaches 3): calls run_architect_redecompose to split the
      failing task into 2 subtasks, splices them into task_queue at current_index,
      resets failure counter. Gracefully degrades on redecompose errors.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict. Never raises — evaluation errors are treated as FAIL.
    """
    task_queue = state["task_queue"]
    task_log = state["task_log"]
    current_index = state["current_task_index"]
    failure_count = state["task_failure_count"]

    if not task_log:
        logger.info("architect_dispatch_node: first run — skipping evaluation")
        return {"task_correction_instructions": None}

    current_task: TaskEntry = task_queue[current_index]
    last_entry = task_log[-1]

    try:
        passed, correction_notes = run_architect_evaluate(
            task=current_task,
            interface_signature=last_entry["interface_signature"],
            spec_path=state.get("architect_spec_path") or "",
            shared_deps_path=state["shared_deps_path"],
            run_dir=state.get("run_dir") or None,
        )
    except Exception as exc:
        logger.error(
            "architect_dispatch_node: evaluate raised %s — treating as FAIL: %s",
            type(exc).__name__,
            exc,
        )
        passed = False
        correction_notes = (
            "Evaluation call failed; please re-implement the file from scratch."
        )

    if passed:
        logger.info(
            "architect_dispatch_node: task %s PASSED — advancing to index %d",
            current_task["task_id"],
            current_index + 1,
        )
        updated_log = list(task_log)
        updated_log[-1] = {**last_entry, "status": "complete"}
        return {
            "current_task_index": current_index + 1,
            "task_failure_count": 0,
            "task_correction_instructions": None,
            "task_log": updated_log,
        }

    new_failure_count = failure_count + 1
    logger.warning(
        "architect_dispatch_node: task %s FAILED (failure_count now %d): %s",
        current_task["task_id"],
        new_failure_count,
        correction_notes,
    )

    if new_failure_count < 3:
        return {
            "task_failure_count": new_failure_count,
            "task_correction_instructions": correction_notes,
        }

    logger.warning(
        "architect_dispatch_node: escalating task %s after %d failures — re-decomposing",
        current_task["task_id"],
        new_failure_count,
    )

    try:
        subtasks = run_architect_redecompose(
            failing_task=current_task,
            spec_path=state.get("architect_spec_path") or "",
            shared_deps_path=state["shared_deps_path"],
            run_dir=state.get("run_dir") or None,
        )
    except Exception as exc:
        logger.error(
            "architect_dispatch_node: redecompose failed for %s: %s — resetting failure count",
            current_task["task_id"],
            exc,
        )
        return {
            "task_failure_count": 0,
            "task_correction_instructions": None,
        }

    new_queue = list(task_queue)
    new_queue[current_index : current_index + 1] = subtasks
    logger.info(
        "architect_dispatch_node: inserted subtasks [%s, %s] at index %d",
        subtasks[0]["task_id"],
        subtasks[1]["task_id"],
        current_index,
    )
    return {
        "task_queue": new_queue,
        "task_failure_count": 0,
        "task_correction_instructions": None,
    }


def synthesis_node(state: PipelineState) -> dict:
    """Run the Synthesis agent to consolidate critic reports.

    Reads the three critic report paths from state, calls run_synthesis to
    produce a single SYNTHESIS_REPORT.md in /context/, and stores the path.
    Raw critic outputs never flow beyond this node.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict updating ``synthesis_report_path`` and ``revision_count``
        if blocking issues require a revision cycle.
    """
    t0 = time.perf_counter()
    logger.info("synthesis_node: consolidating critic feedback")
    out_path = state.get("synthesis_report_path")
    if not out_path:
        logger.error("synthesis_node: synthesis_report_path is not set in state")
        return {"synthesis_report_path": None}
    try:
        report_path, has_blocking = run_synthesis(
            test_feedback_path=state.get("test_feedback_path"),
            security_feedback_path=state.get("security_feedback_path"),
            quality_feedback_path=state.get("quality_feedback_path"),
            out_path=out_path,
            run_dir=state.get("run_dir") or None,
        )
    except Exception as exc:
        logger.error("synthesis_node: failed: %s", exc)
        return {"synthesis_report_path": None}

    logger.info(
        "synthesis_node: done in %.2fs — blocking=%s path=%s",
        time.perf_counter() - t0,
        has_blocking,
        report_path,
    )
    return {
        "synthesis_report_path": report_path,
        "has_blocking_issues": has_blocking,
    }


def should_revise(state: PipelineState) -> str:
    """Route after synthesis: targeted revision or end.

    Reads SYNTHESIS_REPORT.md from disk via read_synthesis_report() rather than
    trusting the boolean already in state, so the decision is grounded in the
    file that was actually written.

    Args:
        state: The current pipeline state.

    Returns:
        "architect_revision" if blocking issues remain and revision budget allows,
        "end" otherwise.
    """
    report_path = state.get("synthesis_report_path")
    revision_count = state.get("revision_count", 0)

    if not report_path:
        logger.warning("should_revise: synthesis_report_path is None — routing to end")
        return "end"

    report = read_synthesis_report(report_path)
    has_blocking = report["has_blocking_issues"]

    if has_blocking and revision_count < 2:
        logger.info(
            "should_revise: blocking issues found, revision_count=%d — routing to architect_revision",
            revision_count,
        )
        return "architect_revision"

    logger.info(
        "should_revise: routing to end (has_blocking=%s, revision_count=%d)",
        has_blocking,
        revision_count,
    )
    return "end"


def architect_revision_node(state: PipelineState) -> dict:
    """Generate targeted revision tasks from the synthesis report.

    Calls run_architect_revision() to produce a minimal task list covering only
    the files implicated by blocking issues. Replaces task_queue entirely and
    resets the coder loop to index 0. Increments revision_count here — not in
    the coder and not in synthesis.

    generated_file_paths is intentionally NOT reset: critics need those paths
    on the next pass, and the coder overwrites specific files in-place.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict updating task_queue, current_task_index,
        revision_count, task_failure_count, and task_correction_instructions.
        Returns {"status": "failed"} on unrecoverable error.
    """
    revision_number = state.get("revision_count", 0) + 1
    report_path = state.get("synthesis_report_path") or ""

    logger.info(
        "architect_revision_node: starting revision %d from %s",
        revision_number,
        report_path,
    )

    try:
        revision_tasks = run_architect_revision(
            synthesis_report_path=report_path,
            architect_spec_path=state.get("architect_spec_path") or "",
            shared_deps_path=state.get("shared_deps_path", ""),
            generated_file_paths=state.get("generated_file_paths", []),
            revision_number=revision_number,
            run_dir=state.get("run_dir") or None,
        )
    except Exception as exc:
        logger.error("architect_revision_node: run_architect_revision failed: %s", exc)
        return {"status": "failed"}

    if not revision_tasks:
        logger.warning(
            "architect_revision_node: no revision tasks produced — advancing with empty queue"
        )

    logger.info(
        "architect_revision_node: queued %d revision tasks for revision %d",
        len(revision_tasks),
        revision_number,
    )

    return {
        "task_queue": revision_tasks,
        "current_task_index": 0,
        "revision_count": revision_number,
        "task_failure_count": 0,
        "task_correction_instructions": None,
    }


def e2b_node(state: PipelineState) -> dict:
    """Execute generated files in an e2b sandbox and capture runtime output.

    Writes each generated file to the sandbox filesystem (flat namespace under
    /home/user/), attempts to run the main entrypoint (main.py if present,
    otherwise the first file), and captures stdout, stderr, and exit code.
    The sandbox is shut down after execution regardless of outcome. A 30-second
    timeout guards against generated code that hangs.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict updating ``e2b_output``.
    """
    from e2b_code_interpreter import Sandbox
    from scripts.sandbox import wrap_user_command

    file_paths: list[str] = state.get("generated_file_paths", [])
    if not file_paths:
        logger.warning("e2b_node: no generated files — skipping sandbox execution")
        return {
            "e2b_output": E2bOutput(
                stdout="", stderr="No files to execute.", exit_code=-1
            )
        }

    stdout = ""
    stderr = ""
    exit_code = -1

    sandbox = None
    try:
        sandbox = Sandbox.create(timeout=30, api_key=config.E2B_API_KEY)
        for abs_path in file_paths:
            try:
                source = Path(abs_path).read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("e2b_node: could not read %s: %s", abs_path, exc)
                continue
            filename = Path(abs_path).name
            sandbox.files.write(f"/home/user/{filename}", source)

        names = [Path(p).name for p in file_paths]
        entrypoint = "main.py" if "main.py" in names else names[0]

        result = sandbox.commands.run(
            wrap_user_command(f"cd /home/user && python3 {entrypoint}"),
            timeout=30,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        exit_code = result.exit_code if result.exit_code is not None else -1

    except Exception as exc:
        logger.error("e2b_node: sandbox error: %s", exc)
        stderr = str(exc)
        exit_code = -1
    finally:
        if sandbox is not None:
            try:
                sandbox.kill()
            except Exception as exc:
                logger.warning("e2b_node: sandbox.kill() failed: %s", exc)

    e2b_output = E2bOutput(stdout=stdout, stderr=stderr, exit_code=exit_code)
    logger.info(
        "e2b_node: exit_code=%d stdout=%d chars stderr=%d chars",
        exit_code,
        len(stdout),
        len(stderr),
    )
    return {"e2b_output": e2b_output}


def github_node(state: PipelineState) -> dict:
    """Route to dry-run or live GitHub publish based on PIPELINE_MODE.

    Also renders the per-run API cost summary from the metrics ledger
    written during the pipeline — this is the last node, so it is the
    one chance to capture totals before the graph exits.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict updating ``github_repo_url``, ``status``, and
        ``api_metrics_summary_path``.
    """
    if config.PIPELINE_MODE == "dry_run":
        logger.warning("github_node: DRY RUN — no repo will be created")
        result = _github_node_dry_run(state)
    else:
        result = _github_node_live(state)

    run_dir = state.get("run_dir")
    if run_dir:
        try:
            summary_path = write_summary(run_dir)
            result["api_metrics_summary_path"] = str(summary_path)
        except Exception as exc:
            logger.warning("github_node: failed to write metrics summary: %s", exc)
            result["api_metrics_summary_path"] = None

    return result


def _github_node_dry_run(state: PipelineState) -> dict:
    """Write a local manifest of what would have been committed to GitHub.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict with a placeholder ``github_repo_url`` and ``status``.
    """
    repo_name = _project_name_slug(state.get("project_brief", ""))
    files_to_commit = (
        state.get("generated_file_paths", []) + state.get("devops_config_paths", [])
    )
    manifest_path = Path(state["run_dir"]) / "GITHUB_DRY_RUN.md"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        f"# Dry run: would create repo '{repo_name}'\n\n"
        "## Files that would be committed:\n"
        + "\n".join(f"- {f}" for f in files_to_commit),
        encoding="utf-8",
    )
    logger.warning("github_node dry run: manifest written to %s", manifest_path)
    return {
        "github_repo_url": f"[dry-run] would create: {repo_name}",
        "status": "complete",
    }


def _github_node_live(state: PipelineState) -> dict:
    """Publish generated files to a new GitHub repo and open an initial PR.

    Reads generated_file_paths and devops_config_paths from state (disk paths),
    creates a GitHub repo named after the project brief slug, commits all files
    to a ``scaffold/initial`` branch, and opens an initial PR against main.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict updating ``github_repo_url`` and ``status``.
    """
    t0 = time.perf_counter()
    logger.info("github_node: publishing to GitHub")
    try:
        repo_url = run_github(
            project_brief=state.get("project_brief", ""),
            generated_file_paths=state.get("generated_file_paths", []),
            devops_config_paths=state.get("devops_config_paths", []),
        )
    except Exception as exc:
        logger.error("github_node: failed: %s", exc)
        return {"status": "failed", "github_repo_url": None}
    logger.info(
        "github_node: done in %.2fs — repo at %s", time.perf_counter() - t0, repo_url
    )
    return {"github_repo_url": repo_url, "status": "complete"}


def _route_after_architect_dispatch(state: PipelineState) -> str:
    """Route after architect_dispatch_node: loop to coder or exit to e2b.

    Args:
        state: The current pipeline state.

    Returns:
        "coder" if tasks remain, "e2b" if queue is exhausted.
    """
    if state["current_task_index"] >= len(state["task_queue"]):
        logger.info(
            "architect_dispatch: queue exhausted at index %d — routing to e2b",
            state["current_task_index"],
        )
        return "e2b"
    return "coder"


# ---------------------------------------------------------------------------
# Workspace bootstrap node
# ---------------------------------------------------------------------------


def workspace_node(state: PipelineState) -> dict:
    """Create the run workspace and populate path fields in state."""
    validated_brief = config.validate_brief(state["project_brief"])
    run_dir = create_run_workspace(validated_brief)
    return {
        "project_brief": validated_brief,
        "run_dir": str(run_dir),
        "shared_deps_path": str(run_dir / "context" / "shared_dependencies.md"),
        "task_queue_path": str(run_dir / "context" / "task_queue.json"),
        "api_metrics_path": str(metrics_path_for(run_dir)),
        "architect_spec_path": str(run_dir / "context" / "ARCHITECT_SPEC.md"),
        "interfaces_path": str(run_dir / "context" / "INTERFACES.py"),
        "synthesis_report_path": str(run_dir / "context" / "SYNTHESIS_REPORT.md"),
    }


def spec_clarifier_node(state: PipelineState) -> dict:
    """Run the Spec Clarifier on the project brief.

    Calls run_spec_clarifier() to produce clarified_brief.md inside the
    per-run workspace. Stores only the path in state — never brief content.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict updating ``clarified_brief_path``.
    """
    t0 = time.perf_counter()
    logger.info("spec_clarifier_node: starting")
    try:
        conventions = CONVENTIONS_PATH.read_text(encoding="utf-8")
        result = run_spec_clarifier(
            project_brief=state["project_brief"],
            conventions=conventions,
            run_dir=state["run_dir"],
        )
    except Exception as exc:
        logger.error("spec_clarifier_node: failed: %s", exc)
        return {"clarified_brief_path": ""}
    logger.info(
        "spec_clarifier_node: done in %.2fs — %s",
        time.perf_counter() - t0,
        result["clarified_brief_path"],
    )
    return {"clarified_brief_path": result["clarified_brief_path"]}


def architect_node(state: PipelineState) -> dict:
    """Run the two-pass Architect to produce spec, interfaces, deps, and task queue.

    Reads the clarified brief from disk and delegates to run_architect(),
    which writes ARCHITECT_SPEC.md, INTERFACES.py, shared_dependencies.md,
    and task_queue.json into run_dir/context/. Stores task queue + paths
    in state — never file content.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict updating the architect path fields and task_queue.
    """
    t0 = time.perf_counter()
    logger.info("architect_node: starting")
    try:
        conventions = CONVENTIONS_PATH.read_text(encoding="utf-8")
        clarified_brief = Path(state["clarified_brief_path"]).read_text(
            encoding="utf-8"
        )
        result = run_architect(
            clarified_brief=clarified_brief,
            conventions=conventions,
            run_dir=state["run_dir"],
        )
    except Exception as exc:
        logger.error("architect_node: failed: %s", exc)
        return {"status": "failed"}
    logger.info(
        "architect_node: done in %.2fs — %d tasks queued",
        time.perf_counter() - t0,
        len(result["task_queue"]),
    )
    return {
        "architect_spec_path": result["architect_spec_path"],
        "interfaces_path": result["interfaces_path"],
        "shared_deps_path": result["shared_deps_path"],
        "task_queue_path": result["task_queue_path"],
        "task_queue": result["task_queue"],
    }


# ---------------------------------------------------------------------------
# Graph construction — compiled at module level for importability
# ---------------------------------------------------------------------------

_builder = StateGraph(PipelineState)
_builder.add_node("workspace", workspace_node)
_builder.add_node("spec_clarifier", spec_clarifier_node)
_builder.add_node("architect", architect_node)
_builder.add_node("architect_dispatch", architect_dispatch_node)
_builder.add_node("coder", coder_node)
_builder.add_node("e2b", e2b_node)
_builder.add_node("test_writer_node", test_writer_node)
_builder.add_node("security_reviewer_node", security_reviewer_node)
_builder.add_node("quality_reviewer_node", quality_reviewer_node)
_builder.add_node("devops_node", devops_node)
_builder.add_node("synthesis", synthesis_node)
_builder.add_node("architect_revision", architect_revision_node)
_builder.add_node("github", github_node)

_builder.add_edge(START, "workspace")
_builder.add_edge("workspace", "spec_clarifier")
_builder.add_edge("spec_clarifier", "architect")
_builder.add_edge("architect", "architect_dispatch")
_builder.add_conditional_edges(
    "architect_dispatch",
    _route_after_architect_dispatch,
    {"coder": "coder", "e2b": "e2b"},
)
_builder.add_edge("coder", "architect_dispatch")
_builder.add_conditional_edges(
    "e2b",
    dispatch_critics,
    [
        "test_writer_node",
        "security_reviewer_node",
        "quality_reviewer_node",
        "devops_node",
    ],
)
_builder.add_edge("test_writer_node", "synthesis")
_builder.add_edge("security_reviewer_node", "synthesis")
_builder.add_edge("quality_reviewer_node", "synthesis")
_builder.add_edge("devops_node", "synthesis")
_builder.add_conditional_edges(
    "synthesis",
    should_revise,
    {"architect_revision": "architect_revision", "end": "github"},
)
_builder.add_edge("architect_revision", "architect_dispatch")
_builder.add_edge("github", END)

app = _builder.compile()


