"""Unit tests for the credential redaction module."""

from __future__ import annotations

import pytest

from scripts.redaction import REDACTED, redact_state, redact_string


class TestRedactString:
    """redact_string masks known credential prefixes and high-entropy runs."""

    def test_anthropic_key_redacted(self):
        key = "sk-ant-api03-" + "A" * 95
        text = f"calling api with {key} now"
        result = redact_string(text)
        assert REDACTED in result
        assert key not in result

    def test_github_classic_pat_redacted(self):
        key = "ghp_" + "a" * 36
        result = redact_string(f"token={key}")
        assert REDACTED in result
        assert key not in result

    def test_github_server_pat_redacted(self):
        key = "ghs_" + "B" * 36
        assert key not in redact_string(key)

    def test_github_fine_grained_pat_redacted(self):
        key = "github_pat_" + "C" * 50
        result = redact_string(f"auth: {key}")
        assert REDACTED in result
        assert key not in result

    def test_e2b_key_redacted(self):
        key = "e2b_" + "D" * 30
        assert key not in redact_string(key)

    def test_generic_high_entropy_string_redacted(self):
        blob = "X" * 50
        result = redact_string(f"payload {blob} end")
        assert REDACTED in result
        assert blob not in result

    def test_short_alphanum_not_redacted(self):
        text = "version abc123def456 build 99 status ok"
        assert redact_string(text) == text

    def test_long_path_with_dashes_not_redacted(self):
        path = "output/2026-05-04T19-09-42-write-a-python-function-that-adds-two-nu/code/main.py"
        assert redact_string(path) == path

    def test_normal_log_message_unchanged(self):
        msg = "Coder starting task task_007: models/user.py"
        assert redact_string(msg) == msg

    def test_non_string_passthrough(self):
        assert redact_string(42) == 42  # type: ignore[arg-type]
        assert redact_string(None) is None  # type: ignore[arg-type]

    def test_idempotent(self):
        key = "ghp_" + "x" * 36
        text = f"once {key}"
        once = redact_string(text)
        twice = redact_string(once)
        assert once == twice


class TestRedactState:
    """redact_state masks sensitive fields and walks nested structures."""

    def test_project_brief_masked(self):
        state = {"project_brief": "build a thing", "status": "running"}
        result = redact_state(state)
        assert result["project_brief"] == REDACTED
        assert result["status"] == "running"

    def test_e2b_output_preserves_exit_code(self):
        key = "sk-ant-api03-" + "Z" * 95
        state = {
            "e2b_output": {
                "stdout": f"leaked {key} here",
                "stderr": "",
                "exit_code": 0,
            }
        }
        result = redact_state(state)
        assert key not in result["e2b_output"]["stdout"]
        assert REDACTED in result["e2b_output"]["stdout"]
        assert result["e2b_output"]["exit_code"] == 0

    @pytest.mark.parametrize(
        "field",
        ["api_key", "auth_token", "user_password", "github_pat", "client_secret", "ANTHROPIC_KEY"],
    )
    def test_sensitive_field_names_masked(self, field):
        state = {field: "anything-goes-here"}
        assert redact_state(state)[field] == REDACTED

    def test_benign_fields_untouched(self):
        state = {
            "run_dir": "/abs/path/to/output/2026-05-04T19-09-42-build",
            "status": "complete",
            "revision_count": 2,
        }
        result = redact_state(state)
        assert result == state

    def test_task_log_string_values_redacted(self):
        key = "ghp_" + "q" * 36
        state = {
            "task_log": [
                {
                    "task_id": "task_001",
                    "interface_signature": f"def call(): return '{key}'",
                    "status": "complete",
                }
            ]
        }
        result = redact_state(state)
        assert key not in result["task_log"][0]["interface_signature"]
        assert result["task_log"][0]["task_id"] == "task_001"

    def test_nested_dict_values_redacted(self):
        key = "e2b_" + "n" * 25
        state = {"meta": {"runtime": {"label": f"started with {key}"}}}
        result = redact_state(state)
        assert key not in str(result)

    def test_list_of_strings_redacted(self):
        key = "github_pat_" + "L" * 50
        state = {"generated_file_paths": ["main.py", f"oops_{key}.py"]}
        result = redact_state(state)
        assert key not in result["generated_file_paths"][1]
