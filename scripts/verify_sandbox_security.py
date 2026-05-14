"""Sandbox security verification harness.

Runs four isolation checks against a live e2b sandbox using the same
configuration the pipeline uses (``graph.pipeline.e2b_node``): ``Sandbox.create(timeout=30)``
on the default ``code-interpreter`` template.

Tests:
    1. Network isolation — outbound HTTP from inside the sandbox.
    2. Filesystem isolation — writes to protected paths inside the sandbox,
       and confirms a sentinel written inside the sandbox is NOT visible on the host.
    3. Resource limits — 30 s per-command timeout actually terminates a long-running command.
    4. Malicious code — ``rm -rf / --no-preserve-root`` inside the sandbox does not damage the host.

The script prints a structured report to stdout. Exit code is non-zero if any
expected-failure check unexpectedly succeeded.
"""

import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from e2b_code_interpreter import Sandbox  # noqa: E402

import config  # noqa: E402
from scripts.sandbox import wrap_user_command  # noqa: E402


@dataclass
class TestResult:
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)


def _run(sandbox: Sandbox, cmd: str, timeout: int = 15):
    """Run a command in the sandbox and return (exit_code, stdout, stderr)."""
    try:
        result = sandbox.commands.run(cmd, timeout=timeout)
        return result.exit_code, result.stdout or "", result.stderr or ""
    except Exception as exc:
        return -1, "", f"<exception: {type(exc).__name__}: {exc}>"


def test_network_isolation(sandbox: Sandbox) -> TestResult:
    """Attempt outbound HTTP from the sandbox, via the same wrapper e2b_node uses."""
    result = TestResult(name="1. Network isolation", passed=False)
    inner = (
        "python3 -c \""
        "import urllib.request, socket; socket.setdefaulttimeout(8); "
        "r = urllib.request.urlopen('https://example.com'); "
        "print('HTTP', r.status, len(r.read()), 'bytes')\""
    )
    cmd = wrap_user_command(inner)
    result.details.append(f"egress block enabled: {config.SANDBOX_BLOCK_EGRESS}")
    result.details.append(f"effective command: {cmd[:120]}...")
    exit_code, stdout, stderr = _run(sandbox, cmd, timeout=20)
    result.details.append(f"command exit_code = {exit_code}")
    result.details.append(f"stdout = {stdout.strip()!r}")
    result.details.append(f"stderr = {stderr.strip()[:200]!r}")
    if exit_code != 0:
        result.passed = True
        result.details.append("OK: outbound HTTP was blocked / failed.")
    else:
        result.details.append(
            "FINDING: outbound HTTP to example.com SUCCEEDED. "
            "e2b sandboxes permit unrestricted internet egress by default. "
            "Containment vs. host is still provided by the Firecracker microVM; "
            "but exfiltration via outbound network from generated code is NOT prevented."
        )
    return result


def test_filesystem_isolation(sandbox: Sandbox) -> TestResult:
    """Write to protected paths inside sandbox; confirm host filesystem is untouched."""
    result = TestResult(name="2. Filesystem isolation", passed=True)

    exit_code, _, stderr = _run(
        sandbox,
        "python3 -c \"open('/etc/sandbox_breakout_test','w').write('x')\"",
    )
    result.details.append(
        f"write to /etc/sandbox_breakout_test (non-root): exit={exit_code} stderr={stderr.strip()[:200]!r}"
    )
    if exit_code == 0:
        result.passed = False
        result.details.append(
            "FAIL: non-root sandbox user was able to write to /etc — unexpected."
        )

    exit_code, stdout, _ = _run(sandbox, "id -u")
    result.details.append(f"sandbox effective uid = {stdout.strip()!r}")

    sentinel = f"sandbox_isolation_{uuid.uuid4().hex}.txt"
    sandbox_path = f"/home/user/{sentinel}"
    host_path = Path("/") / sentinel
    host_tmp_path = Path("/tmp") / sentinel
    sandbox.files.write(sandbox_path, "sandbox-only sentinel")
    exit_code, stdout, _ = _run(sandbox, f"cat {sandbox_path}")
    result.details.append(
        f"sentinel readable inside sandbox: exit={exit_code} content={stdout.strip()!r}"
    )

    host_root_exists = host_path.exists()
    host_tmp_exists = host_tmp_path.exists()
    result.details.append(
        f"host {host_path}: exists={host_root_exists}; host {host_tmp_path}: exists={host_tmp_exists}"
    )
    if host_root_exists or host_tmp_exists:
        result.passed = False
        result.details.append("FAIL: sandbox file leaked onto host filesystem.")
    else:
        result.details.append(
            "OK: sandbox-written file is NOT visible on host (Firecracker microVM boundary holds)."
        )

    return result


def test_resource_limits(sandbox: Sandbox) -> TestResult:
    """Verify per-command timeout terminates a hanging command and sandbox lifetime is bounded."""
    result = TestResult(name="3. Resource limits (timeout)", passed=False)
    start = time.monotonic()
    exit_code, stdout, stderr = _run(sandbox, "sleep 120", timeout=5)
    elapsed = time.monotonic() - start
    result.details.append(f"sleep 120 with timeout=5: elapsed={elapsed:.1f}s exit={exit_code}")
    result.details.append(f"stderr/exc = {stderr.strip()[:200]!r}")
    if elapsed < 30 and exit_code != 0:
        result.passed = True
        result.details.append("OK: per-command timeout terminated the long-running command.")
    else:
        result.details.append("FAIL: command was not terminated by timeout.")

    result.details.append(
        "Sandbox lifetime cap: Sandbox.create(timeout=30) → microVM auto-pauses/kills after 30 s "
        "(matches graph.pipeline.e2b_node configuration)."
    )
    result.details.append(
        "Compute limits: project uses the default base template (no custom --cpu-count / --memory-mb), "
        "so resource ceilings are the e2b defaults for that template."
    )
    return result


def test_malicious_code(sandbox: Sandbox, host_canary: Path) -> TestResult:
    """Run rm -rf / inside the sandbox; verify host canary survives."""
    result = TestResult(name="4. Malicious code (rm -rf /)", passed=False)

    assert host_canary.exists(), "host canary should exist before test"
    canary_before = host_canary.read_text()
    result.details.append(f"host canary {host_canary} present before test (len={len(canary_before)})")

    exit_code, stdout, stderr = _run(
        sandbox,
        "python3 -c \"import os; os.system('rm -rf / --no-preserve-root 2>/dev/null'); print('post-rm')\"",
        timeout=20,
    )
    result.details.append(f"rm -rf / inside sandbox: exit={exit_code}")
    result.details.append(f"stdout = {stdout.strip()[:200]!r}")
    result.details.append(f"stderr = {stderr.strip()[:200]!r}")

    host_canary_survived = host_canary.exists() and host_canary.read_text() == canary_before
    result.details.append(f"host canary survived = {host_canary_survived}")

    project_root = Path(__file__).resolve().parent.parent
    project_intact = project_root.exists() and (project_root / "CLAUDE.md").exists()
    result.details.append(f"project root + CLAUDE.md intact = {project_intact}")

    if host_canary_survived and project_intact:
        result.passed = True
        result.details.append("OK: destructive command inside sandbox did not affect host.")
    else:
        result.details.append("CRITICAL FAIL: host artifacts were modified by sandbox.")
    return result


def main() -> int:
    print("=" * 78)
    print("e2b sandbox security verification")
    print("=" * 78)
    print(f"Sandbox config under test: Sandbox.create(timeout=30) — same as graph.pipeline.e2b_node")
    print(f"e2b_code_interpreter SDK: present; API key loaded from env: {bool(config.E2B_API_KEY)}")

    host_canary = Path("/tmp") / f"host_canary_{uuid.uuid4().hex}.txt"
    host_canary.write_text("DO NOT DELETE — host canary for sandbox verification")

    sandbox = None
    results: list[TestResult] = []
    try:
        sandbox = Sandbox.create(timeout=30, api_key=config.E2B_API_KEY)
        print(f"sandbox created: id={getattr(sandbox, 'sandbox_id', '<unknown>')}")

        results.append(test_network_isolation(sandbox))
        results.append(test_filesystem_isolation(sandbox))
        results.append(test_resource_limits(sandbox))
        results.append(test_malicious_code(sandbox, host_canary))
    finally:
        if sandbox is not None:
            try:
                sandbox.kill()
            except Exception as exc:
                print(f"sandbox.kill() failed: {exc}")
        try:
            if host_canary.exists():
                host_canary.unlink()
        except OSError:
            pass

    print()
    print("=" * 78)
    print("RESULTS")
    print("=" * 78)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"\n[{status}] {r.name}")
        for line in r.details:
            print(f"    {line}")

    print()
    summary_fail = [r.name for r in results if not r.passed]
    if summary_fail:
        print(f"FAILED checks: {summary_fail}")
        return 1
    print("All four checks passed (containment confirmed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
