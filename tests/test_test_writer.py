"""Unit tests for agents/test_writer.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.test_writer import run_test_writer
from tests.conftest import make_text_response


def _seed(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    run_dir = tmp_path / "run"
    (run_dir / "code").mkdir(parents=True)
    (run_dir / "context").mkdir()
    src = run_dir / "code" / "greeter.py"
    src.write_text("def greet(name): return f'Hello, {name}!'\n", encoding="utf-8")
    interfaces = run_dir / "context" / "INTERFACES.py"
    interfaces.write_text("def greet(name: str) -> str: ...\n", encoding="utf-8")
    deps = run_dir / "context" / "shared_dependencies.md"
    deps.write_text("# Shared Deps\n", encoding="utf-8")
    return run_dir, src, interfaces, deps


def _valid_test_response(filename: str) -> str:
    body = (
        "import pytest\n"
        "from greeter import greet\n\n"
        "def test_greet_happy():\n    assert greet('a') == 'Hello, a!'\n"
    )
    return json.dumps({"tests": {filename: body}})


def test_run_test_writer_valid_input_writes_test_file(anthropic_mock, tmp_path):
    anthropic_mock.messages.create.return_value = make_text_response(
        _valid_test_response("test_greeter.py")
    )
    run_dir, src, interfaces, deps = _seed(tmp_path)

    written = run_test_writer(
        generated_file_paths=[str(src)],
        interfaces_path=str(interfaces),
        shared_deps_path=str(deps),
        run_dir=str(run_dir),
    )
    assert any(p.endswith("test_greeter.py") for p in written)
    assert any(p.endswith("TEST_SUMMARY.md") for p in written)
    for p in written:
        assert Path(p).exists()


def test_run_test_writer_empty_file_list_raises(anthropic_mock, tmp_path):
    """Empty file list is a programming error, not graceful input."""
    run_dir, _, interfaces, deps = _seed(tmp_path)
    with pytest.raises(ValueError):
        run_test_writer(
            generated_file_paths=[],
            interfaces_path=str(interfaces),
            shared_deps_path=str(deps),
            run_dir=str(run_dir),
        )


def test_run_test_writer_malformed_response_skipped_but_summary_written(
    anthropic_mock, tmp_path
):
    """Bad JSON should skip the file but still produce TEST_SUMMARY.md."""
    anthropic_mock.messages.create.return_value = make_text_response("not json")
    run_dir, src, interfaces, deps = _seed(tmp_path)

    written = run_test_writer(
        generated_file_paths=[str(src)],
        interfaces_path=str(interfaces),
        shared_deps_path=str(deps),
        run_dir=str(run_dir),
    )
    assert any(p.endswith("TEST_SUMMARY.md") for p in written)


def test_run_test_writer_missing_interfaces_raises(anthropic_mock, tmp_path):
    run_dir, src, _, deps = _seed(tmp_path)
    with pytest.raises(FileNotFoundError):
        run_test_writer(
            generated_file_paths=[str(src)],
            interfaces_path=str(tmp_path / "ghost.py"),
            shared_deps_path=str(deps),
            run_dir=str(run_dir),
        )


def test_run_test_writer_missing_source_file_skipped(anthropic_mock, tmp_path):
    """A non-existent source file should be skipped, not crash the agent."""
    anthropic_mock.messages.create.return_value = make_text_response(
        _valid_test_response("test_ghost.py")
    )
    run_dir, _, interfaces, deps = _seed(tmp_path)

    written = run_test_writer(
        generated_file_paths=[str(tmp_path / "ghost.py")],
        interfaces_path=str(interfaces),
        shared_deps_path=str(deps),
        run_dir=str(run_dir),
    )
    assert any(p.endswith("TEST_SUMMARY.md") for p in written)
