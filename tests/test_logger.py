"""Tests for the redaction filter wiring on scripts.logger."""

from __future__ import annotations

import logging

import pytest

from scripts.logger import _RedactionFilter, get_logger
from scripts.redaction import REDACTED


@pytest.fixture
def isolated_logger():
    """Yield a freshly-built logger with a unique name and tear it down.

    ``get_logger`` is idempotent on logger name, so each test needs its
    own name to ensure the filter and handlers are attached from scratch.
    """
    name = f"test_logger_{id(object())}"
    logger = get_logger(name, level=logging.DEBUG)
    yield logger
    logger.handlers.clear()
    logger.filters.clear()


def test_filter_attached(isolated_logger):
    assert any(isinstance(f, _RedactionFilter) for f in isolated_logger.filters)


def test_github_pat_redacted_in_caplog(isolated_logger, caplog):
    key = "ghp_" + "x" * 36
    isolated_logger.propagate = True
    with caplog.at_level(logging.INFO, logger=isolated_logger.name):
        isolated_logger.info("token=%s", key)
    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert REDACTED in text
    assert key not in text


def test_anthropic_key_redacted_in_caplog(isolated_logger, caplog):
    key = "sk-ant-api03-" + "Y" * 95
    isolated_logger.propagate = True
    with caplog.at_level(logging.INFO, logger=isolated_logger.name):
        isolated_logger.info("calling claude with %s", key)
    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert REDACTED in text
    assert key not in text


def test_normal_path_unchanged(isolated_logger, caplog):
    path = "/abs/output/2026-05-04T19-09-42-build/code/main.py"
    isolated_logger.propagate = True
    with caplog.at_level(logging.INFO, logger=isolated_logger.name):
        isolated_logger.info("wrote %s", path)
    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert path in text


def test_get_logger_idempotent_does_not_double_attach():
    name = "test_logger_idempotent_check"
    first = get_logger(name)
    handler_count = len(first.handlers)
    filter_count = len(first.filters)
    second = get_logger(name)
    assert second is first
    assert len(second.handlers) == handler_count
    assert len(second.filters) == filter_count
    first.handlers.clear()
    first.filters.clear()


def test_exception_message_redacted_in_caplog(isolated_logger, caplog):
    key = "sk-ant-api03-" + "Q" * 95
    isolated_logger.propagate = True
    with caplog.at_level(logging.ERROR, logger=isolated_logger.name):
        try:
            raise RuntimeError(f"failed call {key}")
        except RuntimeError as exc:
            isolated_logger.error("oops: %s", exc)
    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert REDACTED in text
    assert key not in text
