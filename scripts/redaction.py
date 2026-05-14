"""Credential redaction for logs and state serialization.

Provides two public helpers:

- ``redact_string`` masks strings matching known credential patterns and
  a high-entropy fallback. Used by the logger's redaction filter and by
  ``redact_state`` when walking string values.
- ``redact_state`` produces a deep copy of a pipeline state (or any
  mapping) with sensitive field names blanked out and string values run
  through ``redact_string``. Use this whenever you need to log state
  shaped data.

The same regex pipeline backs both helpers so masking is consistent
between log messages and serialized state.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

REDACTED = "[REDACTED]"

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-api03-[A-Za-z0-9_\-]{50,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"ghs_[A-Za-z0-9]{36}"),
    re.compile(r"e2b_[A-Za-z0-9]{20,}"),
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),
)

SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset({"project_brief", "e2b_output"})

SENSITIVE_FIELD_REGEX: re.Pattern[str] = re.compile(
    r"key|token|secret|password|pat", re.IGNORECASE
)

_MAX_RECURSION_DEPTH = 4


def redact_string(text: str) -> str:
    """Mask credential-like substrings in ``text``.

    Applies the explicit-prefix patterns first (Anthropic, GitHub, e2b)
    so specific tokens are caught before the generic high-entropy
    fallback can partially consume them. Non-string inputs are returned
    unchanged so callers can pass arbitrary values without a type check.

    Args:
        text: String to scan. Anything else is returned as-is.

    Returns:
        The input with each matched substring replaced by ``[REDACTED]``.
    """
    if not isinstance(text, str):
        return text
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def _redact_value(value: Any, depth: int = 0) -> Any:
    """Recursively redact a value, respecting a max depth.

    Args:
        value: Arbitrary value to walk.
        depth: Current recursion depth. Stops once it reaches
            ``_MAX_RECURSION_DEPTH`` to guard against pathological input.

    Returns:
        A redacted copy of ``value``. Scalars are returned directly.
    """
    if depth >= _MAX_RECURSION_DEPTH:
        return value
    if isinstance(value, str):
        return redact_string(value)
    if isinstance(value, Mapping):
        return {k: _redact_field(k, v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item, depth + 1) for item in value)
    return value


def _redact_field(key: Any, value: Any, depth: int) -> Any:
    """Redact a single mapping entry by key name and value content.

    Args:
        key: Dict key. String keys are checked against the sensitive
            field name set and regex; non-string keys skip that check.
        value: Value to redact.
        depth: Current recursion depth, forwarded to ``_redact_value``.

    Returns:
        Either ``[REDACTED]`` (if the key is sensitive) or the result of
        redacting ``value`` recursively.
    """
    if isinstance(key, str):
        if key in SENSITIVE_FIELD_NAMES:
            if key == "e2b_output" and isinstance(value, Mapping):
                return {
                    "stdout": redact_string(value.get("stdout", "")),
                    "stderr": redact_string(value.get("stderr", "")),
                    "exit_code": value.get("exit_code"),
                }
            return REDACTED
        if SENSITIVE_FIELD_REGEX.search(key):
            return REDACTED
    return _redact_value(value, depth)


def redact_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return a redacted copy of a pipeline state mapping.

    Sensitive fields named ``project_brief`` and ``e2b_output`` plus any
    key matching ``key|token|secret|password|pat`` are masked. All
    remaining string values pass through ``redact_string`` so embedded
    credentials in otherwise safe fields are still caught. Nested dicts
    and lists are walked up to ``_MAX_RECURSION_DEPTH`` levels deep.

    Args:
        state: Any mapping shaped like ``PipelineState``.

    Returns:
        A plain ``dict`` with the same keys and redacted values.
    """
    return {k: _redact_field(k, v, 1) for k, v in state.items()}
