"""Sandbox runtime helpers shared by the pipeline and the security harness.

The e2b base template grants passwordless ``sudo`` to ``uid=1000`` ("user").
When ``config.SANDBOX_BLOCK_EGRESS`` is True (the default) we wrap user-code
execution in ``sudo -n unshare -n -- runuser user -c '...'`` so the command
runs inside a fresh network namespace that only has a loopback interface.
This blocks all outbound traffic (including DNS) without breaking the e2b
control plane, which runs as root outside the netns.

Kernel-module reminder: the e2b minimal kernel does not include ``xt_owner``,
so iptables-based ``-m owner --uid-owner`` rules fail with "missing kernel
module". The netns approach avoids that constraint entirely.
"""

from __future__ import annotations

import config


def wrap_user_command(cmd: str) -> str:
    """Return ``cmd`` wrapped for execution as the sandbox ``user`` account.

    When ``SANDBOX_BLOCK_EGRESS`` is enabled, the wrapping isolates the
    command in a fresh network namespace; otherwise it is returned unchanged
    (e2b already runs ``commands.run`` as uid 1000).

    Args:
        cmd: Shell snippet to execute inside the sandbox.

    Returns:
        The wrapped command string suitable for ``sandbox.commands.run``.
    """
    if not config.SANDBOX_BLOCK_EGRESS:
        return cmd
    escaped = cmd.replace("'", "'\\''")
    return f"sudo -n unshare -n -- runuser user -c '{escaped}'"
