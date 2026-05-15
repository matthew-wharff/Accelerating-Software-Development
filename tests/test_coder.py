"""Unit tests for agents/coder.py.

Mocks both Claude API calls (generation + interface extraction). Verifies
the generated file is written under run_dir/code/ and shared_dependencies.md
gets the extracted interface appended.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.coder import run_coder_task
from tests.conftest import make_text_response


GENERATED_CODE = "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"
EXTRACTED_INTERFACE = "### Functions\ndef greet(name: str) -> str\n"


def _seed_run_dir(tmp_path: Path) -> tuple[Path, Path]:
    run_dir = tmp_path / "run"
    (run_dir / "code").mkdir(parents=True)
    (run_dir / "context").mkdir()
    shared_deps = run_dir / "context" / "shared_dependencies.md"
    shared_deps.write_text("# Shared Dependencies\n", encoding="utf-8")
    return run_dir, shared_deps


def _two_responses():
    return [
        make_text_response(GENERATED_CODE),
        make_text_response(EXTRACTED_INTERFACE),
    ]


def test_run_coder_task_valid_input_writes_file_and_returns_interface(
    anthropic_mock, tmp_path
):
    anthropic_mock.messages.create.side_effect = _two_responses()
    run_dir, shared_deps = _seed_run_dir(tmp_path)

    task = {
        "task_id": "task_001",
        "target_file": "utils/greeter.py",
        "description": "Implement a greet(name) function.",
        "interface_refs": [],
        "dependency_paths": [],
    }

    file_path, interface = run_coder_task(
        task=task,
        shared_deps="# Shared Dependencies\n",
        shared_deps_path=str(shared_deps),
        relevant_interfaces="",
        prior_signatures="",
        conventions="# Conventions\n",
        run_dir=run_dir,
    )

    assert Path(file_path).exists(), "generated source file should exist on disk"
    assert Path(file_path).read_text(encoding="utf-8") == GENERATED_CODE
    assert interface == EXTRACTED_INTERFACE
    assert "greet" in shared_deps.read_text(encoding="utf-8"), (
        "extracted interface should be appended to shared_dependencies.md"
    )


def test_run_coder_task_empty_strings_handled(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.side_effect = _two_responses()
    run_dir, shared_deps = _seed_run_dir(tmp_path)

    task = {
        "task_id": "task_002",
        "target_file": "empty.py",
        "description": "",
    }

    file_path, _ = run_coder_task(
        task=task,
        shared_deps="",
        shared_deps_path=str(shared_deps),
        relevant_interfaces="",
        prior_signatures="",
        conventions="",
        run_dir=run_dir,
    )
    assert Path(file_path).exists()


@pytest.mark.parametrize("bad_task", [None, 0, "not-a-dict"])
def test_run_coder_task_malformed_task_raises_typeerror(
    anthropic_mock, tmp_path, bad_task
):
    """Non-dict task inputs should fail fast — but never silently corrupt state."""
    anthropic_mock.messages.create.side_effect = _two_responses()
    run_dir, shared_deps = _seed_run_dir(tmp_path)

    with pytest.raises((TypeError, KeyError)):
        run_coder_task(
            task=bad_task,  # type: ignore[arg-type]
            shared_deps="",
            shared_deps_path=str(shared_deps),
            relevant_interfaces="",
            prior_signatures="",
            conventions="",
            run_dir=run_dir,
        )


def test_run_coder_task_huge_inputs_no_crash(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.side_effect = _two_responses()
    run_dir, shared_deps = _seed_run_dir(tmp_path)

    huge = "x" * 50_000
    task = {
        "task_id": "task_003",
        "target_file": "huge.py",
        "description": huge,
        "interface_refs": [],
        "dependency_paths": [],
    }
    file_path, _ = run_coder_task(
        task=task,
        shared_deps=huge,
        shared_deps_path=str(shared_deps),
        relevant_interfaces=huge,
        prior_signatures=huge,
        conventions=huge,
        run_dir=run_dir,
    )
    assert Path(file_path).exists()
