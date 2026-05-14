import os
import re
from typing import Literal, cast, get_args
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
E2B_API_KEY: str = os.environ["E2B_API_KEY"]
GITHUB_PAT: str = os.environ["GITHUB_PAT"]
# New: pipeline execution mode
Mode = Literal["live", "dry_run"]

def _get_mode() -> Mode:
    val = os.environ["PIPELINE_MODE"]
    if val not in get_args(Mode):
        raise ValueError(f"Invalid PIPELINE_MODE: {val!r}")
    return cast(Mode, val)

PIPELINE_MODE: Mode = _get_mode()


def _get_block_egress() -> bool:
    """Sandbox-side network egress policy.

    Defaults to True (block). Set ``SANDBOX_BLOCK_EGRESS=false`` to opt out
    when generated code legitimately needs outbound access (e.g. ``pip install``).
    """
    val = os.environ.get("SANDBOX_BLOCK_EGRESS", "true").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"Invalid SANDBOX_BLOCK_EGRESS: {val!r}")


SANDBOX_BLOCK_EGRESS: bool = _get_block_egress()


# Per-model pricing in USD per million tokens. Source:
# https://platform.claude.com/docs/en/about-claude/pricing (verified 2026-05).
# Update this table whenever the published rates change — every downstream
# cost calculation reads from here. Keys must match the exact ``model`` id
# passed to ``client.messages.create`` so look-ups don't silently miss.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {
        "input": 3.00,
        "cache_write_5m": 3.75,
        "cache_read": 0.30,
        "output": 15.00,
    },
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "cache_write_5m": 1.25,
        "cache_read": 0.10,
        "output": 5.00,
    },
}


_MAX_BRIEF_LENGTH = 4000

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?|rules?)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"new\s+(system\s+)?(instructions?|prompt)", re.IGNORECASE),
    re.compile(r"</?\s*system\s*>", re.IGNORECASE),
    re.compile(r"\[\s*system\s*\]", re.IGNORECASE),
    re.compile(r"###\s*system", re.IGNORECASE),
]


def validate_brief(brief: str) -> str:
    """Validate and sanitize a user-supplied project brief.

    Strips ASCII control characters (including null bytes), enforces a
    4000-character cap, and rejects briefs containing known prompt-injection
    trigger phrases. Idempotent: re-validating a previously-validated brief
    is a no-op.

    Args:
        brief: Plain-English project description from the user.

    Returns:
        The cleaned brief (control characters removed, whitespace trimmed).

    Raises:
        ValueError: If brief is not a string, is empty after cleaning,
            exceeds the length cap, or matches an injection pattern.
    """
    if not isinstance(brief, str):
        raise ValueError(f"project_brief must be str, got {type(brief).__name__}")

    cleaned = re.sub(r"[\x00-\x1f]", "", brief).strip()

    if not cleaned:
        raise ValueError("project_brief is empty after sanitization")
    if len(cleaned) > _MAX_BRIEF_LENGTH:
        raise ValueError(
            f"project_brief too long: {len(cleaned)} chars (limit {_MAX_BRIEF_LENGTH})"
        )
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            raise ValueError(
                f"project_brief contains a blocked injection pattern: {pattern.pattern!r}"
            )
    return cleaned