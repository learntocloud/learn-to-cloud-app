---
name: ship-it
description: Run the quality gate (lint, type-check, tests), resolve issues, commit, push, open a PR to main, then monitor the deploy workflow after merge and resolve any deploy failures. Use when user says "ship it", "commit and deploy", "push and deploy", or "land this".
---

# Ship It: Quality Gate, Commit, Push & Monitor Deploy

**Run the steps in order. Do not skip steps. Surface git and CI errors to the user instead of forcing past them.**

---

## Prerequisites

- `gh` CLI authenticated. Check with `gh auth status` at the very start (see Step 1).
- `git` configured with push access to the remote
- Workspace dependencies installed (`uv sync --all-packages --locked`), which provides the `poe` and `prek` dev tools
- Working directory is inside the repository

---

## Step 0: Match User's Energy

Reply with "LFG 🚀 I'll ship it" to acknowledge the user's intent.

---

## Step 1: Confirm Branch and GitHub Auth

Capture the current branch into a variable so later commands are copy-pasteable, and confirm `gh` is authenticated before doing anything that depends on it.

```bash
branch=$(git branch --show-current)
echo "On branch: $branch"
gh auth status || echo "gh NOT authenticated, deploy monitoring will be skipped"
```

- Never commit on `main`. If `$branch` is `main`, stop and ask the user for a feature branch name first.
- If `gh` is not authenticated, you can still run checks, commit, push, and open a PR through the web link, but you will not be able to monitor the deploy run from here. Tell the user this up front.

---

## Step 2: Run the Quality Gate

Stage everything first, then run the full quality gate. `uv run poe check` is a
sequence of three tasks:

1. `static` — `prek run --all-files`: ruff lint, ruff format, ty type check,
   migration SQL safety lint, docs link check, file hygiene.
2. `package-smoke` — builds the `learn-to-cloud-shared` wheel, installs it into
   a throwaway venv, and runs `learn_to_cloud_shared.runtime_package_check`.
3. `test` — pytest with coverage for `api` and
   `packages/learn-to-cloud-shared`, plus the `apps/verification-functions`
   suite.

```bash
cd <workspace>
git add -A
uv run poe check
```

### `poe check` is necessary but not sufficient for CI

CI's `ci` job runs `poe static`, `poe package-smoke`, and `poe test`, but also
several checks that have no local poe task. A green `poe check` can still hit a
red CI. Run the relevant ones yourself when your change touches their inputs:

| CI step | Command | Run it when you touched |
|---------|---------|-------------------------|
| Curriculum content integrity | `cd packages/learn-to-cloud-shared && uv run python scripts/validate_content.py` | curriculum content YAML |
| YAML JSON schema drift | `cd packages/learn-to-cloud-shared && uv run python scripts/generate_yaml_schemas.py` then confirm `git diff --exit-code src/learn_to_cloud_shared/content/schemas/` is clean | content Pydantic models |
| `curriculum.json` artifact drift | regenerate the artifact and commit it | curriculum content or artifact schema |
| Single migration head | `cd api && uv run alembic heads` shows exactly one head | Alembic migrations |
| Migration naming/docstrings | `cd api && uv run python scripts/check_migration_naming.py` | Alembic migrations |
| Migrations apply + model sync | `cd api && uv run alembic upgrade head && uv run alembic check` | models or migrations |

Terraform changes are gated by the separate `terraform-ci` job (`terraform fmt
-check -recursive`, `validate`, `terraform test`), and dependency changes by
`dependency-review`. Neither is covered by `poe check`.

> Stage files first (`git add -A`). The static checks run `prek run --all-files`,
> which only inspects git-tracked files, so newly-created files (new migrations,
> modules, tests) are silently skipped unless staged.

### Handling Failures

Many static hooks auto-fix in place (ruff lint `--fix`, ruff format, trailing
whitespace, end-of-file). If `uv run poe check` fails:

1. Read the failure output and fix the cause (lint, types, a failing test,
   malformed YAML/JSON, large file, merge-conflict markers). Never silence a
   failure with `# noqa` or `type: ignore`.
2. If hooks auto-fixed files, `git add -A` again.
3. Re-run `uv run poe check` until it passes cleanly.

**Do NOT proceed to commit until `uv run poe check` passes. No exceptions.**

---

## Step 3: Stage and Commit

Stage everything (`ship it` means ship all changes, never cherry-pick), review, then commit.

```bash
git add -A
git diff --cached --stat
```

Use the user's commit message if given; otherwise write a conventional-commit message (`feat:`, `fix:`, `refactor:`, `docs:`, `style:`, `test:`, `chore:`). Include the repo's trailer unless the user opts out. Ask the user if the intent is ambiguous.

```bash
git commit -m "<type>: <concise description>" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Step 4: Push and Open a PR

```bash
git push -u origin "$branch"
```

**If the push is rejected (remote has commits you don't):** do NOT auto-rebase or force-push. Try only a safe fast-forward, and if that fails, stop and surface the situation to the user:

```bash
git pull --ff-only || {
  echo "Remote and local have diverged. Stopping."
  git status -sb
  git log --oneline --left-right --graph "@{u}"...HEAD
}
```

Rebasing rewrites history and can introduce conflicts that need human judgment, so let the user decide how to reconcile before pushing again.

If the branch is not `main`, open a PR to `main`:

```bash
gh pr create --fill --base main --head "$branch"
```

Then watch the PR's own checks (CI, terraform-ci, dependency-review). These run on the `pull_request` event but do NOT deploy:

```bash
gh pr checks "$branch" --watch --fail-fast
```

**Merging is a separate, explicit decision.** Deploy only happens after the PR merges to `main`, and branch protection may require a human review, so do not assume you can merge. If the user wants to merge and it is allowed:

```bash
gh pr merge "$branch" --squash --auto --delete-branch
```

**Note**: The `deploy.yml` deploy jobs are gated to `github.ref == 'refs/heads/main' && github.event_name != 'pull_request'`. A feature-branch push or PR runs CI only; the real Terraform apply and deploy happen on the push to `main` that the merge creates. If `gh` is not authenticated here, stop after opening the PR and tell the user deployment will run after merge.

---

## Step 5: Monitor the Deploy Workflow

Only do this once the PR has merged to `main`. Select the deploy run precisely by branch, event, and the merge commit SHA so you do not accidentally watch the PR's CI-only run or another branch's run.

```bash
git fetch origin main
merge_sha=$(git rev-parse origin/main)

# Give Actions a moment to register the push, then find the run for this commit
sleep 5
run_id=$(gh run list --workflow=deploy.yml --branch main --event push \
  --commit "$merge_sha" --limit 1 --json databaseId --jq '.[0].databaseId')
```

**If `run_id` is empty, that is often correct, not an error.** `deploy.yml`'s
push trigger is path-filtered to `api/**`, `apps/verification-functions/**`,
`infra/**`, `packages/learn-to-cloud-shared/**`, `pyproject.toml`, `uv.lock`,
`scripts/**`, `docker-compose.yml`, and `.github/workflows/deploy.yml`. A merge
touching only docs, skills, or other paths starts no run at all. Confirm the
merge changed a deploy-relevant path before assuming something went wrong:

```bash
git diff --name-only "$merge_sha^" "$merge_sha"
```

If nothing deploy-relevant changed, report that no deploy was triggered and
skip to the end. Otherwise, retry the lookup a few times — Actions can take
several seconds to register the run.

Watch it with the built-in command instead of a hand-rolled poll loop. `--exit-status` returns non-zero on failure (handy for chaining), `--compact` keeps output small:

```bash
gh run watch "$run_id" --compact --exit-status
```

**If the workflow succeeds**: report success and the deploy URL (`gh run view "$run_id" --json url --jq .url`). Done!

---

## Step 6: Diagnose Deploy Failures

If `gh run watch` exits non-zero, pull just the failed logs:

```bash
gh run view "$run_id" --log-failed
```

For anything beyond an obvious lint/test slip (Terraform state locks, Azure auth/RBAC, container or migration job failures), hand off to the dedicated **debug-deploy** skill instead of duplicating that guidance here.

### Fix and Re-deploy

After fixing on the feature branch: re-run the quality gate (Step 2), commit, push, and once merged to `main`, monitor again (Step 5).

If no code changes are needed (e.g., a transient state lock that debug-deploy cleared):
```bash
gh run rerun "$run_id"
gh run watch "$run_id" --compact --exit-status
```

---

## Step 7: Verify Production

After a successful deploy:

```bash
curl -s https://<api-url>/health
curl -s https://<api-url>/ready
```



---

## Full Ship-It Flow Summary

```markdown
## Ship It: <branch-name>

1. **Branch + Auth**: on feature branch `<branch>`; gh authenticated (or noted)
2. **Quality Gate**: `uv run poe check` passed (static + package-smoke + tests across api, shared, verification-functions); CI-only checks run where relevant
3. **Commit**: `<commit-hash>` `<commit-message>`
4. **Push + PR**: pushed `<branch>`; PR opened to `main`; PR checks passing
5. **Deploy (after merge)**: Run #<id> succeeded / failed (see step 6) / pending merge
6. **Deploy fix (if needed)**: `<failure>` → fixed → re-deployed
7. **Production**: /health healthy | /ready ready
```

---

## Retry Policy

- **Quality gate auto-fixes**: re-run `uv run poe check` up to 3 times
- **Deploy failures**: attempt fix + re-deploy up to 2 times
- **Git push rejected or rebase conflict**: do not force past it, surface to the user
- **If still failing**: stop and report with full error context
