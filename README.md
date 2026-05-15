# Multi-Agent Dev Assistant

A LangGraph pipeline that turns a plain-English project brief into a complete, scaffolded codebase — tests, security review, CI/CD config, and a live GitHub repo.

## What it does

**You write:**

> Build me a Python REST API for a task manager with user authentication.

**The system produces:**

- Fully written source code, generated one file at a time
- Unit and integration tests
- An OWASP-style security review
- A Dockerfile and GitHub Actions CI/CD workflow
- A private GitHub repository with all of the above committed

## Pipeline at a glance

```
       Project Brief
             |
             v
    [Workspace Bootstrap]   --> output/<run_id>/{code,context,reports}
             |
             v
      [Spec Clarifier]      --> 3-5 clarifying questions -> clarified_brief.md
             |
             v
        [Architect]         --> shared_deps.md, INTERFACES.py, task_queue.json
             |
             v
   [Coder (Ralph Loop)]     --> per task: implement -> validate -> write -> reset
             |
             v
       [e2b Sandbox]        --> execute generated code (30s timeout)
             |
             v
     parallel fan-out
  +-------+-------+--------+--------+
  |       |       |        |
  v       v       v        v
 Test   Security  Code   DevOps
 Writer Reviewer Quality (Sonnet:
 (Haiku)(Haiku)  (Haiku) Dockerfile,
                          CI/CD)
  |       |       |        |
  +-------+---+---+--------+
              |
              v
        [Synthesis]         --> critic firewall -> SYNTHESIS_REPORT.md
              |
       revision loop (max 2x, routes back to Coder if critical issues)
              |
              v
       [GitHub MCP]         --> create repo + commit (live mode only)
              |
              v
            Output
```

## Why this is interesting

The hard problem in multi-file code generation is **context pollution**, not raw model capability. Research cited in [context/project_guide_v3.md](context/project_guide_v3.md) shows single-function coding tasks reach ~87% accuracy, while multi-file tasks with accumulated context drop to ~19%. This system is organized end-to-end around closing that gap.

Three rules govern every agent invocation:

1. **Decompose before generating** — the Architect produces a dependency-ordered task queue, not a monolithic spec dump. The Coder receives one task at a time.
2. **Isolate by default** — each agent invocation receives only what it needs: task description, relevant interfaces, the shared dependency manifest, and project conventions. Never full conversation history. Never sibling agents' source.
3. **Compress at boundaries, not thresholds** — context resets at logical completion (file written, test passed), not when token counts hit arbitrary limits.

Concretely, this shows up as the Coder's Ralph Loop, the Synthesis Agent acting as a context firewall between critics and any revision, and a state schema that holds file *paths* — never file contents.

## Getting started

### Prerequisites

- Python 3.11+ (pyenv-managed; do not use the system Python)
- A GitHub PAT with `repo` scope only — see [SECURITY.md](SECURITY.md#github-pat--least-privilege-scope) for the scope rationale and verification script
- API keys for Anthropic and [e2b.dev](https://e2b.dev)

### Setup

```bash
git clone <repo-url>
cd Accelerating-Software-Development
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in ANTHROPIC_API_KEY, E2B_API_KEY, GITHUB_PAT
```

### Run the pipeline

```bash
# Dry-run mode (default) — no real GitHub repos are created
python3 -m graph.pipeline "build a hello world CLI"

# Live mode — actually creates a private GitHub repo
PIPELINE_MODE=live python3 -m graph.pipeline "build a hello world CLI"
```

### Run the tests

```bash
pytest -v                      # all unit tests
pytest -m integration          # integration tests (real API calls)
pytest tests/test_config.py    # fast smoke test for env / config
```

## Model assignments

| Agent | Model | Why |
|---|---|---|
| Architect, Coder, Synthesis, DevOps | `claude-sonnet-4-20250514` | Deep reasoning, complex generation |
| Test Writer, Security Reviewer, Code Quality | `claude-haiku-4-5-20251001` | Review-only — Haiku is sufficient and ~10x cheaper |

These assignments are hard rules in [CLAUDE.md](CLAUDE.md): critics never use Sonnet, the Architect and Coder never use Haiku.

## Pipeline modes

`PIPELINE_MODE` controls destructive side effects. Default is `dry_run`.

| Mode | What happens |
|---|---|
| `dry_run` (default) | The GitHub agent logs intended actions but does not call the GitHub API. No repos, no commits, no PRs. Safe for audits, tests, and exploratory work. |
| `live` | Full execution including real GitHub repository creation. Opt-in only. |

This default exists because of a real incident: five real GitHub repositories were created during a single audit session before anyone noticed. Fail-safe defaults eliminate that entire class of bug — opting into live mode must be explicit.

## What happened before any agent code was written

This project was not vibe-coded. A meaningful amount of design and research work shipped before the first agent file existed:

- **Researched production coding-agent patterns first** — Smol Developer, MetaGPT, Aider, and Sweep AI. The lessons (decompose, isolate, compress) were distilled into a context-isolation architecture before code was written.
- **Synthesized the research into a formal project guide and an ordered task list** — [context/project_guide_v3.md](context/project_guide_v3.md) (the full reference) and [context/DevAssistant_TaskList_v4.md](context/DevAssistant_TaskList_v4.md) (a priority-labeled, dependency-ordered plan).
- **Conventions and rules up front** — [context/CONVENTIONS.md](context/CONVENTIONS.md), [context/ARCHITECTURE.md](context/ARCHITECTURE.md), and [CLAUDE.md](CLAUDE.md) were committed before the first agent was implemented, so every generation and refactor since has had stable ground truth.
- **Phases with explicit gates** — no phase starts until the previous phase's sign-off document is committed. Phase 1B's gate required a prompt-injection audit, sandbox isolation verification, and cost profiling — without those, Phase 2 does not begin.

## Project phases

| Phase | Scope | Status |
|---|---|---|
| **1A** | Local multi-agent pipeline — all agents running on a developer machine | Complete |
| **1B** | Hardening, testing, prompt-injection audit, dry-run guards, cost profiling | Complete |
| **2** | Cloud-hosted, authenticated API in front of the pipeline | Next |
| **3** | iPhone app — submit briefs, view results, browse generated repos | Planned |

Phase 1B sign-off artifacts currently in tree: [SECURITY.md](SECURITY.md) (prompt-injection audit + PAT scope rules), [SANDBOX_SECURITY_VERIFICATION.md](SANDBOX_SECURITY_VERIFICATION.md) (e2b isolation tests), and [REFACTOR_AUDIT.md](REFACTOR_AUDIT.md) (stable-vs-runtime context split audit).


## How Claude and Claude Code were used to build this

This project leans on two complementary surfaces:

- **Claude (web / projects)** handled the design work: agentic-workflow research, architectural decisions, drafting the project guide, system-prompt engineering for each agent, hosting and tech-stack research, and iteration on the design docs.
- **Claude Code** handled the implementation work in this repository: writing agent code, refactors (notably the Context Folder Refactor that split stable inputs from runtime-generated artifacts), writing and debugging tests, and translating decisions from the Claude (web) planning sessions into committed code.
- **[CLAUDE.md](CLAUDE.md)** is the bridge between the two. It gives Claude Code the project context, conventions, and constraints up front so no session has to re-derive the architecture.

## Reference files

The README intentionally stays shallow. The deeper reading lives in [context/](context/) and the top-level audit docs.

| File | What's in it |
|---|---|
| [context/project_guide_v3.md](context/project_guide_v3.md) | Full architectural reference — go here to actually understand the system |
| [context/DevAssistant_TaskList_v4.md](context/DevAssistant_TaskList_v4.md) | Ordered task plan with priority labels (PRE-, MVP-, AGT-, HRD-) |
| [context/ARCHITECTURE.md](context/ARCHITECTURE.md) | Short architectural overview, injected into every agent call |
| [context/CONVENTIONS.md](context/CONVENTIONS.md) | Coding standards, injected into every agent call |
| [context/shared_dependencies.template.md](context/shared_dependencies.template.md) | Template seed for the runtime manifest each run populates |
| [CLAUDE.md](CLAUDE.md) | Project rules for Claude Code, including "what NOT to do" |
| [SECURITY.md](SECURITY.md) | Prompt-injection threat model, mitigations, residual risks, PAT scope rules |
| [SANDBOX_SECURITY_VERIFICATION.md](SANDBOX_SECURITY_VERIFICATION.md) | e2b sandbox isolation verification |
| [REFACTOR_AUDIT.md](REFACTOR_AUDIT.md) | Static audit of the stable-vs-runtime context split |
