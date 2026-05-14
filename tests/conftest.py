"""Shared test fixtures.

Provides a helper for building mock Anthropic API responses so unit tests can
stub `anthropic.Anthropic` without making network calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from anthropic.types import TextBlock


def make_text_response(text: str) -> MagicMock:
    """Build a mock Anthropic Message whose content is a single TextBlock.

    Agents iterate `response.content` and `isinstance(block, TextBlock)`,
    so the block must be a real TextBlock instance — not a MagicMock.
    """
    resp = MagicMock()
    resp.content = [TextBlock(type="text", text=text)]
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
