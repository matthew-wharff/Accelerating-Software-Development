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
```

## Project Structure

```
agents/       # one .py file per agent (coder, architect, spec_clarifier, etc.)
graph/        # LangGraph graph definition — pipeline.py lives here
state/        # shared state schema — schema.py
prompts/      # prompt template strings
context/      # stable context files injected into every agent call (see below)
tests/        # unit + integration tests
output/       # generated code lands here — gitignored, never committed
scripts/      # utility scripts (file_writer.py, logger.py)
```

## Models

| Agent | Model | Why |
|---|---|---|
| Architect, Coder, Synthesis, DevOps | `claude-sonnet-4-20250514` | Deep reasoning, complex generation |
| Test Writer, Security Reviewer, Code Quality | `claude-haiku-4-5-20251001` | Review tasks — Haiku is sufficient and 10x cheaper |

**IMPORTANT: Never use Sonnet for critic agents. Never use Haiku for Architect or Coder.**

## Architecture: How Context Flows

The core design constraint is **context isolation** — the 87%/19% accuracy gap between single-task and multi-file generation is caused by context pollution, not model capability. Every decision enforces this.

**Pipeline order:** Spec Clarifier → Architect → Coder (Ralph Loop) → e2b Sandbox → [Test Writer + Security Reviewer + Code Quality + DevOps] in parallel → Synthesis → revision loop (max 2x) → GitHub MCP

**Coder uses the Ralph Loop:** pick task → implement → validate → write to disk → reset context → pick next task. One file per task. Fresh context per task.

**State holds file paths, never file contents.** Generated code is written to `/output/` immediately. State stores the path. Agents read from disk when they need source.

**Three stable context files** live in `/context/` and are injected into every agent call:
- `CONVENTIONS.md` — coding standards for this project
- `shared_dependencies.md` — cross-file contract manifest (updated after each Coder task)
- `ARCHITECTURE.md` — high-level system overview

## Conventions

- **Python 3.11+** — never use the system Python; always use the pyenv-managed version
- **Linux environment:** use `python3` for all bash commands — `python` is not aliased on this system. `pip` works fine as-is.
- **Imports:** stdlib → third-party → local, one blank line between groups
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes
- **Error handling:** explicit `try/except` with typed exceptions; never bare `except:`
- **Docstrings:** Google style on all public functions and classes
- **Type annotations:** required on all public function signatures
- **NEVER use `print()`** — use `from utils.logger import logger` and log at the appropriate level (DEBUG/INFO/WARNING/ERROR)
- **NEVER store generated code in LangGraph state** — write to `/output/` and store the path
- **NEVER commit `.env`** — it contains real API keys

## Environment Variables Required

```
ANTHROPIC_API_KEY    # Anthropic API — load via config.py, never hardcode
E2B_API_KEY          # e2b.dev sandbox execution
GITHUB_PAT           # GitHub personal access token, repo scope only
```

Config is validated at startup in `config.py` using `os.environ['KEY']` (not `.get()`) so missing keys fail immediately with a clear error.

## Key External Services

- **e2b.dev** — sandboxed code execution before critics review. SDK: `e2b-code-interpreter`. Timeout: 30s.
- **GitHub MCP** — creates repo and commits generated files after pipeline completes. Uses `@modelcontextprotocol/server-github`.
- **LangGraph Send API** — used for parallel fan-out to critics. Each `Send` creates an isolated state copy.

## What NOT to Do

- Do not pass full source code of previously generated files to the Coder — pass signatures only
- Do not give the Coder the full project spec — give it the current task description only
- Do not pass raw critic output to the Coder on revision — it reads `SYNTHESIS_REPORT.md` only
- Do not let the Coder retry a failing task more than 3 times — escalate to the Architect for re-scoping
- Do not accumulate conversation history in LangGraph state — use compact task completion logs
- Do not run generated code outside an e2b sandbox
