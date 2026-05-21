"""Unit tests for e2b_node in graph/pipeline.py.

Mocks e2b_code_interpreter.Sandbox so no real API calls are made.
"""

import sys
import os
from typing import cast
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from state.schema import PipelineState

load_dotenv()


def _make_state(file_paths: list[str]) -> PipelineState:
    return cast(PipelineState, {
        "generated_file_paths": file_paths,
        "project_brief": "test project",
    })


def _make_sandbox_result(stdout: str, stderr: str, exit_code: int) -> MagicMock:
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.exit_code = exit_code
    return result


def test_e2b_node_happy_path(tmp_path):
    """e2b_node returns e2b_output with correct keys on successful execution."""
    src = tmp_path / "main.py"
    src.write_text("print('hello')")

    mock_result = _make_sandbox_result("hello\n", "", 0)
    mock_sandbox = MagicMock()
    mock_sandbox.__enter__ = MagicMock(return_value=mock_sandbox)
    mock_sandbox.__exit__ = MagicMock(return_value=False)
    mock_sandbox.commands.run.return_value = mock_result

    with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
        from graph.pipeline import e2b_node

        output = e2b_node(_make_state([str(src)]))

    assert "e2b_output" in output
    e2b = output["e2b_output"]
    assert e2b["stdout"] == "hello\n"
    assert e2b["stderr"] == ""
    assert e2b["exit_code"] == 0


def test_e2b_node_prefers_main_py(tmp_path):
    """e2b_node uses main.py as entrypoint when present."""
    other = tmp_path / "utils.py"
    other.write_text("x = 1")
    main = tmp_path / "main.py"
    main.write_text("print('main')")

    mock_result = _make_sandbox_result("main\n", "", 0)
    mock_sandbox = MagicMock()
    mock_sandbox.__enter__ = MagicMock(return_value=mock_sandbox)
    mock_sandbox.__exit__ = MagicMock(return_value=False)
    mock_sandbox.commands.run.return_value = mock_result

    with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
        from graph.pipeline import e2b_node

        e2b_node(_make_state([str(other), str(main)]))

    call_args = mock_sandbox.commands.run.call_args[0][0]
    assert "main.py" in call_args


def test_e2b_node_falls_back_to_first_file(tmp_path):
    """e2b_node uses the first file as entrypoint when main.py is absent."""
    first = tmp_path / "app.py"
    first.write_text("print('app')")
    second = tmp_path / "helpers.py"
    second.write_text("pass")

    mock_result = _make_sandbox_result("app\n", "", 0)
    mock_sandbox = MagicMock()
    mock_sandbox.__enter__ = MagicMock(return_value=mock_sandbox)
    mock_sandbox.__exit__ = MagicMock(return_value=False)
    mock_sandbox.commands.run.return_value = mock_result

    with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
        from graph.pipeline import e2b_node

        e2b_node(_make_state([str(first), str(second)]))

    call_args = mock_sandbox.commands.run.call_args[0][0]
    assert "app.py" in call_args


def test_e2b_node_sandbox_exception_captured():
    """e2b_node captures sandbox exceptions and returns them in stderr."""
    with patch("e2b_code_interpreter.Sandbox.create", side_effect=RuntimeError("API failure")):
        from graph.pipeline import e2b_node

        output = e2b_node(_make_state(["/fake/path/main.py"]))

    e2b = output["e2b_output"]
    assert "API failure" in e2b["stderr"]
    assert e2b["exit_code"] == -1


def test_e2b_node_no_files():
    """e2b_node returns early with sentinel output when no files are present."""
    from graph.pipeline import e2b_node

    output = e2b_node(_make_state([]))

    e2b = output["e2b_output"]
    assert e2b["exit_code"] == -1
    assert "No files" in e2b["stderr"]


def test_e2b_node_nonzero_exit_code(tmp_path):
    """e2b_node captures non-zero exit codes from failing programs."""
    src = tmp_path / "main.py"
    src.write_text("raise ValueError('boom')")

    mock_result = _make_sandbox_result("", "ValueError: boom\n", 1)
    mock_sandbox = MagicMock()
    mock_sandbox.__enter__ = MagicMock(return_value=mock_sandbox)
    mock_sandbox.__exit__ = MagicMock(return_value=False)
    mock_sandbox.commands.run.return_value = mock_result

    with patch("e2b_code_interpreter.Sandbox.create", return_value=mock_sandbox):
        from graph.pipeline import e2b_node

        output = e2b_node(_make_state([str(src)]))

    e2b = output["e2b_output"]
    assert e2b["exit_code"] == 1
    assert "ValueError" in e2b["stderr"]
