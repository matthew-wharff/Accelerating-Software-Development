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
this document references a specific part of this diagram. Two changes
from a naive pipeline design are visible here: the Coder now shows \'one
task at a time\' with the Ralph Loop annotation, and the output layer
includes Stable Context Files on disk.

+-----------------------------------------------------------------------+
| **MULTI-AGENT DEV ASSISTANT --- FULL PIPELINE**                       |
+-----------------------------------------------------------------------+
|   ---------- -----                                                    |
| -- ----------- ------- ----------- ---------------------------------- |
|   **📋       **→**   **🔍 SPEC   **→**   **🏗️                         |
|   PROJECT            CLARIFIER           ARCHITECT                    |
|   BRIEF              Agent**             Agent**                      |
|   (User                                                               |
|   Input)**                                                            |
|                                                                       |
|   ---------- -----                                                    |
| -- ----------- ------- ----------- ---------------------------------- |
+-----------------------------------------------------------------------+
|   -------------                                                       |
| - -- ------------ -- ------------- ---------------------------------- |
|   *Project          *Clarified      *3 Artifacts:                     |
|   description*      brief*          Manifest                          |
|                                     Interfaces,                       |
|                                     Task Queue*                       |
|                                                                       |
|   -------------                                                       |
| - -- ------------ -- ------------- ---------------------------------- |
+-----------------------------------------------------------------------+
|   -                                                                   |
| ------------------- ------- ----------------------------------------- |
|                        **↓**                                          |
|                                                                       |
|   -                                                                   |
| ------------------- ------- ----------------------------------------- |
+-----------------------------------------------------------------------+
|                                                                       |
|  -------------------- --------------- -- ---------------------------- |
|                        **💻 CODER         *Ralph Loop: Pick task →    |
|                                                                       |
|                       Agent (1 Task      Implement → Validate → Write |
|                        at a Time)**       to disk → Reset context →   |
|                                           Pick next task*             |
|                                                                       |
|                                                                       |
|  -------------------- --------------- -- ---------------------------- |
+-----------------------------------------------------------------------+
|   ---------                                                           |
| ----------- ------- ------- -------------- -------------------------- |
|                        **↓**   **→**   **🐳 DEVOPS                    |
|                                        Agent                          |
|                                        (Dockerfile,                   |
|                                        CI/CD)**                       |
|                                                                       |
|   ---------                                                           |
| ----------- ------- ------- -------------- -------------------------- |
+-----------------------------------------------------------------------+
|   -------------------- --------------- ------------------------------ |
|                        **🔬 e2b                                       |
|                        SANDBOX                                        |
|                        (Execute &                                     |
|                        Capture                                        |
|                        Output)**                                      |
|                                                                       |
|   -------------------- --------------- ------------------------------ |
+-----------------------------------------------------------------------+
|   -------------------- --------------- ------------------------------ |
|                        *Runtime output                                |
|                        fed to critics*                                |
|                                                                       |
|   -------------------- --------------- ------------------------------ |
+-----------------------------------------------------------------------+
|   -                                                                   |
| ------------------- ------- ----------------------------------------- |
|                        **↓**                                          |
|                                                                       |
|   -                                                                   |
| ------------------- ------- ----------------------------------------- |
+-----------------------------------------------------------------------+
|   ---                                                                 |
| ----------------- ------------- -- ------------- -- ------------- --- |
|                                                                       |
|                      **🧪 TEST        **🔒 SECURITY    **✅ CODE      |
|                                                                       |
|                      WRITER           REVIEWER         QUALITY        |
|                                                                       |
|                      Agent**          Agent**          Agent**        |
|                                                                       |
|   ---                                                                 |
| ----------------- ------------- -- ------------- -- ------------- --- |
+-----------------------------------------------------------------------+
|   -------------------- ---------------------------------------------  |
|                        *← Critic Trio runs in parallel                |
|                        simultaneously →*                              |
|                                                                       |
|   -------------------- ---------------------------------------------  |
+-----------------------------------------------------------------------+
|   -                                                                   |
| ------------------------- ------- ----------------------------------- |
|                              **↓**                                    |
|                                                                       |
|   -                                                                   |
| ------------------------- ------- ----------------------------------- |
+-----------------------------------------------------------------------+
|   -------------------- --------------- ------------------------------ |
|                        **🧠 SYNTHESIS                                 |
|                        Agent (Context                                 |
|                        Firewall)**                                    |
|                                                                       |
|   -------------------- --------------- ------------------------------ |
+-----------------------------------------------------------------------+
|   --                                                                  |
| ------------------ ------- --------------- -------------------------- |
|                        **↓**   *Revision loop:                        |
|                                high-severity                          |
|                                issues route                           |
|                                back to Coder                          |
|                                with fresh                             |
|                                context (max                           |
|                                2x)*                                   |
|                                                                       |
|   --                                                                  |
| ------------------ ------- --------------- -------------------------- |
+-----------------------------------------------------------------------+
|   -                                                                   |
| ------------------- ------- ----------------------------------------- |
|                        **↓**                                          |
|                                                                       |
|   -                                                                   |
| ------------------- ------- ----------------------------------------- |
+-----------------------------------------------------------------------+
|                                                                       |
| -------------------- --------------- -- --------- -- --------- ------ |
|                        **📁 Generated     **🐙         **📄           |
|                        Code Files**       GitHub       Stable         |
|                                           Repo (via    Context        |
|                                           MCP)**       Files on       |
|                                                        Disk**         |
|                                                                       |
|                                                                       |
| -------------------- --------------- -- --------- -- --------- ------ |
+-----------------------------------------------------------------------+

**How to read this diagram:**

-   Each colored box is one agent (or input/output). The color indicates
    the type of work it does.

-   The Architect produces three artifacts (not one spec dump) that
    control how much context every downstream agent needs.

-   The Coder works through one task at a time with a fresh context
    window per task --- the Ralph Loop.

-   The Critic Trio and DevOps Agent all run simultaneously via
    LangGraph fan-out.

-   The Synthesis Agent acts as a context firewall between the critics
    and any revision --- it compresses three sets of feedback into one
    structured action list.

-   Stable Context Files live on disk and are injected into every agent
    invocation. They are the mechanism for shared knowledge without
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

  ---------------------- ------------------------------------------------
  **State Field**        **What It Contains**

  project_brief          The original project description you submitted

  clarified_brief        The brief after the Spec Clarifier asked its
                         questions

  architect_spec         The structured spec: tech stack, file structure,
                         API contracts

  task_queue             Ordered list of coding tasks from the Architect

  task_log               Compact completion log: {task_name, status,
                         file_path, interface_signature}

  generated_code         Dict of {filename: filepath_on_disk} --- paths
                         only, not content

  e2b_output             Runtime output from sandbox execution: {stdout,
                         stderr, exit_code}

  synthesis_report       De-duplicated, prioritized action list from the
                         Synthesis Agent

  devops_config          Dict of {filename: filepath_on_disk} for
                         Dockerfile, CI/CD config

  revision_count         How many revision loops have run (max: 2)

  status                 Current pipeline status: running, complete,
                         failed
  ---------------------- ------------------------------------------------

**2. Nodes**

A node is a Python function that takes the state as input and returns
updates to the state. Each agent is a node.

+-----------------------------------------------------------------------+
| \# Example: what a LangGraph node looks like                          |
|                                                                       |
| def coder_node(state: PipelineState) -\> dict:                        |
|                                                                       |
| \# Read the current task (not the full spec)                          |
|                                                                       |
| task = state\[\'task_queue\'\]\[0\]                                   |
|                                                                       |
| manifest = read_file(SHARED_DEPS_PATH) \# from disk                   |
|                                                                       |
| \# Call Claude with scoped context only                               |
|                                                                       |
| code = call_claude(task, manifest)                                    |
|                                                                       |
| \# Write code to disk, store only the path                            |
|                                                                       |
| path = write_to_disk(task.filename, code)                             |
|                                                                       |
| \# Return compact update, not the full code                           |
|                                                                       |
| return {\'task_log\': \[{\'task\': task.name, \'path\': path}\]}      |
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

-   The shared dependency manifest (CONVENTIONS.md and
    shared_dependencies.md from disk)

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
type definitions) and adds it to the dependency context available for
subsequent tasks. The full implementation goes to disk and is never
re-injected into context.

**Stable Context Files**

Three markdown files live at the project root and are injected into
every agent invocation. They survive context resets and carry knowledge
that would otherwise need to be re-derived on every call. The critical
rule is to keep them concise --- they consume context budget on every
invocation.

  ------------------------ ------------------------------------------------
  **File**                 **Contents and Purpose**

  CONVENTIONS.md           Coding standards, naming conventions, error
                           handling patterns, import style, formatting
                           rules. Equivalent to .cursorrules or CLAUDE.md.
                           Every agent gets this.

  shared_dependencies.md   The Architect\'s cross-file contract manifest.
                           Every shared type, exported function signature,
                           API contract, data schema, environment variable,
                           and DOM element ID used across files. Updated
                           after each coding task completes. This is the
                           cross-file coherence mechanism.

  ARCHITECTURE.md          High-level system overview, module boundaries,
                           data flow. Reference only --- not the full spec.
                           Keeps agents oriented without overwhelming them
                           with implementation detail.
  ------------------------ ------------------------------------------------

  -------------- ------------------------------------------------------------
  **Filesystem   Generated code, dependency manifests, and handoff reports
  as Shared      all live on disk. Agents read from disk rather than
  Memory**       receiving artifacts through LangGraph state. This keeps
                 state objects small, prevents context accumulation, and
                 means any agent can access any prior output without it being
                 injected into every context window.

  -------------- ------------------------------------------------------------

**Report-File Handoffs**

When one agent\'s output feeds another, the handoff is a structured
markdown report file --- not raw conversation history. For example, the
Synthesis Agent writes SYNTHESIS_REPORT.md, and the Coder on a revision
pass reads that file.

This pattern compresses context naturally. A 3000-token critic
conversation becomes a 200-token action list. The receiving agent starts
fresh with only the signal it needs.

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
| **📍 DIAGRAM FOCUS: Spec Clarifier Agent → Architect Agent**          |
|                                                                       |
| The two agents that run before any code is written. The Spec          |
| Clarifier eliminates brief ambiguity. The Architect converts the      |
| clarified brief into three specific artifacts that control how much   |
| context every downstream agent needs.                                 |
+-----------------------------------------------------------------------+

**The Spec Clarifier Agent**

Runs first. Asks 3--5 targeted questions that eliminate the most
important ambiguities in the brief. Good clarifying questions address
technical decisions that are hard to change later: authentication type,
database choice, API design, expected scale.

  ---------------------- ------------------------------------------------
  **Property**           **Detail**

  Input                  Raw project brief

  Output                 Structured dict of {question: answer} pairs that
                         all downstream agents reference

  Model                  Claude Sonnet

  File                   agents/spec_clarifier.py
  ---------------------- ------------------------------------------------

**The Architect Agent --- Three Required Artifacts**

The Architect is the most important context engineering component in the
system. Its job is not simply to write a spec --- it is to produce three
specific artifacts that collectively determine how much context every
downstream agent needs. These are not optional. They are the
architecture.

**Artifact 1: Shared Dependency Manifest (shared_dependencies.md)**

Every shared type, exported function signature, API contract, data
schema, environment variable, and DOM element ID used across more than
one file. This file travels with every Coder invocation as the
cross-file coherence mechanism.

The Coder uses it to know: what does the database layer export? What
type does the authentication function return? What environment variables
does the app expect? Without this manifest, the Coder guesses --- and
guesses accumulate into cross-file inconsistencies.

**Artifact 2: Interface Definitions**

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

**Artifact 3: Ordered Task Queue**

A topologically sorted list of file-level coding tasks derived from the
project\'s import and dependency graph. Files with zero external
dependencies are generated first. Files that depend on others come after
those dependencies exist.

Each task entry in the queue contains:

-   Target file path

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

  Input                  Clarified brief + answers from Spec Clarifier

  Output                 Three artifacts: shared_dependencies.md,
                         interface definitions, ordered task queue

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
| one task at a time with a fresh context window per task. This section |
| explains the Ralph Loop pattern, why single-agent design wins over    |
| parallelization, and how failure escalation works.                    |
+-----------------------------------------------------------------------+

**The Ralph Loop**

The Coder operates on a strict repeating cycle called the Ralph Loop.
The name comes from the pattern proven by Smol Developer. The cycle
enforces context isolation automatically:

  ---------------------- ------------------------------------------------
  **Ralph Loop Step**    **What Happens**

  1\. Pick Task          Reads the next task from the Architect\'s
                         ordered queue

  2\. Implement          Calls Claude with scoped context: task +
                         manifest + relevant interfaces + prior file
                         signatures only

  3\. Validate           Runs basic validation (syntax check, linting) on
                         the generated file

  4\. Write to Disk      If valid, writes the file to /output/. Extracts
                         the public interface signature.

  5\. Update Manifest    Adds the new file\'s exported interface to
                         shared_dependencies.md

  6\. Reset Context      Clears conversation history. The next task
                         starts completely fresh.

  7\. Pick Next Task     Returns to step 1 with the next item in the
                         queue
  ---------------------- ------------------------------------------------

Continuity between tasks lives in the filesystem and the Architect\'s
state --- not in the Coder\'s context window. The Coder is stateless
between tasks by design.

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

Before the Critic Trio sees the code, the full generated codebase is
executed in an e2b sandbox. The runtime output --- stdout, stderr, exit
code --- is stored in state and passed to all three critics. Critics
reviewing code that has actually run produce significantly better
feedback than critics reviewing static code alone.

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
| critics independently review from different angles --- each receiving |
| only the context relevant to its specific job. The DevOps Agent works |
| in parallel from the spec to produce infrastructure files.            |
+-----------------------------------------------------------------------+

**Context Isolation Across the Critics**

Parallelism is safe here precisely because these agents are independent.
But independence also means scoped context --- each critic receives only
what it needs:

  ------------------ -------------------------- --------------------------
  **Agent**          **Receives**               **Does NOT Receive**

  Test Writer        Implementation files +     Security findings, quality
                     interface defs + shared    notes, Dockerfile
                     dependency manifest + e2b  
                     output                     

  Security Reviewer  Implementation files +     Test files, quality notes,
                     dependency manifest +      e2b output
                     environment variable       
                     definitions                

  Code Quality Agent Implementation files +     Test files, security
                     project conventions        findings, DevOps config
                     (CONVENTIONS.md)           

  DevOps Agent       File tree + shared         Implementation source
                     dependency manifest +      code, any critic output
                     project conventions        
  ------------------ -------------------------- --------------------------

The DevOps Agent deliberately does not receive implementation source
code --- it works from the spec and file tree only, because its job
(Docker, CI/CD) is independent of how the code is implemented
internally.

**Test Writer Agent**

  ---------------------- ------------------------------------------------
  **Property**           **Detail**

  Model                  Claude Haiku

  Output                 Dict of {test_filename: test_code} --- pytest
                         unit and integration tests

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

  Output                 Structured list: \[{severity: high/medium/low,
                         issue, location, remediation}\]

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

  Output                 List of findings: {category, issue, location,
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
                         .env.example, docker-compose.yml

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

  Input                  test_feedback + security_feedback +
                         quality_feedback from state

  Output                 Structured JSON: {has_critical_issues: bool,
                         actions: \[{priority, issue, location,
                         action}\]}

  Model                  Claude Sonnet --- synthesis requires reasoning
                         to resolve conflicts across three formats

  File                   agents/synthesis.py

  Also writes            SYNTHESIS_REPORT.md to disk --- the handoff file
                         the Coder reads on a revision pass
  ---------------------- ------------------------------------------------

**The Revision Loop**

  ---------------------- ------------------------------------------------
  **Condition**          **Routing Decision**

  has_critical_issues =  Route back to Coder. Coder reads
  true AND               SYNTHESIS_REPORT.md, starts the Ralph Loop fresh
  revision_count \< 2    with the action list as additional context.

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
GitHub MCP server to create a real GitHub repository and push all
generated files.

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
    prompt injection attempt, SQL injection patterns in the brief)

-   Optimization: profile token usage per agent, confirm model
    assignments (Haiku vs Sonnet are used where intended), measure and
    document actual cost per pipeline run

-   Security: audit prompts for injection risk, validate no secrets
    appear in logs, confirm e2b sandbox is truly isolated, verify GitHub
    PAT uses minimum required permissions only

  ---------- ------------------------------------------------------------
  **Phase 1B You may not start Phase 2 until: test suite passes with
  Gate**     meaningful coverage, at least one non-obvious bug was found
             and fixed, cost per run is documented, and
             PHASE_1B_SIGNOFF.md exists and has been committed.

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
    /status/{job_id}, GET /result/{job_id}, GET /health

4.  Add API key authentication --- static key check, not JWT at this
    stage

5.  Deploy, configure structured logging, and set up alerting for
    failure rates

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

9.  Output display --- show GitHub URL, generated file list, synthesis
    report summary

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
| **📍 DIAGRAM FOCUS: MVP Scope: Brief → Coder (single task) → Critic → |
| File Output**                                                         |
|                                                                       |
| The smallest version that proves the loop works. One Coder task, one  |
| Critic, file output. Even at this stage, the Coder should receive a   |
| scoped task --- not a full spec --- to establish the right habit from |
| the start.                                                            |
+-----------------------------------------------------------------------+

The full pipeline is complex. Building it all at once is a path to
getting lost. The MVP has one goal: prove the loop works and that the
context isolation pattern is correctly implemented.

  ---------------------- ------------------------------------------------
  **MVP Step**           **What You Build**

  MVP-01                 Define the shared LangGraph state schema
                         (state/schema.py) --- paths not contents

  MVP-02                 Build a minimal Coder Agent --- receives a
                         single task description, returns one file\'s
                         code

  MVP-03                 Build a minimal Critic Agent --- takes code
                         string, returns feedback string

  MVP-04                 Wire both into a LangGraph graph: Coder → Critic
                         → Output. Run it.

  MVP-05                 Write generated code to disk in /output/. Coder
                         returns a filepath, not the code in state.

  MVP-06                 Run with a real brief, review output files,
                         document what worked and what didn\'t
  ---------------------- ------------------------------------------------

  ----------- ------------------------------------------------------------
  **The MVP   The MVP will produce imperfect code. That is fine. The point
  Mindset**   is: LangGraph runs, Claude responds, state stays small,
              files land on disk. If the MVP works with correct context
              isolation (scoped task, no accumulated history), the
              architecture is proven.

  ----------- ------------------------------------------------------------

**Environment Setup --- Before Any Code**

-   Python 3.11+ via pyenv (do not use system Python)

-   VS Code with Python extension, Pylance, Ruff linter, GitLens

-   GitHub repo with SSH auth, .gitignore configured

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

  **2. Diagram**     The updated pipeline adds: the Ralph Loop annotation
                     on the Coder, the e2b sandbox as an explicit step
                     before critics, \'one task at a time\' framing on
                     the Coder, and Stable Context Files as a distinct
                     output. The Architect\'s label now shows three
                     artifacts, not one spec.

  **3. LangGraph**   LangGraph manages state, nodes, and edges. The state
                     is intentionally lean: file paths not file contents,
                     compact task logs not conversation history. The Send
                     API creates isolated state for parallel critic
                     branches. Conditional edges drive the revision loop.

  **4. Context       A new dedicated section. Covers the three governing
  Management**       rules in detail, the Stable Context Files
                     (CONVENTIONS.md, shared_dependencies.md,
                     ARCHITECTURE.md), filesystem-as-shared-memory, and
                     report-file handoffs between agents. This is the
                     foundational section --- every other section
                     references back to it.

  **5. Spec          The Architect produces three specific artifacts ---
  Clarifier &        not one spec dump. The Shared Dependency Manifest is
  Architect**        the cross-file coherence mechanism. Interface
                     Definitions are generated first (before any
                     implementation), mirroring the C
                     header/implementation split. The Ordered Task Queue
                     is topologically sorted by dependency graph. The
                     Architect also runs a feedback loop after each
                     coding task.

  **6. Coder Agent** The Ralph Loop: pick task → implement → validate →
                     write to disk → extract interface → reset context →
                     repeat. Fresh context per task solves the 19%
                     problem. Failure escalation (3+ failures) routes to
                     the Architect for task re-scoping, not more Coder
                     retries. Explicit list of what the Coder does NOT
                     receive.

  **7. Critic Trio + Each critic receives scoped context matching its job
  DevOps**           --- not the full codebase. The DevOps Agent works
                     from spec and file tree only, not source code.
                     Context isolation is the mechanism that makes
                     parallelism safe and output quality high.

  **8. Synthesis     The context firewall between critics and revision
  Agent**            cycles. Compresses three feedback streams into one
                     structured action list via SYNTHESIS_REPORT.md on
                     disk. has_critical_issues drives the conditional
                     routing. Max 2 revision loops prevents infinite
                     cycling.

  **9. Phases        Phase 1B is a formal hardening gate --- no Phase 2
  1B/2/3**           until PHASE_1B_SIGNOFF.md exists. Phase 2
                     containerizes and hosts the pipeline as an
                     authenticated REST API. Phase 3 is a deliberate
                     React Native learning project, built screen by
                     screen from smallest to largest.

  **10. Weekend      The starting point. A single scoped Coder task, one
  MVP**              Critic, file output to disk. The MVP enforces
                     context isolation from the first line of code. If it
                     works --- small state, scoped context, files on disk
                     --- the architecture is proven and expansion can
                     begin.
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
| The Architect produces three artifacts (not one spec) to minimize     |
| each downstream agent\'s context. The Coder uses the Ralph Loop to    |
| work through one task at a time with a fresh context window. Stable   |
| Context Files on disk carry shared knowledge without accumulating     |
| history. The Synthesis Agent compresses three critics\' output into   |
| one action list before any revision cycle.                            |
|                                                                       |
| LangGraph orchestrates it all: conditional revision loops, parallel   |
| fan-out with the Send API, and a state object designed to hold file   |
| paths and compact logs --- not file contents and conversation         |
| history. Claude Sonnet handles reasoning-heavy work. Claude Haiku     |
| handles review tasks at lower cost. MCP connects to GitHub. e2b       |
| ensures generated code actually runs before critics review it.        |
+-----------------------------------------------------------------------+
