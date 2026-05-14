# Accelerating-Software-Development
A multi-agent pipeline that takes a software project brief and produces a working, scaffolded codebase with tests, security review, CI/CD config, and a GitHub repo.

## GitHub PAT — Minimum Permissions

The pipeline's GitHub agent ([agents/github_agent.py](agents/github_agent.py)) does exactly three things: create a repo, commit files to a branch, and open a PR. It needs one scope and nothing more.

### Required scope

- **`repo`** — full control of private repositories (create, push, open PRs).

That single scope covers the entire surface of [run_github()](agents/github_agent.py#L40): `user.create_repo`, `repo.create_git_ref`, `repo.create_file`, `repo.create_pull`. No other scope is read by the pipeline.

### Scopes that MUST be denied

| Scope | Why denied |
|---|---|
| `admin:org`, `admin:org_hook` | Pipeline never touches org settings. With this scope, a prompt-injected brief could add members, change visibility, or install hooks. |
| `delete_repo` | Pipeline only creates repos. With this scope, a compromised run could nuke an existing repo. |
| `admin:enterprise`, `site_admin` | Out of scope entirely — no enterprise APIs are called. |
| `admin:repo_hook` | Pipeline does not register webhooks. Removes a persistence vector. |
| `admin:public_key`, `admin:ssh_signing_key` | Pipeline does not manage keys. Removes a persistence vector. |
| `delete:packages` | Pipeline does not publish or delete packages. |
| `workflow` | Pipeline writes `ci.yml` as a regular file. GitHub triggers the resulting workflow itself; the PAT does not need to dispatch workflows. Only add this scope if you later have the agent call `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` directly. |

### Token expiration & rotation

- The PAT MUST have an expiration date. Non-expiring PATs are rejected by the verification script.
- A 90-day expiration is recommended. The verification script warns at 14 days remaining.
- Mid-pipeline expiration surfaces as a `github.BadCredentialsException` (HTTP 401) from PyGithub. [_github_node_live()](graph/pipeline.py#L774) catches it, logs the exception, and returns `{"status": "failed", "github_repo_url": None}`. The pipeline does **not** hang — the SDK does not retry on 401.

### Verifying the PAT

A re-runnable check is provided at [scripts/verify_github_pat_scope.py](scripts/verify_github_pat_scope.py):

```bash
source .venv/bin/activate
python3 -m scripts.verify_github_pat_scope
```

It performs four checks and exits non-zero on any failure:

1. **Scope inspection** — pulls `x-oauth-scopes` from `/user` and compares against the allowlist (`repo`) and denylist above.
2. **Expiration** — reads `github-authentication-token-expiration` and warns at <14 days.
3. **Out-of-scope rejection** — issues `DELETE /repos/<user>/__verify_nonexistent_repo__` and `PUT /orgs/__verify_bogus_org__/memberships/<user>`. With a correctly-scoped PAT both return **403** (scope check fails before resource lookup). A **404** means the PAT was permitted to attempt the action and only the named resource was missing — that's the over-scoped signal.
4. **Invalid-token failure mode** — initializes PyGithub with a bogus token and confirms `BadCredentialsException(status=401)` is raised, mirroring what happens when a real PAT expires mid-pipeline.

### Rotation playbook

1. Create a new classic PAT at <https://github.com/settings/tokens> with **only** the `repo` scope and a 90-day expiration.
2. Replace `GITHUB_PAT` in `.env` (never commit `.env`).
3. Run `python3 -m scripts.verify_github_pat_scope` — all four checks must pass.
4. Delete the old PAT in the GitHub UI.

## Other docs

- [CLAUDE.md](CLAUDE.md) — project conventions, pipeline architecture, model assignments.
- [SECURITY.md](SECURITY.md) — prompt-injection audit and PAT scope rationale.
- [SANDBOX_SECURITY_VERIFICATION.md](SANDBOX_SECURITY_VERIFICATION.md) — e2b sandbox isolation tests.
