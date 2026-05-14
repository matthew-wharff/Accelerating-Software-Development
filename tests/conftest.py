"""Shared test fixtures.

Provides a helper for building mock Anthropic API responses so unit tests can
stub `anthropic.Anthropic` without making network calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from anthropic.types import TextBlock


def make_text_response(
    text: str,
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> MagicMock:
    """Build a mock Anthropic Message whose content is a single TextBlock.

    Agents iterate `response.content` and `isinstance(block, TextBlock)`,
    so the block must be a real TextBlock instance — not a MagicMock.

    A ``usage`` MagicMock is attached with concrete integer attributes so
    ``scripts.instrumentation.instrumented_call`` can record token totals
    without each test having to wire it up. Tests that care about specific
    numbers can override the kwargs.
    """
    resp = MagicMock()
    resp.content = [TextBlock(type="text", text=text)]
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.cache_creation_input_tokens = cache_creation_input_tokens
    usage.cache_read_input_tokens = cache_read_input_tokens
    resp.usage = usage
    return resp


@pytest.fixture
def anthropic_mock(mocker):
    """Patch anthropic.Anthropic and return the mock client.

    Tests configure `client.messages.create.return_value` for single-call
    agents or `.side_effect = [resp1, resp2, ...]` for multi-call agents.
    """
    mock_client = MagicMock()
    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    return mock_client
