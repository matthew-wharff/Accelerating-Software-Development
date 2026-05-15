"""GitHub PAT scope and failure-mode verification.

Confirms that ``GITHUB_PAT`` carries the minimum scopes the pipeline needs
(``repo`` only — see README) and nothing more, and that out-of-scope or
invalid-token failures surface as a clean ``BadCredentialsException``
rather than a hang.

Checks run:
    1. Scope inspection — read ``x-oauth-scopes`` from ``/user`` and compare
       against the allowlist and denylist.
    2. Token expiration — surface ``github-authentication-token-expiration``
       and warn if it is within 14 days.
    3. Out-of-scope probe — attempt ``DELETE /repos/<user>/__verify_nonexistent__``
       and ``PUT /orgs/__verify_bogus__/memberships/<user>``. With a
       correctly-scoped PAT (no ``delete_repo``, no ``admin:org``) both must
       return **403**. With an over-scoped PAT the resource layer answers
       first (404), which still proves the API responded but does NOT prove
       the scope is locked down — the script flags that explicitly.
    4. Invalid-token failure mode — initialize PyGithub with a bogus token and
       confirm the SDK raises ``BadCredentialsException(status=401)`` rather
       than hanging or returning silently. This is the same code path an
       expired PAT triggers mid-pipeline.

Exit code is non-zero if any required scope is missing, any forbidden scope is
present, or the invalid-token path does not raise the expected exception.

Run:
    source .venv/bin/activate
    python3 -m scripts.verify_github_pat_scope
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import github as gh  # noqa: E402

REQUIRED_SCOPES: frozenset[str] = frozenset({"repo"})
"""Scopes the pipeline actually needs. ``repo`` covers create/push/PR on
private repositories owned by the authenticated user."""

FORBIDDEN_SCOPES: frozenset[str] = frozenset(
    {
        "admin:enterprise",
        "admin:org",
        "admin:org_hook",
        "admin:public_key",
        "admin:repo_hook",
        "admin:ssh_signing_key",
        "delete_repo",
        "delete:packages",
        "site_admin",
        "workflow",
    }
)
"""Scopes the pipeline must NOT carry. Any one of these expands blast radius
beyond what ``run_github`` requires."""

API = "https://api.github.com"


@dataclass
class CheckResult:
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)


def _print_result(r: CheckResult) -> None:
    mark = "PASS" if r.passed else "FAIL"
    print(f"[{mark}] {r.name}")
    for line in r.details:
        print(f"       {line}")


def check_scopes(token: str) -> CheckResult:
    """Confirm the PAT carries exactly the required scopes and none of the forbidden ones."""
    resp = requests.get(
        f"{API}/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    raw = resp.headers.get("x-oauth-scopes", "")
    scopes = {s.strip() for s in raw.split(",") if s.strip()}

    missing = REQUIRED_SCOPES - scopes
    forbidden_present = scopes & FORBIDDEN_SCOPES

    details = [f"granted scopes: {sorted(scopes) or '(none)'}"]
    if missing:
        details.append(f"MISSING required: {sorted(missing)}")
    if forbidden_present:
        details.append(f"FORBIDDEN present: {sorted(forbidden_present)} — rotate PAT to repo-only")

    return CheckResult(
        name="scope inspection (allowlist=repo, deny admin/delete/workflow)",
        passed=not missing and not forbidden_present,
        details=details,
    )


def check_expiration(token: str) -> CheckResult:
    """Surface the PAT expiration date; warn if it is within 14 days."""
    resp = requests.get(
        f"{API}/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    exp_raw = resp.headers.get("github-authentication-token-expiration", "")
    if not exp_raw:
        return CheckResult(
            name="token expiration",
            passed=False,
            details=["no expiration header — PAT is non-expiring, which violates least-privilege"],
        )
    try:
        exp = datetime.strptime(exp_raw.strip(), "%Y-%m-%d %H:%M:%S %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return CheckResult(
            name="token expiration",
            passed=False,
            details=[f"could not parse expiration header: {exp_raw!r}"],
        )
    days_left = (exp - datetime.now(timezone.utc)).days
    return CheckResult(
        name="token expiration",
        passed=days_left > 14,
        details=[f"expires {exp.isoformat()} ({days_left} days)"],
    )


def check_out_of_scope_rejected(token: str, login: str) -> CheckResult:
    """Attempt two non-destructive out-of-scope actions; both must return 403 under a repo-only PAT.

    Targets are bogus on purpose — the calls cannot succeed even if the PAT is
    over-scoped (the named resources do not exist), so the only signal here is
    the HTTP status code GitHub chooses to return.
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    details: list[str] = []
    passed = True

    delete_resp = requests.delete(
        f"{API}/repos/{login}/__verify_nonexistent_repo__", headers=headers, timeout=10
    )
    details.append(
        f"DELETE /repos/{login}/__verify_nonexistent_repo__ -> {delete_resp.status_code}"
    )
    if delete_resp.status_code == 403:
        details.append("  delete_repo scope is correctly absent")
    elif delete_resp.status_code == 404:
        details.append(
            "  WARNING: 404 means the scope check passed and only the resource was missing — "
            "PAT may still have delete_repo. Re-run after rotation."
        )
        passed = False
    else:
        details.append(f"  UNEXPECTED status {delete_resp.status_code}")
        passed = False

    org_resp = requests.put(
        f"{API}/orgs/__verify_bogus_org__/memberships/{login}",
        headers=headers,
        json={"role": "member"},
        timeout=10,
    )
    details.append(
        f"PUT  /orgs/__verify_bogus_org__/memberships/{login} -> {org_resp.status_code}"
    )
    if org_resp.status_code == 403:
        details.append("  admin:org scope is correctly absent")
    elif org_resp.status_code == 404:
        details.append(
            "  WARNING: 404 means the scope check passed and only the resource was missing — "
            "PAT may still have admin:org. Re-run after rotation."
        )
        passed = False
    else:
        details.append(f"  UNEXPECTED status {org_resp.status_code}")
        passed = False

    return CheckResult(
        name="out-of-scope action rejected with 403",
        passed=passed,
        details=details,
    )


def check_invalid_token_fails_cleanly() -> CheckResult:
    """Confirm PyGithub raises ``BadCredentialsException`` on an expired/revoked token.

    This is the exact failure mode an expired PAT triggers mid-pipeline. The
    ``except Exception`` in ``graph.pipeline._github_node_live`` then converts
    it to ``status='failed'`` — graceful, not a hang.
    """
    bogus = gh.Github(auth=gh.Auth.Token("ghp_" + "x" * 36))
    try:
        bogus.get_user().login
    except gh.BadCredentialsException as e:
        return CheckResult(
            name="invalid/expired token raises BadCredentialsException",
            passed=e.status == 401,
            details=[f"status={e.status} message={e.data.get('message')!r}"],
        )
    except Exception as e:
        return CheckResult(
            name="invalid/expired token raises BadCredentialsException",
            passed=False,
            details=[f"raised {type(e).__name__} instead: {e}"],
        )
    return CheckResult(
        name="invalid/expired token raises BadCredentialsException",
        passed=False,
        details=["call returned without raising — auth not enforced"],
    )


def main() -> int:
    token = os.environ.get("GITHUB_PAT")
    if not token:
        print("FAIL: GITHUB_PAT not set in environment")
        return 2

    me = requests.get(
        f"{API}/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    if me.status_code != 200:
        print(f"FAIL: /user returned {me.status_code} — token is not valid")
        return 2
    login = me.json()["login"]
    print(f"Authenticated as: {login}\n")

    results = [
        check_scopes(token),
        check_expiration(token),
        check_out_of_scope_rejected(token, login),
        check_invalid_token_fails_cleanly(),
    ]
    for r in results:
        _print_result(r)

    failed = [r for r in results if not r.passed]
    print()
    if failed:
        print(f"SUMMARY: {len(failed)} of {len(results)} checks failed")
        return 1
    print(f"SUMMARY: all {len(results)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
