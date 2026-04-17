"""LangGraph pipeline definition — MVP architecture proof.

Wires two nodes in a linear graph: coder_node → critic_node.
Each node calls its agent, writes output to /output/, and returns
only file paths in state — never file contents.

Usage:
    python graph/pipeline.py        # runs hardcoded smoke test
    from graph.pipeline import app  # import compiled graph
"""

from __future__ import annotations

from pathlib import Path

import anthropic
from langgraph.graph import END, START, StateGraph

import re

from agents.coder import run_coder_task
from agents.critic import run_critic
from scripts.logger import get_logger
from state.schema import PipelineState, TaskEntry, TaskLogEntry, default_state

CONVENTIONS_PATH = Path(__file__).parent.parent / "context" / "CONVENTIONS.md"
SHARED_DEPS_PATH = Path(__file__).parent.parent / "context" / "shared_dependencies.md"
INTERFACES_PATH = Path(__file__).parent.parent / "context" / "INTERFACES.py"

logger = get_logger(__name__)


def _project_name_slug(brief: str) -> str:
    """Derive a safe directory name from the project brief.

    Args:
        brief: The plain-English project description from state.

    Returns:
        A lowercase, underscore-separated string of at most 40 characters,
        defaulting to ``"project"`` if ``brief`` is blank.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", brief.lower().strip()).strip("_")
    return (slug[:40] or "project")


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

    project_name = _project_name_slug(state.get("project_brief", ""))
    interface_refs = task.get("interface_refs", [])
    dependency_paths = task.get("dependency_paths", [])

    coder_task = {
        "task_id": task["task_id"],
        "target_file": task["target_file"],
        "description": task["description"],
        "interface_refs": interface_refs,
        "dependency_paths": dependency_paths,
        "project_name": project_name,
    }

    # Build relevant_interfaces: pass full INTERFACES.py when refs exist.
    # TODO: filter to only the named symbols from interface_refs (optimization).
    relevant_interfaces = ""
    if interface_refs and INTERFACES_PATH.exists():
        relevant_interfaces = INTERFACES_PATH.read_text(encoding="utf-8")

    # Build prior_signatures from completed task log entries this task depends on.
    prior_sig_parts: list[str] = []
    task_log = state.get("task_log", [])
    for dep_path in dependency_paths:
        for entry in task_log:
            if entry["file_path"].endswith(dep_path) and entry.get("interface_signature"):
                prior_sig_parts.append(f"# {dep_path}\n{entry['interface_signature']}")
                break
    prior_signatures = "\n\n".join(prior_sig_parts)

    try:
        conventions = CONVENTIONS_PATH.read_text(encoding="utf-8")
        shared_deps = SHARED_DEPS_PATH.read_text(encoding="utf-8")
        file_path, extracted_interface = run_coder_task(
            task=coder_task,
            shared_deps=shared_deps,
            relevant_interfaces=relevant_interfaces,
            prior_signatures=prior_signatures,
            conventions=conventions,
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
        logger.error("coder_node: file_writer error for %s: %s", task["target_file"], exc)
        return {"status": "failed"}

    log_entry: TaskLogEntry = {
        "task_id": task["task_id"],
        "task_name": f"Implement {task['target_file']}",
        "status": "complete",
        "file_path": file_path,
        "interface_signature": extracted_interface,
    }

    logger.info("coder_node: wrote %s", file_path)

    return {
        "generated_file_paths": state["generated_file_paths"] + [file_path],
        "task_log": state["task_log"] + [log_entry],
        "current_task_index": current_index + 1,
    }


def critic_node(state: PipelineState) -> dict:
    """Execute the Critic agent against the most recently generated file.

    Reads the last path in ``state["generated_file_paths"]``, delegates to
    ``run_critic``, and returns the feedback file path in state.

    Args:
        state: The current pipeline state.

    Returns:
        Partial state dict updating ``quality_feedback_path`` on success;
        ``{"status": "failed"}`` on any error.
    """
    generated = state["generated_file_paths"]

    if not generated:
        logger.error("critic_node: generated_file_paths is empty — nothing to review")
        return {"status": "failed"}

    file_path = generated[-1]
    logger.info("critic_node: reviewing %s", file_path)

    try:
        conventions = CONVENTIONS_PATH.read_text(encoding="utf-8")
        feedback_path = run_critic(file_path, conventions)
    except FileNotFoundError as exc:
        logger.error("critic_node: source file not found: %s", exc)
        return {"status": "failed"}
    except anthropic.APIError as exc:
        logger.error("critic_node: Claude API error reviewing %s: %s", file_path, exc)
        return {"status": "failed"}

    logger.info("critic_node: feedback written to %s", feedback_path)
    return {"quality_feedback_path": feedback_path}


# ---------------------------------------------------------------------------
# Graph construction — compiled at module level for importability
# ---------------------------------------------------------------------------

_builder = StateGraph(PipelineState)
_builder.add_node("coder", coder_node)
_builder.add_node("critic", critic_node)
_builder.add_edge(START, "coder")
_builder.add_edge("coder", "critic")
_builder.add_edge("critic", END)

app = _builder.compile()


# ---------------------------------------------------------------------------
# Smoke test — hardcoded single-task run to prove the architecture
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    initial_state = default_state(project_brief="MVP pipeline smoke test")
    initial_state["task_queue"] = [
        TaskEntry(
            task_id="task_001",
            target_file="hello_pipeline.py",
            description=(
               # "Write a Python module with a single function `greet(name: str) -> str` "
               # "that returns the string 'Hello, {name}!'. "
               # "Include a Google-style docstring and type annotations."
               "Build a Python REST API for a task manager with SQLite. Include endpoints for create, read, update, delete tasks. Use FastAPI and include basic input validation."
            ),
            interface_refs=[],
            dependency_paths=[],
        )
    ]

    logger.info("Invoking pipeline graph...")
    final_state = app.invoke(initial_state)

    logger.info("Pipeline status   : %s", final_state["status"])
    logger.info("Generated files   : %s", final_state["generated_file_paths"])
    logger.info("Quality feedback  : %s", final_state["quality_feedback_path"])
    logger.info("Task log          : %s", final_state["task_log"])

    assert final_state["generated_file_paths"], "generated_file_paths must not be empty"
    for p in final_state["generated_file_paths"]:
        assert Path(p).exists(), f"Expected generated file on disk: {p}"

    if final_state["quality_feedback_path"]:
        assert Path(final_state["quality_feedback_path"]).exists(), (
            f"Expected feedback file on disk: {final_state['quality_feedback_path']}"
        )

    logger.info("All assertions passed — architecture proof complete.")
    sys.exit(0)
