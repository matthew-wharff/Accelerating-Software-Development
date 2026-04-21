import re
import shutil
from datetime import datetime
from pathlib import Path

from scripts.logger import get_logger

logger = get_logger(__name__)


def create_run_workspace(project_brief: str) -> Path:
    """Create an isolated workspace directory for a single pipeline run.

    Structure:
        output/<timestamp>-<slug>/
            context/           # runtime context files
            code/              # generated code
            reports/           # critic outputs

    Returns the absolute path to the run directory.
    """
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    slug = _slugify(project_brief)[:40]
    run_dir = Path("output") / f"{timestamp}-{slug}"

    (run_dir / "context").mkdir(parents=True, exist_ok=True)
    (run_dir / "code").mkdir(exist_ok=True)
    (run_dir / "reports").mkdir(exist_ok=True)

    template = Path("context/shared_dependencies.template.md")
    if not template.exists():
        raise FileNotFoundError(
            f"Template not found at {template}. Run prompt 1 first."
        )
    shutil.copy(template, run_dir / "context" / "shared_dependencies.md")

    logger.info(f"Created run workspace: {run_dir.absolute()}")
    return run_dir.absolute()


def _slugify(text: str) -> str:
    """Convert arbitrary text to a filesystem-safe slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')
