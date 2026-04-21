import os
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