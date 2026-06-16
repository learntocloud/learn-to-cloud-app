---
name: ship-it
description: Run prek, run tests, resolve issues, commit, push, open a PR to main, then monitor the deploy workflow after merge and resolve any deploy failures. Use when user says "ship it", "commit and deploy", "push and deploy", or "land this".
---

# Ship It — Prek, Commit, Push & Monitor Deploy

End-to-end workflow: run prek checks, run tests, fix failures, commit, push, and monitor the GitHub Actions deploy pipeline through to a healthy production readiness check.

**This skill orchestrates the full ship cycle. Do NOT skip steps.**

---

## When to Use

- User says "ship it", "land this", "commit and deploy", "push and deploy"
- User wants to commit, push, and ensure a successful deploy
- After completing a feature or fix and wanting to ship to production

---

## Prerequisites

- `gh` CLI authenticated. Check with `gh auth status` at the very start (see Step 1).
- `git` configured with push access to the remote
- `prek` installed (already present in the project devcontainer; otherwise install from https://github.com/j178/prek)
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
gh auth status || echo "gh NOT authenticated — deploy monitoring will be skipped"
```

- Never commit on `main`. If `$branch` is `main`, stop and ask the user for a feature branch name first.
- If `gh` is not authenticated, you can still run checks, commit, push, and open a PR through the web link, but you will not be able to monitor the deploy run from here. Tell the user this up front.

---

## Step 2: Run Prek


```bash
cd <workspace> && git add -A && prek run --all-files
```

> Stage files first (`git add -A`). `prek run --all-files` only inspects git-tracked files, so newly-created files (new migrations, modules, tests) are silently skipped unless staged.

### Handling Failures

Prek hooks may auto-fix issues (ruff lint `--fix`, ruff format, trailing whitespace, end-of-file).

**If prek fails:**

1. **Check if hooks auto-fixed files** — many hooks modify files in place. Re-run prek:
   ```bash
   prek run --all-files
   ```

2. **If the second run passes** — the auto-fixes resolved everything. Proceed to Step 3.

3. **If the second run still fails** — manual intervention needed:
   - **Ruff lint errors**: Read error output, fix the code, re-run
   - **ty type errors**: Read error output, fix type issues, re-run
   - **check-yaml / check-json**: Fix malformed YAML/JSON files
   - **check-added-large-files**: Remove or `.gitignore` the large file
   - **check-merge-conflict**: Resolve merge conflict markers

4. **Keep re-running prek** until all hooks pass.

**Do NOT proceed to Step 3 until prek passes cleanly.**

---

## Step 3: Run the Quality Gates

prek is a fast first pass, but the authoritative checks live in `.github/copilot-instructions.md`. Run the full Quality Gates so a newly-created file cannot pass locally yet fail in CI.

```bash
# Lint, format, and type-check across all three projects
cd <workspace>/api && uv run ruff check . ../packages/learn-to-cloud-shared
cd <workspace>/api && uv run ruff format --check . ../packages/learn-to-cloud-shared
cd <workspace>/api && uv run ty check --exclude scripts --exclude tests .
cd <workspace>/packages/learn-to-cloud-shared && uv run ty check --exclude tests .
cd <workspace>/apps/verification-functions && uv run ruff check . && uv run ruff format --check . && uv run ty check .

# Tests (catch runtime errors that static checks cannot)
cd <workspace>/api && uv run pytest tests/ -x --tb=short
cd <workspace>/packages/learn-to-cloud-shared && uv run pytest tests/ -x --tb=short
cd <workspace>/apps/verification-functions && uv run python -c "import function_app"
```

### Handling Failures

**If any check or test fails:**

1. Read the failure output — fix the code (never silence with `# noqa` or `type: ignore`)
2. Re-run prek (Step 2) if you changed Python files
3. Re-run the Quality Gates until everything passes

**Do NOT proceed to commit until all checks and tests pass. No exceptions.**

---

## Step 4: Stage Changed Files


```bash
git status
git diff --stat
```

**Always stage ALL changes. Never cherry-pick files. `ship it` means ship everything.**

```bash
git add -A
git diff --cached --stat
```

---

## Step 5: Commit

**If the user provided a commit message**, use it directly.

**If no commit message was provided**, generate one based on the changes:

```bash
git commit -m "<type>: <concise description>"
```

Conventional commit types: `feat:`, `fix:`, `refactor:`, `docs:`, `style:`, `test:`, `chore:`

Include the repo's `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer unless the user asks otherwise. Ask the user for a commit message if the intent is ambiguous.

---

## Step 6: Push and Open a PR

```bash
git push -u origin "$branch"
```

If rejected (behind remote):
```bash
git pull --rebase && git push
```

If the current branch is not `main`, open a PR to `main` after pushing:

```bash
gh pr create --fill --base main --head "$branch"
```

Then watch the PR's own checks (CI, terraform-ci, dependency-review). These run on the `pull_request` event but do NOT deploy:

```bash
gh pr checks "$branch" --watch --fail-fast
```

**Merging is a separate, explicit decision.** Deploy only happens after the PR merges to `main`. Branch protection may require a human review, so do not assume you can merge. If the user wants to merge and it is allowed:

```bash
gh pr merge "$branch" --squash --auto --delete-branch
```

**Note**: The `deploy.yml` deploy jobs are gated to `github.ref == 'refs/heads/main' && github.event_name != 'pull_request'`. A feature-branch push or PR runs CI only. The real Terraform apply and deploy happen on the push to `main` that the merge creates. If `gh` is not authenticated here, stop after opening the PR and tell the user deployment will run after merge.

---

## Step 7: Monitor the Deploy Workflow

Only do this once the PR has merged to `main`. Select the deploy run precisely by branch, event, and the merge commit SHA so you do not accidentally watch the PR's CI-only run or another branch's run.

```bash
git fetch origin main
merge_sha=$(git rev-parse origin/main)

# Give Actions a moment to register the push, then find the run for this commit
sleep 5
run_id=$(gh run list --workflow=deploy.yml --branch main --event push \
  --commit "$merge_sha" --limit 1 --json databaseId --jq '.[0].databaseId')
```

Watch it with the built-in command instead of a hand-rolled poll loop. `--exit-status` returns non-zero on failure (handy for chaining), `--compact` keeps output small:

```bash
gh run watch "$run_id" --compact --exit-status
```

**If the workflow succeeds** — report success and the deploy URL (`gh run view "$run_id" --json url --jq .url`). Done!

---

## Step 8: Diagnose Deploy Failures

If `gh run watch` exits non-zero, pull just the failed logs:

```bash
gh run view "$run_id" --log-failed
```

For deeper troubleshooting (Terraform state locks, Azure auth errors, container or migration job failures), use the dedicated **debug-deploy** skill rather than duplicating that guidance here. A quick orientation:

#### CI / lint-and-test failures (fixable locally)

| Pattern | Fix |
|---------|-----|
| `ruff` lint errors | `(cd api && uv run ruff check --fix . ../packages/learn-to-cloud-shared)`, commit & push |
| `ruff-format` | `(cd api && uv run ruff format . ../packages/learn-to-cloud-shared)`, commit & push |
| `ty` type errors | Fix type errors, commit & push |
| `pytest` / `FAILED` | Reproduce with `uv run pytest tests/ -x`, fix, commit & push |

#### Terraform / build / deploy failures

These usually need the **debug-deploy** skill (state-lock recovery, OIDC/RBAC checks, container and migration job logs). Hand off there instead of guessing.

### Fix and Re-deploy

After fixing on the feature branch:
1. Re-run prek (Step 2) and the Quality Gates (Step 3)
2. `git add -A && git commit -m "fix: resolve deploy failure"`
3. `git push`
4. Once merged to `main`, monitor again (Step 7)

If no code changes are needed (e.g., a transient state lock that debug-deploy cleared):
```bash
gh run rerun "$run_id"
gh run watch "$run_id" --compact --exit-status
```

---

## Step 9: Verify Production

After a successful deploy:

```bash
curl -s https://<api-url>/health
curl -s https://<api-url>/ready
```


---

## Full Ship-It Flow Summary

```markdown
## Ship It: <branch-name>

### 1. Branch + Auth
✅ On feature branch `<branch>` | gh authenticated (or noted as not)

### 2. Pre-commit
✅ All hooks passed / ❌ Failed → fixed → ✅ Passed on re-run

### 3. Quality Gates
✅ ruff + ty + pytest passed across api, shared, verification-functions

### 4. Commit
✅ `<commit-hash>` — `<commit-message>`

### 5. Push + PR
✅ Pushed to `<branch>`; PR opened to `main`; PR checks passing

### 6. Deploy Workflow (after merge)
✅ Run #<id> — succeeded in X min / ❌ Failed (see step 7) / ⏸ pending merge

### 7. Deploy Fix (if needed)
❌ <failure reason> → fixed → ✅ Re-deployed successfully

### 8. Production Health
✅ /health — healthy | /ready — ready
```


---

## Retry Policy

- **Pre-commit auto-fixes**: Re-run up to 3 times
- **Deploy failures**: Attempt fix + re-deploy up to 2 times
- **If still failing**: Stop and report the issue with full error context

---

## Trigger Phrases

- "ship it"
- "commit and deploy"
- "push and deploy"
- "land this"
- "deploy this"
