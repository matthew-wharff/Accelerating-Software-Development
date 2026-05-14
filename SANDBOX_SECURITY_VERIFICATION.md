# e2b Sandbox Security Verification

Verification run for the e2b sandbox used by [`graph/pipeline.py:656`](graph/pipeline.py#L656) (`e2b_node`).
This document captures the configuration under test, the four required isolation checks, and the results.

Last run: 2026-05-13 (after egress block landed).
Harness: [`scripts/verify_sandbox_security.py`](scripts/verify_sandbox_security.py) — re-runnable via `python3 scripts/verify_sandbox_security.py` from the project root with the venv active.

## Verdict

| # | Check | Result |
|---|---|---|
| 1 | Network isolation | **PASS** — outbound HTTP fails (DNS resolution fails inside the user-code netns) |
| 2 | Filesystem isolation | PASS |
| 3 | Resource limits / timeout | PASS |
| 4 | Malicious code (`rm -rf /`) | PASS |

**Phase 2 is cleared.** All four containment properties hold. The egress block is implemented at the per-command wrapper layer (`scripts.sandbox.wrap_user_command`) and gated by the `SANDBOX_BLOCK_EGRESS` env var (default `true`). The earlier failure of test 1 — recorded below for posterity — is resolved.

## Sandbox configuration under test

This is what the pipeline now uses in `e2b_node`:

```python
from e2b_code_interpreter import Sandbox
from scripts.sandbox import wrap_user_command

sandbox = Sandbox.create(timeout=30, api_key=config.E2B_API_KEY)
result = sandbox.commands.run(
    wrap_user_command("cd /home/user && python3 main.py"),
    timeout=30,
)
```

`wrap_user_command` produces `sudo -n unshare -n -- runuser user -c '...'` when `config.SANDBOX_BLOCK_EGRESS` is True (the default), so the inner command executes inside a fresh network namespace with only a loopback interface. envd (the e2b control-plane daemon) runs as root *outside* the netns, so `commands.run` and `files.write` keep working.

Resolved properties:

- **SDK:** `e2b==2.20.0`, `e2b-code-interpreter==2.6.0` (from `requirements.txt`).
- **Template:** default `code-interpreter` base template (no custom template; no `--cpu-count` / `--memory-mb` override).
- **CPU / memory:** e2b defaults for the base template (the project has not opted into custom compute via `e2b template build`).
- **Sandbox lifetime cap:** 30 s (`Sandbox.create(timeout=30)`). Per [e2b timeout docs](https://e2b.dev/docs/legacy/sandbox/api/timeouts) the SDK default is 300 s; the project tightens that to 30 s.
- **Per-command timeout:** 30 s (`commands.run(..., timeout=30)`).
- **Effective uid inside sandbox:** `1000` (non-root) — confirmed at runtime.
- **Network egress policy:** the e2b platform itself permits unrestricted egress; the *project* now restricts it via the per-command netns wrapper. Set `SANDBOX_BLOCK_EGRESS=false` to opt out (e.g. when generated code needs `pip install` during execution).
- **Host boundary:** each sandbox runs in its own [Firecracker microVM](https://e2b.dev/blog/firecracker-vs-qemu) with a dedicated minimal kernel ([e2b's CVE-2026-31431 write-up](https://e2b.dev/blog/not-affected-by-copy-fail-heres-why)). Kernel, memory, page cache, and filesystem are not shared with the host.

## Documentation summary (what the platform guarantees)

The three URLs in the task brief return 404 on the current docs site; the live equivalents and the e2b engineering blog were used instead.

- **Isolation architecture** ([blog: Firecracker vs QEMU](https://e2b.dev/blog/firecracker-vs-qemu), [blog: not affected by Copy Fail](https://e2b.dev/blog/not-affected-by-copy-fail-heres-why)): every sandbox is a dedicated Firecracker microVM with its own kernel, memory, and page cache. There is no shared kernel surface between sandbox and host, so a kernel-level RCE inside the sandbox does not reach the host without an additional Firecracker escape vulnerability.
- **Timeouts** ([docs](https://e2b.dev/docs/legacy/sandbox/api/timeouts)): SDK default 300 s; max sandbox lifetime 1 h (Hobby) / 24 h (Pro). Configured via `Sandbox.create(timeout=...)` and mutable at runtime via `sandbox.set_timeout(...)`. `commands.run(..., timeout=...)` is a separate per-command cap.
- **Compute** ([docs](https://e2b.dev/docs/sandbox-template/customize-cpu-ram), [blog](https://e2b.dev/blog/customize-sandbox-compute)): CPU and RAM are baked into the *template* at build time via the CLI (`e2b template build --cpu-count N --memory-mb N`). Pro users can pick CPU ∈ {1, 2, 4, 6, 8} and RAM ∈ [512, 8192] MiB (even values). The base template the project uses has not been customised.
- **Network policy:** the docs do not describe a sandbox-side egress firewall. Network restriction is the caller's responsibility (see "Required action" below).

## Test methodology and raw results

The harness creates one sandbox with the production configuration, runs all four checks against it, then kills the sandbox. A host-side canary file under `/tmp` is created before the destructive test and verified afterwards.

### 1. Network isolation — PASS

The harness runs the same Python `urllib.request.urlopen('https://example.com')` snippet, but routed through `wrap_user_command(...)`, so the effective command is:

```
sudo -n unshare -n -- runuser user -c 'python3 -c "import urllib.request, ...; r = urllib.request.urlopen(\"https://example.com\"); ..."'
```

Result: exit code 1, with `socket.gaierror: [Errno -3] Temporary failure in name resolution`. The empty netns has only a loopback interface (DOWN), so DNS and IP egress both fail.

**Interpretation.** Generated code cannot make outbound network calls. The same `commands.run` invocation from outside the wrapper (e.g. internal pipeline orchestration) still has network — only user code is isolated.

**Why not iptables.** The first attempt used `iptables -m owner --uid-owner 1000 -j REJECT`, which is the textbook way to block egress per-user. The e2b minimal kernel does not include the `xt_owner` extension, so the rule fails with `Warning: Extension owner revision 0 not supported, missing kernel module?`. A blanket `OUTPUT -j REJECT` would have worked but also killed envd's reply path back to the host, breaking the control plane. The netns wrapper sidesteps both problems: envd runs as root outside the namespace, user code runs inside it.

#### Earlier (pre-fix) result, kept for posterity

Without the wrapper, the same urllib call returned `HTTP 200 528 bytes` (exit code 0). That was the default e2b posture: the platform leaves egress open and expects callers to layer their own policy. The fix in [`scripts/sandbox.py`](scripts/sandbox.py) and [`graph/pipeline.py:e2b_node`](graph/pipeline.py#L656) is that layer.

### 2. Filesystem isolation — PASS

- Write to `/etc/sandbox_breakout_test` from inside the sandbox: exit code 1, `PermissionError`. Sandbox effective uid is `1000`, so the regular Unix discretionary ACL stopped the write — no special restriction beyond that, which is fine because the host filesystem is unreachable regardless.
- Wrote a uuid-named sentinel inside the sandbox at `/home/user/sandbox_isolation_<uuid>.txt`. After the test, the host's `/` and `/tmp` were checked for that filename — not present in either location.

**Interpretation.** The microVM has its own filesystem. Nothing the sandbox writes is visible on the host. (Inside the sandbox the model still has full write access to `/home/user/` and to anywhere `uid=1000` can write, which is the intended behavior.)

### 3. Resource limits — PASS

Invoked `sleep 120` with `commands.run(..., timeout=5)`. Elapsed wall time was 5.1 s; the SDK raised `ReadTimeout` and the command was terminated.

The 30 s sandbox lifetime cap from `Sandbox.create(timeout=30)` matches what `e2b_node` uses in production. The base template's CPU/memory defaults apply; this project has not built a custom template, so no `--cpu-count` / `--memory-mb` override is in effect.

### 4. Malicious code (`rm -rf /`) — PASS

Inside the sandbox: `os.system('rm -rf / --no-preserve-root 2>/dev/null')` followed by a `print('post-rm')`. The command returned exit code 0 and `post-rm` was printed (the sandbox was demolishing itself in parallel with the print). After the sandbox was killed:

- Host canary at `/tmp/host_canary_<uuid>.txt` still present, contents byte-identical to pre-test.
- Project root at `/home/dev-projects/Repos/Accelerating-Software-Development/` and `CLAUDE.md` both intact.

**Interpretation.** The destructive command stayed inside the microVM. The host is untouched.

## Known limitations of this fix

- **Generated code cannot use the network during execution.** No `pip install`, no API calls, no fetching remote data. If a future task needs that, set `SANDBOX_BLOCK_EGRESS=false` for that run; pre-install dependencies in a custom template instead.
- **Wrapper scope.** Only the entrypoint command in `e2b_node` is wrapped. If you add other `sandbox.commands.run(...)` call sites that execute generated code, route them through `wrap_user_command` too.
- **Not a defense against template tampering.** This fix relies on the base template's `unshare` binary and passwordless sudo. A future custom template would be a more durable place to encode the policy.

## Reproducing this

```bash
source .venv/bin/activate
python3 scripts/verify_sandbox_security.py
```

The harness exits non-zero if any check regresses. Re-run after any change to the sandbox configuration in `e2b_node`, after switching to a custom template, or after upgrading the `e2b-code-interpreter` SDK.
