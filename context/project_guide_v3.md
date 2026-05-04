+-----------------------------------------------------------------------+
| **MULTI-AGENT DEV ASSISTANT**                                         |
|                                                                       |
| *A Complete Project Guide --- From Zero to iPhone*                    |
|                                                                       |
| Architecture · Context Management · Agent Design · Tech Stack ·       |
| Phases · Resources                                                    |
+-----------------------------------------------------------------------+

**Section 1: Introduction --- What Are We Building?**

This guide walks you through a project that uses multiple AI agents ---
think of them as a team of specialized software engineers --- to turn a
plain-English project description into a complete, working codebase.

You write: \"Build me a Python REST API for a task manager with user
authentication.\" The system produces: fully written code, unit tests, a
security audit, a Dockerfile, a GitHub Actions CI/CD pipeline, and a
live GitHub repository --- all automatically.

**What is an LLM?**

  ---------- ------------------------------------------------------------
  **Key      An LLM is a model that takes text as input and produces text
  Idea**     as output. In this project, every agent is a carefully
             crafted text prompt sent to Claude, plus logic that
             processes what Claude writes back.

  ---------- ------------------------------------------------------------

The two Claude models used:

  ---------------------- ------------------------------------------------
  **Model**              **Used For / Why**

  Claude Sonnet          Architect, Coder, Synthesis --- tasks requiring
                         deep reasoning and complex code generation. More
                         capable, higher cost per token.

  Claude Haiku           Critic agents --- faster and cheaper. Critics
                         review code rather than generate it, so Haiku is
                         sufficient and cuts costs significantly.
  ---------------------- ------------------------------------------------

**What is an Agent?**

An agent = an LLM + a goal + the ability to take actions. In this
project, each agent has a specialized system prompt (its job
description), receives scoped input from the pipeline state, calls
Claude, and writes its output back for the next agent.

The key principle is that agents in this project are not
general-purpose. Each has a narrow, well-defined job and receives only
the information it needs for that job. Context isolation is not an
optimization --- it is the architecture itself.

**The Core Design Principle: Minimal Context, Maximum Precision**

  ----------- ------------------------------------------------------------
  **The 87% / Research shows single-function coding tasks achieve \~87%
  19%         accuracy. Multi-file tasks with accumulated context drop to
  Finding**   \~19%. The primary cause is context pollution --- the model
              getting confused by too much information, not a fundamental
              capability limit. Every architectural decision in this
              system is designed around preventing that drop.

  ----------- ------------------------------------------------------------

Three rules govern every decision about what information an agent
receives:

-   Decompose before generating --- the Architect produces a
    dependency-ordered task queue, not a monolithic spec dump. The Coder
    receives one task at a time.

-   Isolate by default --- every agent invocation gets only what it
    needs: task description, relevant interfaces, shared dependency
    manifest, and project conventions. Never full conversation history.
    Never sibling agents\' code.

-   Compress at boundaries, not thresholds --- trigger context cleanup
    when a logical task completes (file written, test passed), not when
    token counts hit arbitrary limits.

**Project Phases**

  ---------------------- ------------------------------------------------
  **Phase**              **What You Build**

  Phase 1A               The full local multi-agent pipeline --- all
                         agents, running on your machine

  Phase 1B               Testing, hardening, and security audit of what
                         you built in 1A

  Phase 2                Host the pipeline in the cloud, expose it as an
                         authenticated API

  Phase 3                iPhone app that submits briefs and displays
                         results
  ---------------------- ------------------------------------------------

**Section 2: Full Architecture Diagram**

Here is the complete pipeline from start to finish. Every section in
this document references a specific part of this diagram. The notable
additions vs. a naive pipeline: a Workspace Node runs first to create a
per-run output folder, the Coder follows a Ralph Loop of one task at a
time, and the output layer now shows two distinct filesystem roles --- a
per-run workspace for generated artifacts, and a stable read-only
context/ directory for project-wide conventions.

+-----------------------------------------------------------------------+
| **MULTI-AGENT DEV ASSISTANT --- FULL PIPELINE**                       |
+-----------------------------------------------------------------------+
|   --------- ------- -------                                           |
| ---- ------- ----------- ------- ----------- ------------------------ |
|                                                                       |
| **📋      **→**   **📂        **→**   **🔍 SPEC   **→**   **🏗️         |
|   P                                                                   |
| ROJECT           WORKSPACE           CLARIFIER           ARCHITECT    |
|   B                                                                   |
| RIEF**           Node**              Agent**             Agent**      |
|                                                                       |
|   --------- ------- -------                                           |
| ---- ------- ----------- ------- ----------- ------------------------ |
+-----------------------------------------------------------------------+
|   -------- -- -                                                       |
| ---------- -- ------------- -- ------------- ------------------------ |
|   *User       *Creates       *Clarifying      *3 artifacts:           |
|   input*      run            questions*       manifest,               |
|               folder +                        interfaces,             |
|               seeds                           task queue*             |
|               manifest*                                               |
|                                                                       |
|   -------- -- -                                                       |
| ---------- -- ------------- -- ------------- ------------------------ |
+-----------------------------------------------------------------------+
|   -                                                                   |
| ----------------------------- ------- ------------------------------- |
|                                  **↓**                                |
|                                                                       |
|   -                                                                   |
| ----------------------------- ------- ------------------------------- |
+-----------------------------------------------------------------------+
|                                                                       |
|  --------------------- --------------- -- --------------------------- |
|                         **💻 CODER         *Ralph Loop: Pick task →   |
|                         Agent (1 Task      Implement → Validate →     |
|                         at a Time)**       Write to run code/ dir →   |
|                                            Reset context → Pick next  |
|                                            task*                      |
|                                                                       |
|                                                                       |
|  --------------------- --------------- -- --------------------------- |
+-----------------------------------------------------------------------+
|   ---------                                                           |
| ------------ ------- ------- -------------- ------------------------- |
|                         **↓**   **→**   **🐳 DEVOPS                   |
|                                         Agent                         |
|                                         (Dockerfile,                  |
|                                         CI/CD)**                      |
|                                                                       |
|   ---------                                                           |
| ------------ ------- ------- -------------- ------------------------- |
+-----------------------------------------------------------------------+
|   --------------------- --------------- ----------------------------- |
|                         **🔬 e2b                                      |
|                         SANDBOX                                       |
|                         (Execute &                                    |
|                         Capture)**                                    |
|                                                                       |
|   --------------------- --------------- ----------------------------- |
+-----------------------------------------------------------------------+
|   -                                                                   |
| -------------------- ------- ---------------------------------------- |
|                         **↓**                                         |
|                                                                       |
|   -                                                                   |
| -------------------- ------- ---------------------------------------- |
+-----------------------------------------------------------------------+
|   ----                                                                |
| ----------------- ------------- -- ------------- -- ------------- --- |
|                                                                       |
|                      **🧪 TEST        **🔒 SECURITY    **✅ CODE      |
|                                                                       |
|                      WRITER           REVIEWER         QUALITY        |
|                                                                       |
|                      Agent**          Agent**          Agent**        |
|                                                                       |
|   ----                                                                |
| ----------------- ------------- -- ------------- -- ------------- --- |
+-----------------------------------------------------------------------+
|   --------------------- --------------------------------------------  |
|                         *← Critic Trio runs in parallel; reports →    |
|                         run reports/ dir →*                           |
|                                                                       |
|   --------------------- --------------------------------------------  |
+-----------------------------------------------------------------------+
|   -                                                                   |
| -------------------------- ------- ---------------------------------- |
|                               **↓**                                   |
|                                                                       |
|   -                                                                   |
| -------------------------- ------- ---------------------------------- |
+-----------------------------------------------------------------------+
|   --------------------- --------------- ----------------------------- |
|                         **🧠 SYNTHESIS                                |
|                         Agent (Context                                |
|                         Firewall)**                                   |
|                                                                       |
|   --------------------- --------------- ----------------------------- |
+-----------------------------------------------------------------------+
|   --                                                                  |
| ------------------- ------- --------------- ------------------------- |
|                         **↓**   *Revision loop:                       |
|                                 high-severity                         |
|                                 issues route                          |
|                                 back to Coder                         |
|                                 with fresh                            |
|                                 context (max                          |
|                                 2x)*                                  |
|                                                                       |
|   --                                                                  |
| ------------------- ------- --------------- ------------------------- |
+-----------------------------------------------------------------------+
|   -                                                                   |
| -------------------- ------- ---------------------------------------- |
|                         **↓**                                         |
|                                                                       |
|   -                                                                   |
| -------------------- ------- ---------------------------------------- |
+-----------------------------------------------------------------------+
|   -------                                                             |
| --------- ---------------------- -- -------------- -- ----------- --- |
|                                                                       |
|              **📁 Run Workspace        **📄 Stable       **🐙 GitHub  |
|                                                                       |
|              output/\<run_id\>/**      Context           Repo (via    |
|                                                                       |
|                                        (context/ ---     MCP)**       |
|                                                                       |
|                                        read-only)**                   |
|                                                                       |
|   -------                                                             |
| --------- ---------------------- -- -------------- -- ----------- --- |
+-----------------------------------------------------------------------+

**How to read this diagram:**

-   Each colored box is one agent (or input/output). The color indicates
    the type of work it does.

-   The Workspace Node runs first, before any agent. It creates a unique
    output/\<run_id\>/ folder with code/, context/, and reports/
    subdirectories --- isolating this run from every other run.

-   The Architect produces three artifacts (manifest, interfaces, task
    queue) that control how much context every downstream agent needs.
    All three land in the run\'s context/ subfolder, not in project-root
    context/.

-   The Coder works through one task at a time with a fresh context
    window per task --- the Ralph Loop. Generated files land in the
    run\'s code/ subfolder.

-   The Critic Trio and DevOps Agent all run simultaneously via
    LangGraph fan-out. Their reports land in the run\'s reports/
    subfolder.

-   The Synthesis Agent acts as a context firewall between the critics
    and any revision --- it compresses three sets of feedback into one
    structured action list.

-   Two filesystem roots feed every agent invocation: the stable
    context/ directory at project root (conventions, architecture docs)
    and the run-specific context/ subfolder (the Architect\'s manifest
    and interfaces). Both together supply shared knowledge without
    shared history.

  ----------- ----------- ----------- ----------- ----------- -----------
  Teal =      Blue =      Purple =    Indigo =    Orange =    Dark =
  Input /     Planning    Coding      Review      DevOps      Output
  Context                                                     

  ----------- ----------- ----------- ----------- ----------- -----------

**Section 3: The Orchestration Layer --- LangGraph**

+-----------------------------------------------------------------------+
| **📍 DIAGRAM FOCUS: LangGraph --- The Pipeline\'s Backbone**          |
|                                                                       |
| LangGraph sits beneath the entire diagram. Every agent, every arrow,  |
| and every loop IS a LangGraph graph. This section explains what       |
| LangGraph is, why it was chosen, and how its state design enforces    |
| context isolation.                                                    |
+-----------------------------------------------------------------------+

**What Problem Does LangGraph Solve?**

Without an orchestration framework you would have to manage execution
order, state passing, loops, and errors entirely yourself. LangGraph
lets you define your pipeline as a directed graph --- a map of nodes
(agents) and edges (connections) --- and handles execution from there.

  ------------- ------------------------------------------------------------
  **Analogy**   LangGraph is like a traffic management system for your
                agents. You draw the roads (graph), set the rules
                (conditional edges), and LangGraph makes sure every piece of
                data gets to the right destination in the right order.

  ------------- ------------------------------------------------------------

**The Three Core Concepts**

**1. State**

The state is a shared Python object --- like a central whiteboard ---
that every agent can read from and write to. Crucially, the state is
designed to support context isolation, not work against it. Two rules
govern it:

-   Store file paths, not file contents. Generated code is written to
    disk. Agents read from disk when they need source code. The state
    references where things are, not what they contain.

-   Use a compact task-completion log, not full message history. The
    state accumulates summaries of what was done (task name, status,
    file path, extracted interface signature) --- not raw LLM
    conversation transcripts.

Every path field in state points somewhere inside the current run\'s
workspace (see Section 4). This is what makes concurrent runs and clean
audits possible.

  ----------------------- ------------------------------------------------
  **State Field**         **What It Contains**

  project_brief           The original project description you submitted

  run_dir                 Absolute path to this run\'s workspace folder
                          (NEW --- set by workspace_node)

  clarified_brief_path    Path to clarified_brief.md in the run\'s
                          context/ subfolder

  architect_spec_path     Path to ARCHITECT_SPEC.md in the run\'s context/

  interfaces_path         Path to INTERFACES.py in the run\'s context/

  shared_deps_path        Path to shared_dependencies.md in the run\'s
                          context/ (seeded from template)

  task_queue_path         Path to task_queue.json in the run\'s context/

  task_log                Compact completion log: {task_name, status,
                          file_path, interface_signature}

  generated_code          Dict of {filename: filepath} --- paths inside
                          run\'s code/ subfolder

  e2b_output              Runtime output from sandbox execution: {stdout,
                          stderr, exit_code}

  synthesis_report_path   Path to SYNTHESIS_REPORT.md in the run\'s
                          reports/ subfolder

  devops_config           Dict of {filename: filepath} --- paths to
                          Dockerfile, ci.yml, etc.

  revision_count          How many revision loops have run (max: 2)

  status                  Current pipeline status: running, complete,
                          failed
  ----------------------- ------------------------------------------------

**2. Nodes**

A node is a Python function that takes the state as input and returns
updates to the state. Each agent is a node. There is also one
infrastructure node --- the workspace_node --- that runs first and
creates the output folder structure.

+-----------------------------------------------------------------------+
| \# Example: what a LangGraph node looks like                          |
|                                                                       |
| def coder_node(state: PipelineState) -\> dict:                        |
|                                                                       |
| \# Read the current task and manifest from the run\'s workspace       |
|                                                                       |
| task = load_task_queue(state\[\'task_queue_path\'\])\[0\]             |
|                                                                       |
| manifest = read_file(state\[\'shared_deps_path\'\])                   |
|                                                                       |
| \# Call Claude with scoped context only                               |
|                                                                       |
| code = call_claude(task, manifest)                                    |
|                                                                       |
| \# Write code to the run\'s code/ subfolder, store only the path      |
|                                                                       |
| path = Path(state\[\'run_dir\'\]) / \'code\' / task.filename          |
|                                                                       |
| path.write_text(code)                                                 |
|                                                                       |
| return {\'task_log\': \[{\'task\': task.name, \'path\': str(path)}\]} |
+-----------------------------------------------------------------------+

**3. Edges and the Send API**

Edges connect nodes. Normal edges always go A → B. Conditional edges use
a function to decide where to route based on current state. The Send API
is LangGraph\'s mechanism for parallel fan-out.

When the Coder finishes and LangGraph needs to fire all three critics
simultaneously, it uses Send to dispatch each critic as an isolated
invocation with its own copy of the relevant state --- this is the
context isolation primitive that ensures critics never see each other\'s
partial output.

+-----------------------------------------------------------------------+
| \# Conditional routing after Synthesis Agent                          |
|                                                                       |
| def should_revise(state: PipelineState) -\> str:                      |
|                                                                       |
| has_critical =                                                        |
| state\[\'synthesis_report\'\]\[\'has_critical_issues\'\]              |
|                                                                       |
| under_limit = state\[\'revision_count\'\] \< 2                        |
|                                                                       |
| if has_critical and under_limit:                                      |
|                                                                       |
| return \'coder\' \# Loop back with fresh context                      |
|                                                                       |
| return \'output\' \# Done                                             |
+-----------------------------------------------------------------------+

**Why LangGraph and Not Something Simpler?**

Two things in this pipeline specifically require LangGraph: conditional
revision loops (cycling back from Synthesis to Coder) and parallel
fan-out with isolated state per branch. A simple for-loop works for
linear pipelines; it breaks down the moment you add loops or
parallelism.

**Resources: LangGraph**

[[LangGraph Official
Documentation]{.underline}](https://langchain-ai.github.io/langgraph/)

[[LangGraph Quickstart
Tutorial]{.underline}](https://langchain-ai.github.io/langgraph/tutorials/introduction/)

[[LangGraph: How to run nodes in parallel (Send
API)]{.underline}](https://langchain-ai.github.io/langgraph/how-tos/branching/)

[[LangGraph: Cycles and revision
loops]{.underline}](https://langchain-ai.github.io/langgraph/concepts/low_level/#cycles)

[[Python TypedDict
documentation]{.underline}](https://docs.python.org/3/library/typing.html#typing.TypedDict)

**Section 4: Context Management --- The Architecture\'s Foundation**

+-----------------------------------------------------------------------+
| **📍 DIAGRAM FOCUS: All Agents --- Context Is the Architecture**      |
|                                                                       |
| This section has no single agent to point to because context          |
| management applies to every agent in the pipeline. Understanding this |
| section is required for understanding every design decision that      |
| follows.                                                              |
+-----------------------------------------------------------------------+

Context management is not an optimization pass you add after the system
works. It is the primary design constraint that shapes every part of the
architecture --- which artifacts the Architect produces, how the Coder
operates, how state is structured, and how handoffs happen between
agents.

**The Three Governing Rules in Practice**

**Rule 1: Decompose Before Generating**

The Architect does not hand the Coder a full spec and say \'build
this.\' It produces a topologically sorted task queue --- an ordered
list of file-level coding tasks derived from the project\'s import and
dependency graph.

Files with no dependencies come first. Files that import from other
modules come after those modules exist. The Coder works through this
queue one task at a time, with a fresh (or near-fresh) context window
per task.

  ----------- ------------------------------------------------------------
  **Why       If the Coder tries to implement a route handler before the
  Topology    database model exists, it has to guess the model\'s
  Matters**   interface. When the model is eventually written with a
              different shape, the route handler breaks. Topological
              ordering eliminates this entire class of inconsistency.

  ----------- ------------------------------------------------------------

**Rule 2: Isolate by Default**

For each task, the Coder receives exactly this context --- nothing more:

-   The current task description from the Architect\'s ordered queue

-   The shared dependency manifest for this run (from the run\'s
    context/ subfolder)

-   Project conventions from the stable context/CONVENTIONS.md

-   Interface definitions relevant to this task only --- not all
    interfaces

-   Signatures (not full implementations) of previously generated files
    this task depends on

**What the Coder explicitly does NOT receive:**

-   The full project spec

-   Full source code of previously generated files --- only their
    exported signatures

-   Conversation history from prior tasks

-   Critic feedback from prior revision cycles --- that gets folded into
    a fresh task re-dispatch

The same principle applies to critics. Each critic receives only the
files relevant to its review scope, not the full codebase. The Security
Reviewer does not need test files. The Test Writer does not need the
Dockerfile.

**Rule 3: Compress at Boundaries**

Context cleanup is triggered when a logical unit of work completes --- a
file is written to disk, a test passes, a task is marked done --- not
when some arbitrary token count is reached.

After each coding task completes, the Architect extracts the public
interface of the generated file (exported functions, class signatures,
type definitions) and appends it to the run\'s shared_dependencies.md.
The full implementation goes to disk and is never re-injected into
context.

**Two Kinds of Context Files --- Stable vs. Runtime**

Context files come in two distinct flavors with opposite lifecycles.
Conflating them was a source of real bugs (manifest corruption,
unreliable git tracking) --- the split below is a hard boundary.

  ------------------ -------------------------- --------------------------------
  **Dimension**      **Stable Context           **Runtime Context
                     (context/)**               (output/\<run_id\>/context/)**

  Lifecycle          Permanent --- lives for    Ephemeral --- created per
                     the life of the project    pipeline run, gitignored

  Author             Human-authored, reviewed   Agent-authored, written during
                     in PRs                     execution

  Git status         Committed                  Ignored (except the .template
                                                file)

  Purpose            Project-wide conventions   Per-run state, contracts, and
                     and doctrine               intermediate artifacts

  Lives in           Repo root: context/        Inside the run\'s workspace:
                                                output/\<run_id\>/context/
  ------------------ -------------------------- --------------------------------

**Stable Context Files (context/ --- committed to git)**

These markdown files live at the project root in context/ and are
human-authored. They carry conventions and doctrine that apply to every
run and every agent. Keep them concise --- they consume context budget
on every invocation.

  --------------------------------- ------------------------------------------------
  **File**                          **Contents and Purpose**

  CONVENTIONS.md                    Coding standards, naming, error handling
                                    patterns, import style, formatting rules.
                                    Equivalent to .cursorrules or CLAUDE.md. Every
                                    agent gets this.

  ARCHITECTURE.md                   High-level system overview, module boundaries,
                                    data flow. Reference only --- not the full spec.

  shared_dependencies.template.md   Empty scaffold (just section headers + bootstrap
                                    env vars). Seeds the runtime manifest at the
                                    start of every pipeline run.

  project_guide_v2.md               This document --- the architectural reference.

  DevAssistant_TaskList_v3.md       The full ordered task list for building the
                                    project itself.
  --------------------------------- ------------------------------------------------

**Runtime Context Files (output/\<run_id\>/context/ --- per-run,
gitignored)**

These files are generated fresh for every pipeline run. They hold the
state and contracts that are specific to that run --- the Architect\'s
decisions, the Coder\'s progress, the Synthesis Agent\'s output. Because
they live inside an isolated run folder, concurrent runs cannot clobber
each other.

  ------------------------ ------------------------------------------------
  **File (per run)**       **Written By / Purpose**

  clarified_brief.md       Spec Clarifier Agent --- brief after clarifying
                           questions

  ARCHITECT_SPEC.md        Architect Agent --- full spec document

  INTERFACES.py            Architect Agent --- type stubs, ABCs, route
                           signatures

  shared_dependencies.md   Architect Agent seeds it from template; Coder
                           appends per-task interface signatures

  task_queue.json          Architect Agent --- ordered, topologically
                           sorted task list

  SYNTHESIS_REPORT.md      Synthesis Agent --- consolidated action list
                           (lives in reports/, not context/)
  ------------------------ ------------------------------------------------

**The Per-Run Workspace**

Every pipeline run creates a new folder under output/ with three
subdirectories. Isolating runs this way was a deliberate design choice
--- it prevents runs from clobbering each other, makes audits and diffs
easy, and mirrors standard build-system conventions (Bazel, CMake,
Cargo).

+-----------------------------------------------------------------------+
| output/                                                               |
|                                                                       |
| └── \<run_id\>/ \# e.g. 2026-04-20T14-32-build-todo-app               |
|                                                                       |
| │ \# (format is illustrative --- any unique id works)                 |
|                                                                       |
| ├── context/ \# runtime context files                                 |
|                                                                       |
| │ ├── clarified_brief.md                                              |
|                                                                       |
| │ ├── ARCHITECT_SPEC.md                                               |
|                                                                       |
| │ ├── INTERFACES.py                                                   |
|                                                                       |
| │ ├── shared_dependencies.md                                          |
|                                                                       |
| │ └── task_queue.json                                                 |
|                                                                       |
| ├── code/ \# generated code (stripped of prefix on GitHub push)       |
|                                                                       |
| │ ├── main.py                                                         |
|                                                                       |
| │ └── models.py                                                       |
|                                                                       |
| └── reports/ \# critic outputs                                        |
|                                                                       |
| ├── test_feedback.md                                                  |
|                                                                       |
| ├── security_report.md                                                |
|                                                                       |
| ├── quality_report.md                                                 |
|                                                                       |
| └── SYNTHESIS_REPORT.md                                               |
+-----------------------------------------------------------------------+

  ------------- ------------------------------------------------------------
  **Workspace   A workspace_node runs first in the graph --- before Spec
  Node**        Clarifier. Its job is to create the run folder, create the
                three subdirectories, seed shared_dependencies.md from the
                template, and set run_dir plus the path fields on state.
                Every subsequent agent reads those paths from state rather
                than hardcoding directory names.

  ------------- ------------------------------------------------------------

**Filesystem as Shared Memory**

Generated code, runtime manifests, and handoff reports live on disk
inside the run folder. Stable conventions live on disk in the
project-root context/ directory. Agents read from disk rather than
receiving artifacts through LangGraph state. This keeps state objects
small, prevents context accumulation, and means any agent can access any
prior output without it being injected into every context window.

**Report-File Handoffs**

When one agent\'s output feeds another, the handoff is a structured
markdown report file --- not raw conversation history. For example, the
Synthesis Agent writes SYNTHESIS_REPORT.md into the run\'s reports/
folder, and the Coder on a revision pass reads that file.

This pattern compresses context naturally. A 3000-token critic
conversation becomes a 200-token action list. The receiving agent starts
fresh with only the signal it needs.

**The GitHub Code/ Prefix Strip**

Generated code lives at output/\<run_id\>/code/main.py during the run
--- the code/ folder is a pipeline-internal artifact layout. When the
GitHub MCP node commits to a new repo, it strips the code/ prefix so
files land at the repo root (main.py, not code/main.py). Without
stripping, an import like from models import User would break because
the user would find code/models.py at the repo root and import models
would fail.

**PIPELINE_MODE --- A Planned Safeguard**

  ------------ ------------------------------------------------------------
  **Deferred   PIPELINE_MODE is not implemented yet but is planned before
  Work**       Phase 1B hardening. When implemented, it will default to
               dry_run, which prevents destructive side effects (GitHub
               repo creation, real API calls where unnecessary) during
               audits and test runs. Live execution requires explicit
               opt-in via PIPELINE_MODE=live. The motivation: five real
               GitHub repos were created during a single audit session
               because the pipeline was executed to \'verify\' claims.
               Fail-safe defaults prevent that category of bug.

  ------------ ------------------------------------------------------------

**Resources: Context Management**

[[Anthropic: Long Context Tips and Best
Practices]{.underline}](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips)

[[Anthropic: Prompt Caching (reduces cost on stable
context)]{.underline}](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)

[[LangGraph Send API (fan-out with isolated
state)]{.underline}](https://langchain-ai.github.io/langgraph/how-tos/branching/)

[[Smol Developer (context isolation pattern
reference)]{.underline}](https://github.com/smol-ai/developer)

**Section 5: Input Processing --- Spec Clarifier & Architect Agents**

+-----------------------------------------------------------------------+
| **📍 DIAGRAM FOCUS: Workspace Node → Spec Clarifier → Architect**     |
|                                                                       |
| These run before any code is written. The Workspace Node creates the  |
| per-run folder. The Spec Clarifier eliminates brief ambiguity. The    |
| Architect converts the clarified brief into three specific artifacts  |
| that control how much context every downstream agent needs --- all    |
| written into the run\'s context/ subfolder.                           |
+-----------------------------------------------------------------------+

**The Spec Clarifier Agent**

Runs after the workspace is created. Asks 3--5 targeted questions that
eliminate the most important ambiguities in the brief. Good clarifying
questions address technical decisions that are hard to change later:
authentication type, database choice, API design, expected scale.

The Spec Clarifier writes its output to clarified_brief.md in the run\'s
context/ subfolder and stores the path in
state\[\'clarified_brief_path\'\]. It does not hold the brief content in
state --- paths, not contents.

  ---------------------- ------------------------------------------------
  **Property**           **Detail**

  Input                  Raw project brief, run_dir from state

  Output                 clarified_brief.md at \<run_dir\>/context/, path
                         stored in state\[\'clarified_brief_path\'\]

  Model                  Claude Sonnet

  File                   agents/spec_clarifier.py
  ---------------------- ------------------------------------------------

**The Architect Agent --- Three Required Artifacts**

The Architect is the most important context engineering component in the
system. Its job is not simply to write a spec --- it is to produce three
specific artifacts that collectively determine how much context every
downstream agent needs. These are not optional. They are the
architecture.

All three artifacts land in the run\'s context/ subfolder. The Architect
does NOT write to the project-root context/ directory --- that\'s
reserved for stable, human-authored files.

**Artifact 1: Shared Dependency Manifest
(\<run_dir\>/context/shared_dependencies.md)**

Every shared type, exported function signature, API contract, data
schema, environment variable, and DOM element ID used across more than
one file. This file travels with every Coder invocation as the
cross-file coherence mechanism.

At the start of the run, this file is seeded from
context/shared_dependencies.template.md (stable, project-root). The
Architect populates the initial structure; the Coder appends the public
interface of each file after implementing it.

**Artifact 2: Interface Definitions
(\<run_dir\>/context/INTERFACES.py)**

Generated in a first pass before any implementation code is written.
Type stubs, abstract base classes, API route signatures, database model
schemas. The Coder implements against these contracts --- it does not
invent them.

  ---------------- ------------------------------------------------------------
  **C Header /     This mirrors the C header file / implementation file split.
  Implementation   Header files define the interface; .c files implement it. In
  Analogy**        Python, this means generating Protocol classes, abstract
                   base classes, and type stubs first --- then implementing
                   them. MetaGPT uses the same Architect-to-Engineer handoff
                   pattern.

  ---------------- ------------------------------------------------------------

**Artifact 3: Ordered Task Queue (\<run_dir\>/context/task_queue.json)**

A topologically sorted list of file-level coding tasks derived from the
project\'s import and dependency graph. Files with zero external
dependencies are generated first. Files that depend on others come after
those dependencies exist.

Each task entry in the queue contains:

-   Target file path (relative --- resolved against \<run_dir\>/code/ at
    write time)

-   The relevant section of the spec for this file only (not the full
    spec)

-   Which interface definitions it implements

-   Which previously generated files it depends on (by path reference,
    not content)

**The Architect-Coder Feedback Loop**

The Architect\'s job does not end when the task queue is dispatched.
After each coding task completes, the Architect evaluates whether the
output satisfies the spec for that task and whether the task queue needs
adjustment before dispatching the next task. This is a tight feedback
loop, not a one-time waterfall handoff.

  ---------------------- ------------------------------------------------
  **Property**           **Detail**

  Input                  clarified_brief_path from state, plus stable
                         CONVENTIONS.md / ARCHITECTURE.md

  Output                 Four files in \<run_dir\>/context/:
                         ARCHITECT_SPEC.md, INTERFACES.py,
                         shared_dependencies.md, task_queue.json

  Model                  Claude Sonnet --- reasoning-heavy, single most
                         important prompt in the pipeline

  File                   agents/architect.py

  Feedback loop          Reviews each completed task, adjusts queue if
                         needed before next dispatch
  ---------------------- ------------------------------------------------

**Resources: Spec Clarifier & Architect**

[[Anthropic: Prompt Engineering
Overview]{.underline}](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)

[[Anthropic: Structured JSON
Outputs]{.underline}](https://docs.anthropic.com/en/docs/build-with-claude/structured-outputs)

[[Anthropic: Few-Shot Prompting
Techniques]{.underline}](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-examples)

[[MetaGPT: Architect-to-Engineer Handoff Pattern
(paper)]{.underline}](https://arxiv.org/abs/2308.00352)

**Section 6: The Coder Agent**

+-----------------------------------------------------------------------+
| **📍 DIAGRAM FOCUS: Coder Agent --- Single Agent, One Task at a       |
| Time**                                                                |
|                                                                       |
| The Coder implements the codebase against the Architect\'s spec ---   |
| one task at a time with a fresh context window per task. Generated    |
| code lands in the run\'s code/ subfolder. This section explains the   |
| Ralph Loop pattern, why single-agent design wins over                 |
| parallelization, and how failure escalation works.                    |
+-----------------------------------------------------------------------+

**The Ralph Loop**

The Coder operates on a strict repeating cycle called the Ralph Loop.
The name comes from the pattern proven by Smol Developer. The cycle
enforces context isolation automatically:

  ---------------------- ------------------------------------------------
  **Ralph Loop Step**    **What Happens**

  1\. Pick Task          Reads the next task from
                         \<run_dir\>/context/task_queue.json

  2\. Implement          Calls Claude with scoped context: task +
                         manifest + relevant interfaces + prior file
                         signatures only

  3\. Validate           Runs basic validation (syntax check, linting) on
                         the generated file

  4\. Write to Disk      If valid, writes to
                         \<run_dir\>/code/\<filename\>. Extracts the
                         public interface signature.

  5\. Update Manifest    Appends the new file\'s exported interface to
                         \<run_dir\>/context/shared_dependencies.md

  6\. Reset Context      Clears conversation history. The next task
                         starts completely fresh.

  7\. Pick Next Task     Returns to step 1 with the next item in the
                         queue
  ---------------------- ------------------------------------------------

Continuity between tasks lives in the filesystem (the run\'s context/
subfolder and code/ subfolder) --- not in the Coder\'s context window.
The Coder is stateless between tasks by design.

**Why a Single Agent?**

Multiple parallel Coder agents were considered and rejected. When
parallel agents write different files simultaneously, they cannot see
each other\'s code. They make different assumptions about variable
names, function signatures, and data structures. Merging the results
requires significant manual repair.

  ------------- ------------------------------------------------------------
  **The Key     A single Coder Agent with fresh context per task beats both
  Trade-off**   (1) a single agent with accumulated context across tasks AND
                (2) parallelized agents that create merge conflicts. The
                Architect owns task ordering. The Coder owns implementation.
                Fresh context per task is the correct solution to the 19%
                accuracy problem.

  ------------- ------------------------------------------------------------

**What the Coder Does NOT Receive**

This is as important as what it does receive. On each task invocation,
the Coder explicitly does not get:

-   The full project spec --- only the task description for the current
    file

-   Full source code of previously generated files --- only their
    exported signatures

-   Conversation history from prior tasks --- every task starts fresh

-   Raw critic feedback from prior revision cycles --- that arrives as a
    structured action list from the Synthesis Agent only

**Failure Escalation**

If a task fails validation 3 or more times, it does not keep retrying
with accumulated error context. The Coder is not allowed to spiral.
Instead:

-   The failed task is flagged back to the Architect

-   The Architect re-scopes or decomposes the task into smaller
    sub-tasks

-   The Coder receives a fresh, smaller task --- not a growing pile of
    error messages

This is a different failure mode from the revision loop (which handles
critic feedback). Escalation handles cases where the task specification
itself is the problem, not the implementation.

**The e2b Sandbox Connection**

Before the Critic Trio sees the code, the contents of the run\'s code/
subfolder are executed in an e2b sandbox. The runtime output --- stdout,
stderr, exit code --- is stored in state and passed to all three
critics. Critics reviewing code that has actually run produce
significantly better feedback than critics reviewing static code alone.

**Resources: Coder Agent**

[[Anthropic Python
SDK]{.underline}](https://github.com/anthropic/anthropic-sdk-python)

[[Anthropic: Messages API
Reference]{.underline}](https://docs.anthropic.com/en/api/messages)

[[e2b.dev Sandbox Documentation]{.underline}](https://e2b.dev/docs)

[[e2b Python SDK
Quickstart]{.underline}](https://e2b.dev/docs/quickstart/python)

[[Smol Developer (Ralph Loop
origin)]{.underline}](https://github.com/smol-ai/developer)

**Section 7: Critic Trio and DevOps Agent (Parallel Execution)**

+-----------------------------------------------------------------------+
| **📍 DIAGRAM FOCUS: Test Writer + Security Reviewer + Code Quality +  |
| DevOps Agent --- All Parallel**                                       |
|                                                                       |
| Four agents run simultaneously after the Coder finishes. Three        |
| critics independently review from different angles. The DevOps Agent  |
| works in parallel from the spec to produce infrastructure files. All  |
| outputs land in the run\'s reports/ subfolder (or are tracked in      |
| state for commit).                                                    |
+-----------------------------------------------------------------------+

**Context Isolation Across the Critics**

Parallelism is safe here precisely because these agents are independent.
But independence also means scoped context --- each critic receives only
what it needs:

  ------------------ -------------------------- --------------------------
  **Agent**          **Receives**               **Does NOT Receive**

  Test Writer        Code files from            Security findings, quality
                     \<run_dir\>/code/ +        notes, Dockerfile
                     interfaces +               
                     shared_deps_path + e2b     
                     output                     

  Security Reviewer  Code files +               Test files, quality notes,
                     shared_deps_path + env var e2b output
                     definitions                

  Code Quality Agent Code files + stable        Test files, security
                     context/CONVENTIONS.md     findings, DevOps config

  DevOps Agent       File tree of               Implementation source
                     \<run_dir\>/code/ +        code, any critic output
                     shared_deps_path +         
                     CONVENTIONS.md             
  ------------------ -------------------------- --------------------------

The DevOps Agent deliberately does not receive implementation source
code --- it works from the spec and file tree only, because its job
(Docker, CI/CD) is independent of how the code is implemented
internally.

**Test Writer Agent**

  ---------------------- ------------------------------------------------
  **Property**           **Detail**

  Model                  Claude Haiku

  Output                 Dict of {test_filename: test_code} written to
                         \<run_dir\>/code/tests/; feedback summary to
                         \<run_dir\>/reports/test_feedback.md

  Mindset                QA engineer trying to break the code. Red-team
                         the implementation.

  File                   agents/test_writer.py
  ---------------------- ------------------------------------------------

-   Happy path for each endpoint and function

-   Edge cases: empty inputs, None values, invalid types, boundary
    conditions

-   Error cases: invalid data, missing required fields, database
    unavailability

-   Runtime failures from e2b output --- specific tests targeting any
    observed errors

**Security Reviewer Agent**

  ---------------------- ------------------------------------------------
  **Property**           **Detail**

  Model                  Claude Haiku

  Output                 Report written to
                         \<run_dir\>/reports/security_report.md ---
                         \[{severity, issue, location, remediation}\]

  Mindset                OWASP Top 10 mindset. Assume the code will be
                         attacked.

  File                   agents/security_reviewer.py
  ---------------------- ------------------------------------------------

  ---------- ------------------------------------------------------------
  **OWASP    OWASP (Open Web Application Security Project) maintains the
  Top 10**   10 most critical web app security risks. The Security
             Reviewer\'s system prompt is built around this checklist:
             injection, broken auth, data exposure, security
             misconfiguration, hardcoded secrets, insecure direct object
             references.

  ---------- ------------------------------------------------------------

**Code Quality Agent**

  ---------------------- ------------------------------------------------
  **Property**           **Detail**

  Model                  Claude Haiku

  Output                 Report at \<run_dir\>/reports/quality_report.md
                         --- list of {category, issue, location,
                         suggestion}

  Mindset                Senior engineer doing a pull request review
                         before merging to main.

  File                   agents/code_quality.py
  ---------------------- ------------------------------------------------

-   PEP 8 violations (Python\'s official style guide)

-   Missing docstrings on public functions and classes

-   Functions longer than 50 lines that should be split

-   Missing type annotations, unhandled exceptions, magic numbers

**DevOps Agent**

  ---------------------- ------------------------------------------------
  **Property**           **Detail**

  Model                  Claude Sonnet --- DevOps config requires domain
                         knowledge

  Output                 Dockerfile, .github/workflows/ci.yml,
                         .env.example, docker-compose.yml written into
                         \<run_dir\>/code/

  Runs in parallel with  Critic Trio --- it does not depend on any review
                         results

  File                   agents/devops.py
  ---------------------- ------------------------------------------------

**Resources: Critics and DevOps**

[[LangGraph: Parallel Execution and the Send
API]{.underline}](https://langchain-ai.github.io/langgraph/how-tos/branching/)

[[OWASP Top 10]{.underline}](https://owasp.org/www-project-top-ten/)

[[OWASP API Security Top
10]{.underline}](https://owasp.org/www-project-api-security/)

[[pytest Documentation]{.underline}](https://docs.pytest.org/en/stable/)

[[Docker Multi-Stage
Builds]{.underline}](https://docs.docker.com/build/building/multi-stage/)

[[GitHub Actions
Documentation]{.underline}](https://docs.github.com/en/actions)

[[PEP 8 --- Python Style
Guide]{.underline}](https://peps.python.org/pep-0008/)

**Section 8: Synthesis Agent --- The Context Firewall**

+-----------------------------------------------------------------------+
| **📍 DIAGRAM FOCUS: Synthesis Agent + Conditional Edge (Revision      |
| Loop)**                                                               |
|                                                                       |
| The Synthesis Agent is the context firewall between the critics and   |
| any revision cycle. It receives three sets of feedback and produces   |
| one structured action list. On a revision pass, the Coder receives    |
| this action list --- not the raw critic output.                       |
+-----------------------------------------------------------------------+

**Why the Synthesis Agent Exists**

Without synthesis, the Coder on a revision pass would receive three
separate feedback streams, potentially contradicting each other, with
the same issue flagged in three different ways. The Synthesis Agent
resolves this:

-   Removes duplicate observations across all three critics

-   Resolves conflicts: security issues take priority over correctness,
    which takes priority over style

-   Produces a single prioritized action list: high_priority_fixes,
    medium_priority_fixes, low_priority_fixes

-   Sets has_critical_issues (bool) --- the single flag that drives the
    revision loop decision

  ---------------------- ------------------------------------------------
  **Property**           **Detail**

  Input                  Reads three critic reports from
                         \<run_dir\>/reports/ (test_feedback.md,
                         security_report.md, quality_report.md)

  Output                 Structured JSON in state; full report written to
                         \<run_dir\>/reports/SYNTHESIS_REPORT.md

  Model                  Claude Sonnet --- synthesis requires reasoning
                         to resolve conflicts across three formats

  File                   agents/synthesis.py

  State field            synthesis_report_path --- path to
                         SYNTHESIS_REPORT.md
  ---------------------- ------------------------------------------------

**The Revision Loop**

  ---------------------- ------------------------------------------------
  **Condition**          **Routing Decision**

  has_critical_issues =  Route back to Coder. Coder reads
  true AND               SYNTHESIS_REPORT.md from the run\'s reports/,
  revision_count \< 2    starts the Ralph Loop fresh with the action list
                         as additional context.

  has_critical_issues =  Route to output. Accept the current state,
  false OR               proceed to GitHub MCP.
  revision_count \>= 2   
  ---------------------- ------------------------------------------------

  -------------- ------------------------------------------------------------
  **Why Max 2    Infinite loops are a real risk. Critics will always find
  Revisions?**   something. Without a hard ceiling, a pipeline could loop
                 indefinitely, spending money and producing diminishing
                 returns. Two revisions handles genuinely critical issues.
                 Known limitations at that point get documented, not
                 infinitely chased.

  -------------- ------------------------------------------------------------

**GitHub MCP Integration**

After the pipeline resolves (post-revision-loop), a final node uses the
GitHub MCP server to create a real GitHub repository and push the
generated files.

Critical detail: the node reads from \<run_dir\>/code/ and strips the
code/ prefix before committing. Files land at the repo root. This is why
generated imports (like from models import User) work correctly in the
delivered repo --- a commit of code/models.py would break those imports.

Reports and runtime context (reports/ and context/ subfolders) are not
committed --- they\'re pipeline-internal artifacts.

  ----------------- ------------------------------------------------------------
  **PIPELINE_MODE   The GitHub MCP node must respect PIPELINE_MODE once
  Guard (planned)** implemented. In dry_run mode (default), it should log the
                    intended action and skip the actual repo creation. This
                    prevents the \'five real repos got created during an audit\'
                    failure mode.

  ----------------- ------------------------------------------------------------

  ---------- ------------------------------------------------------------
  **What is  MCP (Model Context Protocol) is a standard that lets Claude
  MCP?**     connect to external tools and services. Instead of writing
             GitHub API calls manually, you configure the GitHub MCP
             server and Claude knows how to create repos, commit files,
             and open pull requests --- just by describing what you want
             in the prompt.

  ---------- ------------------------------------------------------------

**Resources: Synthesis, Revision Loop, MCP**

[[LangGraph: Conditional Edges and
Routing]{.underline}](https://langchain-ai.github.io/langgraph/how-tos/routing/)

[[GitHub MCP
Server]{.underline}](https://github.com/modelcontextprotocol/servers/tree/main/src/github)

[[Model Context Protocol
Introduction]{.underline}](https://modelcontextprotocol.io/introduction)

[[Anthropic: Tool Use
Overview]{.underline}](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)

**Section 9: Phases 1B, 2, and 3 --- What Comes After**

Phase 1A is the foundation. The remaining phases build on it in order.

**Phase 1B: Harden, Test, and Secure**

+-----------------------------------------------------------------------+
| **Phase 1B Focus**                                                    |
|                                                                       |
| *The goal of Phase 1B is not to confirm the pipeline works --- it is  |
| to find every way it can break, and document the results.*            |
+-----------------------------------------------------------------------+

-   Testing: unit tests per agent (mocked API calls), integration tests
    for the full graph, edge case tests (empty brief, 5000-word brief,
    prompt injection attempt, SQL injection patterns)

-   Optimization: profile token usage per agent, confirm model
    assignments (Haiku vs Sonnet used where intended), measure and
    document actual cost per pipeline run

-   Security: audit prompts for injection risk, validate no secrets
    appear in logs, confirm e2b sandbox is truly isolated, verify GitHub
    PAT uses minimum required permissions only

-   Implement PIPELINE_MODE (dry_run default, live opt-in) and wire it
    into the GitHub node and any other write-side-effects

-   Audit fixtures: tests that mock writes should mock
    output/\<run_id\>/ paths, not the project-root context/

  ---------- ------------------------------------------------------------
  **Phase 1B You may not start Phase 2 until: test suite passes with
  Gate**     meaningful coverage, at least one non-obvious bug was found
             and fixed, cost per run is documented, PIPELINE_MODE is
             implemented, and PHASE_1B_SIGNOFF.md exists and has been
             committed.

  ---------- ------------------------------------------------------------

**Phase 2: Cloud Hosting**

+-----------------------------------------------------------------------+
| **Phase 2 Focus**                                                     |
|                                                                       |
| *Turn the local pipeline into a cloud-hosted API callable from        |
| anywhere --- including the Phase 3 iPhone app.*                       |
+-----------------------------------------------------------------------+

1.  Containerize with Docker --- the DevOps Agent already produced a
    Dockerfile; validate it runs locally first before touching cloud
    infrastructure

2.  Cost analysis --- before committing to a provider, estimate monthly
    cost at 10, 100, and 1000 runs/day for AWS, GCP, and Railway

3.  Expose as a REST API using FastAPI: POST /run-pipeline, GET
    /status/{job_id}, GET /result/{job_id} (returns the run_dir path or
    a zip of the run folder), GET /health

4.  Add API key authentication --- static key check, not JWT at this
    stage

5.  Deploy, configure structured logging, and set up alerting for
    failure rates

  ---------- ------------------------------------------------------------
  **Volume   In the container: mount output/ as a writable volume (or
  Mounts     back it with cloud storage). Mount context/ as read-only.
  Matter**   The stable/runtime split makes this trivial --- the boundary
             is a literal directory boundary. Also consider UUID suffixes
             on run folders to prevent collisions under concurrent API
             requests.

  ---------- ------------------------------------------------------------

**Phase 3: iPhone App**

+-----------------------------------------------------------------------+
| **Phase 3 Focus --- Learning Phase**                                  |
|                                                                       |
| *React Native with Expo. Skills transfer to Phase 4 web development.  |
| Build the smallest useful screen first, in this order.*               |
+-----------------------------------------------------------------------+

6.  API connection screen --- enter API URL and key, test connection,
    store credentials securely with Expo SecureStore (not AsyncStorage)

7.  Project brief submission --- multiline text input, submit to cloud
    API, receive job_id

8.  Progress tracking --- poll GET /status/{job_id} every 3 seconds,
    navigate automatically on completion

9.  Output display --- show GitHub URL, generated file list (the run\'s
    code/ subfolder maps cleanly to a file browser), synthesis report
    summary

10. End-to-end on a physical iPhone --- submit a real brief, receive a
    working repo

**Resources: Phases 1B, 2, and 3**

[[pytest Documentation]{.underline}](https://docs.pytest.org/en/stable/)

[[pytest-mock: Mocking for
pytest]{.underline}](https://pytest-mock.readthedocs.io/en/latest/)

[[FastAPI Documentation]{.underline}](https://fastapi.tiangolo.com/)

[[Docker Getting
Started]{.underline}](https://docs.docker.com/get-started/)

[[Railway --- Simple Cloud Hosting]{.underline}](https://railway.app/)

[[Expo: React Native Getting
Started]{.underline}](https://docs.expo.dev/get-started/introduction/)

[[React Native Official
Documentation]{.underline}](https://reactnative.dev/docs/getting-started)

**Section 10: Where to Start --- The Weekend MVP**

+-----------------------------------------------------------------------+
| **📍 DIAGRAM FOCUS: MVP Scope: Workspace → Coder (one task) → Critic  |
| → File Output**                                                       |
|                                                                       |
| The smallest version that proves the loop works. One Coder task, one  |
| Critic, file output into a proper run workspace. Even at this stage,  |
| the Coder should receive a scoped task --- not a full spec --- and    |
| writes should land in output/\<run_id\>/code/ to establish the right  |
| habits from the start.                                                |
+-----------------------------------------------------------------------+

The full pipeline is complex. Building it all at once is a path to
getting lost. The MVP has one goal: prove the loop works and that the
stable/runtime split and context isolation pattern are correctly
implemented.

  ---------------------- ------------------------------------------------
  **MVP Step**           **What You Build**

  MVP-01                 Define the shared LangGraph state schema
                         (state/schema.py) --- include run_dir and path
                         fields from the start

  MVP-02                 Build scripts/workspace.py + workspace_node ---
                         creates
                         output/\<run_id\>/{code,context,reports}/, seeds
                         manifest from template

  MVP-03                 Build a minimal Coder Agent --- receives a
                         single task description, writes to
                         \<run_dir\>/code/

  MVP-04                 Build a minimal Critic Agent --- reads a file
                         path, writes feedback to \<run_dir\>/reports/

  MVP-05                 Wire into a LangGraph graph: workspace → coder →
                         critic → END. Run it.

  MVP-06                 Run with a real brief, inspect the run folder,
                         document what worked and what didn\'t
  ---------------------- ------------------------------------------------

  ----------- ------------------------------------------------------------
  **The MVP   The MVP will produce imperfect code. That is fine. The point
  Mindset**   is: LangGraph runs, Claude responds, state stays small, the
              workspace folder structure materializes correctly, files
              land in the right subdirectories. If the MVP works with
              correct structure and context isolation, the architecture is
              proven.

  ----------- ------------------------------------------------------------

**Environment Setup --- Before Any Code**

-   Python 3.11+ via pyenv (do not use system Python; on Linux, use
    python3)

-   VS Code with Python extension, Pylance, Ruff linter, GitLens

-   GitHub repo with SSH auth, .gitignore configured to include output/

-   Python virtual environment (.venv), activated, in .gitignore

-   Core packages installed and pinned: langgraph, anthropic,
    python-dotenv, pydantic

-   .env file with ANTHROPIC_API_KEY --- triple-check it is in
    .gitignore

-   API key confirmed working with a 5-line test script before building
    anything

-   e2b account and API key configured (E2B_API_KEY in .env)

-   GitHub PAT with repo scope only (GITHUB_PAT in .env)

**Resources: Setup and Getting Started**

[[pyenv GitHub Repository]{.underline}](https://github.com/pyenv/pyenv)

[[VS Code Python
Extension]{.underline}](https://marketplace.visualstudio.com/items?itemName=ms-python.python)

[[Ruff Python
Linter]{.underline}](https://marketplace.visualstudio.com/items?itemName=charliermarsh.ruff)

[[Anthropic API Console]{.underline}](https://console.anthropic.com/)

[[Anthropic API
Quickstart]{.underline}](https://docs.anthropic.com/en/docs/quickstart)

[[LangGraph
Installation]{.underline}](https://langchain-ai.github.io/langgraph/concepts/)

[[Python venv --- Official
Docs]{.underline}](https://docs.python.org/3/library/venv.html)

[[python-dotenv
Documentation]{.underline}](https://saurabh-kumar.com/python-dotenv/)

**Section Summaries**

  ------------------ ----------------------------------------------------
  **Section**        **Key Takeaway**

  **1.               The core design principle --- minimal context,
  Introduction**     maximum precision --- is driven by a measurable
                     finding: single-function tasks achieve \~87%
                     accuracy while multi-file tasks with accumulated
                     context drop to \~19%. Every architecture decision
                     exists to prevent that drop. Three rules govern the
                     whole system: decompose before generating, isolate
                     by default, compress at boundaries.

  **2. Diagram**     The pipeline now shows a Workspace Node running
                     first to create a per-run output folder, the Ralph
                     Loop annotation on the Coder, the e2b sandbox as an
                     explicit step before critics, and a two-part output
                     layer: a per-run workspace (code, runtime context,
                     reports) and a stable read-only context/ directory.

  **3. LangGraph**   LangGraph manages state, nodes, and edges. State
                     holds paths to files inside the run\'s workspace ---
                     not file contents. The Send API creates isolated
                     state for parallel critic branches. Conditional
                     edges drive the revision loop. Path fields (run_dir,
                     shared_deps_path, task_queue_path, etc.) are set by
                     the workspace_node on pipeline start.

  **4. Context       Two distinct kinds of context files with opposite
  Management**       lifecycles. Stable context (project-root context/,
                     committed to git, human-authored) carries
                     conventions. Runtime context
                     (output/\<run_id\>/context/, gitignored,
                     agent-authored) carries per-run state. A
                     workspace_node creates the run folder and seeds the
                     manifest from a template. The GitHub MCP node strips
                     the code/ prefix on commit. PIPELINE_MODE is a
                     planned safeguard to fail safe on destructive
                     actions.

  **5. Spec          The Architect produces three artifacts --- all
  Clarifier &        written into the run\'s context/ subfolder:
  Architect**        shared_dependencies.md (seeded from template),
                     INTERFACES.py (C-header-style contracts), and
                     task_queue.json (topologically sorted). The Spec
                     Clarifier writes its output to disk and stores the
                     path in state, not the content.

  **6. Coder Agent** The Ralph Loop: pick task → implement → validate →
                     write to \<run_dir\>/code/ → extract interface →
                     append to \<run_dir\>/context/shared_dependencies.md
                     → reset context → repeat. Fresh context per task
                     solves the 19% problem. Failure escalation (3+
                     failures) routes to the Architect for task
                     re-scoping.

  **7. Critic Trio + Each critic receives scoped context matching its
  DevOps**           job. Reports are written to \<run_dir\>/reports/.
                     The DevOps Agent works from spec and file tree only.
                     Context isolation is the mechanism that makes
                     parallelism safe and output quality high.

  **8. Synthesis     The context firewall between critics and revision
  Agent**            cycles. Reads from \<run_dir\>/reports/ and writes
                     SYNTHESIS_REPORT.md there. has_critical_issues
                     drives the conditional routing. Max 2 revision
                     loops. GitHub MCP node strips the code/ prefix;
                     reports/ and context/ are not committed.

  **9. Phases        Phase 1B adds PIPELINE_MODE implementation as a gate
  1B/2/3**           requirement. Phase 2 benefits from the
                     stable/runtime split --- context/ mounts read-only,
                     output/ mounts writable. /result/{job_id} can return
                     a zip of the run folder. Phase 3 maps the code/
                     subfolder cleanly to a UI file browser.

  **10. Weekend      The starting point now includes the workspace node
  MVP**              from day one. Build scripts/workspace.py first, then
                     coder/critic that read and write inside \<run_dir\>.
                     Establishing the right folder structure from step
                     one is cheaper than retrofitting it later.
  ------------------ ----------------------------------------------------

+-----------------------------------------------------------------------+
| **Overall Project Summary**                                           |
|                                                                       |
| You are building a system where multiple specialized AI agents        |
| collaborate to turn a plain-English project description into a        |
| complete, production-ready codebase --- with tests, security review,  |
| Docker infrastructure, CI/CD configuration, and a live GitHub         |
| repository.                                                           |
|                                                                       |
| The architecture is governed by one empirical finding: context        |
| pollution --- not model capability --- is what causes AI code         |
| generation to fail. The 87%/19% accuracy gap between single-function  |
| and multi-file tasks is the design constraint that shapes everything. |
| Context files come in two flavors: stable conventions live in         |
| project-root context/ and are committed to git; runtime per-run state |
| lives in output/\<run_id\>/context/ and is gitignored. The Architect  |
| produces three artifacts into the run workspace; the Coder\'s Ralph   |
| Loop writes code into \<run_dir\>/code/ one file at a time; critics   |
| write reports into \<run_dir\>/reports/. The Synthesis Agent          |
| compresses three critics\' output into one action list before any     |
| revision cycle.                                                       |
|                                                                       |
| LangGraph orchestrates it all: conditional revision loops, parallel   |
| fan-out with the Send API, and a state object designed to hold file   |
| paths and compact logs. A workspace_node runs first to create the     |
| per-run folder structure. The GitHub MCP node strips the code/ prefix |
| when committing so delivered repos have correct imports.              |
| PIPELINE_MODE is a planned safeguard to make destructive actions      |
| opt-in. Claude Sonnet handles reasoning-heavy work. Claude Haiku      |
| handles review tasks at lower cost. MCP connects to GitHub. e2b       |
| ensures generated code actually runs before critics review it.        |
+-----------------------------------------------------------------------+
