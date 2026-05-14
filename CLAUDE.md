# Multi-Agent Dev Assistant

A LangGraph pipeline that turns a plain-English project brief into a complete, scaffolded codebase — with tests, security review, CI/CD config, and a live GitHub repo. Built in Python, deployed to cloud, consumed via an iPhone app.

## Commands

```bash
# Environment
source .venv/bin/activate          # activate venv before every session

# Install / update dependencies
pip install -r requirements.txt
pip freeze > requirements.txt      # always run after installing anything new

# Run tests
pytest -v                          # all tests
pytest -m integration              # integration tests only (makes real API calls)
pytest tests/test_config.py        # smoke test — confirm env loads correctly

# Lint / format (Ruff handles both)
ruff check .
ruff format .

# Run the pipeline (PIPELINE_MODE defaults to dry_run — no real GitHub repos created)
python3 -m graph.pipeline "build a hello world CLI"

# Live mode — actually creates a GitHub repo
PIPELINE_MODE=live python3 -m graph.pipeline "build a hello world CLI"
```

## Project Structure

```
agents/       # one .py file per agent (coder, architect, spec_clarifier, etc.)
graph/        # LangGraph graph definition — pipeline.py lives here
state/        # shared state schema — schema.py
prompts/      # prompt template strings
context/      # stable, human-edited, committed to git (see "Context Folders" below)
tests/        # unit + integration tests
output/       # per-run workspaces — gitignored, never committed (see "Context Folders" below)
scripts/      # utility scripts (workspace.py, file_writer.py, logger.py)
```

## Context Folders — Stable vs Runtime

The system has TWO context locations with opposite lifecycles. Mixing them causes file corruption — keep the boundary clean.

### Stable context (`/context/`) — committed to git
Human-authored project inputs. Agents read these. Agents NEVER write to these.

- `CONVENTIONS.md` — coding standards, injected into every agent call
- `ARCHITECTURE.md` — high-level system overview
- `shared_dependencies.template.md` — empty manifest template (seeds each run's runtime manifest)
- Project guide and task list documents (current canonical versions only)

### Runtime context (`output/<run_id>/context/`) — gitignored, per-run
Agent-authored, regenerated every pipeline run. Lives inside the per-run workspace.

- `shared_dependencies.md` — seeded from template, populated by Architect, appended by Coder after each task
- `task_queue.json` — written by Architect (Pass 2)
- `ARCHITECT_SPEC.md` — written by Architect (Pass 1)
- `INTERFACES.py` — written by Architect (Pass 1)
- `SYNTHESIS_REPORT.md` — written by Synthesis Agent
- `clarified_brief.md` — written by Spec Clarifier

### Per-run workspace structure
Every pipeline run creates an isolated folder under `output/`:

```
output/<timestamp>-<slug>/
├── context/        # runtime context (above)
├── code/           # generated code files (code/ prefix is stripped on GitHub commit)
└── reports/        # critic outputs (test_feedback.md, security_report.md, quality_report.md)
```

`scripts/workspace.py` exports `create_run_workspace(project_brief)` which creates this structure and seeds the manifest from the template. The `workspace_node` runs first in the graph and writes all per-run paths into state.

## Models

| Agent | Model | Why |
|---|---|---|
| Architect, Coder, Synthesis, DevOps | `claude-sonnet-4-20250514` | Deep reasoning, complex generation |
| Test Writer, Security Reviewer, Code Quality | `claude-haiku-4-5-20251001` | Review tasks — Haiku is sufficient and 10x cheaper |

**IMPORTANT: Never use Sonnet for critic agents. Never use Haiku for Architect or Coder.**

## Architecture: How Context Flows

The core design constraint is **context isolation** — the 87%/19% accuracy gap between single-task and multi-file generation is caused by context pollution, not model capability. Every decision enforces this.

**Pipeline order:** Workspace Bootstrap → Spec Clarifier → Architect → Coder (Ralph Loop, dispatched per task by Architect) → e2b Sandbox → [Test Writer + Security Reviewer + Code Quality + DevOps] in parallel → Synthesis → revision loop (max 2x) → GitHub MCP

**Coder uses the Ralph Loop:** pick task → implement → validate → write to disk → reset context → pick next task. One file per task. Fresh context per task.

**State holds file paths, never file contents.** Generated code is written to `output/<run_id>/code/` immediately. State stores the path. Agents read from disk when they need source.

**Path fields in state** (set by `workspace_node` at pipeline start):
- `run_dir` — absolute path to this run's workspace
- `shared_deps_path`, `task_queue_path`, `architect_spec_path`, `interfaces_path`, `synthesis_report_path`, `clarified_brief_path` — all derived from `run_dir`

Agents read these path fields from state. Hardcoded `context/<runtime-file>` paths are NOT allowed in agent code — only stable files (`CONVENTIONS.md`, `ARCHITECTURE.md`) may be referenced by hardcoded path.

## Pipeline Modes

`PIPELINE_MODE` env var controls destructive side effects. Defaults to `dry_run`.

| Mode | Effect |
|---|---|
| `dry_run` (default) | GitHub node logs intended actions but creates no real repos. Safe for audits, tests, and development |
| `live` | Full execution including real GitHub repo creation |

Background: five real GitHub repos got created during a single audit session because the pipeline was executed to "verify" claims. `dry_run` as default prevents this category of bug — opting into live mode must be explicit.

## GitHub Commit Layout

Generated code lives at `output/<run_id>/code/<filename>` during the run. When the GitHub node commits, it strips the `code/` prefix so files land at the repo root (e.g. `output/<run_id>/code/main.py` → `main.py` in the committed repo). Without this, generated imports like `from models import User` would break because the file would be committed under `code/models.py`.

The `code/` prefix matcher lives in `scripts/workspace.py` as `get_code_prefix()`. Do NOT duplicate this regex elsewhere — agents that need to know the workspace layout import the helper.

The `reports/` and runtime `context/` subfolders are NOT committed to GitHub. They're pipeline-internal artifacts.

## Conventions

- **Python 3.11+** — never use the system Python; always use the pyenv-managed version
- **Linux environment:** use `python3` for all bash commands — `python` is not aliased on this system. `pip` works fine as-is.
- **Imports:** stdlib → third-party → local, one blank line between groups
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes
- **Error handling:** explicit `try/except` with typed exceptions; never bare `except:`
- **Docstrings:** Google style on all public functions and classes
- **Type annotations:** required on all public function signatures
- **NEVER use `print()`** — use `from scripts.logger import get_logger` (e.g. `logger = get_logger(__name__)`) and log at the appropriate level (DEBUG/INFO/WARNING/ERROR). A redaction filter is attached automatically; when logging state-shaped data, route it through `redact_state` from `scripts.redaction` first.
- **NEVER store generated code or agent outputs in LangGraph state** — write to disk under `output/<run_id>/` and store the path
- **NEVER write to `/context/` from agent code** — it's stable, human-authored input only
- **NEVER hardcode runtime paths** — read from `state["run_dir"]` or the specific path field
- **NEVER commit `.env`** — it contains real API keys

## Environment Variables Required

```
ANTHROPIC_API_KEY    # Anthropic API — load via config.py, never hardcode
E2B_API_KEY          # e2b.dev sandbox execution
GITHUB_PAT           # GitHub personal access token, repo scope only
PIPELINE_MODE        # 'dry_run' (default) or 'live' — controls GitHub side effects
```

Config is validated at startup in `config.py` using `os.environ['KEY']` (not `.get()`) so missing keys fail immediately with a clear error. `PIPELINE_MODE` is the one exception — it has a safe default of `dry_run`.

## Key External Services

- **e2b.dev** — sandboxed code execution before critics review. SDK: `e2b-code-interpreter`. Timeout: 30s.
- **GitHub MCP** — creates repo and commits generated files after pipeline completes. Uses `@modelcontextprotocol/server-github`. Respects `PIPELINE_MODE`.
- **LangGraph Send API** — used for parallel fan-out to critics. Each `Send` creates an isolated state copy.

## What NOT to Do

- Do not pass full source code of previously generated files to the Coder — pass signatures only
- Do not give the Coder the full project spec — give it the current task description only
- Do not pass raw critic output to the Coder on revision — it reads `SYNTHESIS_REPORT.md` only
- Do not let the Coder retry a failing task more than 3 times — escalate to the Architect for re-scoping
- Do not accumulate conversation history in LangGraph state — use compact task completion logs
- Do not run generated code outside an e2b sandbox
- Do not write to files in `/context/` from agent code — that folder is read-only from the pipeline's perspective
- Do not hardcode `output/` or `context/<runtime-file>` paths in agent code — read from state
- Do not run the pipeline in `live` mode during audits, tests, or exploratory debugging — use `dry_run`
