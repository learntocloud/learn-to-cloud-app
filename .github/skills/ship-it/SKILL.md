---
name: ship-it
description: Run prek, resolve issues, commit, push, then monitor the deploy workflow and resolve any deploy failures. Use when user says "ship it", "commit and deploy", "push and deploy", or "land this".
---

# Ship It — Prek, Commit, Push & Monitor Deploy

End-to-end workflow: run prek checks, fix failures, commit, push, and monitor the GitHub Actions deploy pipeline through to a healthy production readiness check.

**This skill orchestrates the full ship cycle. Do NOT skip steps.**

---

## When to Use

- User says "ship it", "land this", "commit and deploy", "push and deploy"
- User wants to commit, push, and ensure a successful deploy
- After completing a feature or fix and wanting to ship to production

---

## Prerequisites

- `gh` CLI authenticated (`gh auth status`)
- `git` configured with push access to the remote
- `prek` installed (`brew install j178/tap/prek`)
- Working directory is inside the repository

---

## Step 0: Match User's Energy

Reply with "LFG 🚀 I'll ship it" to acknowledge the user's intent.

---

## Step 1: Run Prek

```bash
cd <workspace> && prek run --all-files
```

### Handling Failures

Prek hooks may auto-fix issues (ruff lint `--fix`, ruff format, trailing whitespace, end-of-file).

**If prek fails:**

1. **Check if hooks auto-fixed files** — many hooks modify files in place. Re-run prek:
   ```bash
   prek run --all-files
   ```

2. **If the second run passes** — the auto-fixes resolved everything. Proceed to Step 2.

3. **If the second run still fails** — manual intervention needed:
   - **Ruff lint errors**: Read error output, fix the code, re-run
   - **ty type errors**: Read error output, fix type issues, re-run
   - **check-yaml / check-json**: Fix malformed YAML/JSON files
   - **check-added-large-files**: Remove or `.gitignore` the large file
   - **check-merge-conflict**: Resolve merge conflict markers

4. **Keep re-running prek** until all hooks pass.

**Do NOT proceed to commit until prek passes cleanly.**

---

## Step 2: Stage Changed Files

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

## Step 3: Commit

**If the user provided a commit message**, use it directly.

**If no commit message was provided**, generate one based on the changes:

```bash
git commit -m "<type>: <concise description>"
```

Conventional commit types: `feat:`, `fix:`, `refactor:`, `docs:`, `style:`, `test:`, `chore:`

Ask the user for a commit message if the intent is ambiguous.

---

## Step 4: Push

```bash
git push
```

If rejected (behind remote):
```bash
git pull --rebase && git push
```

**Note**: The deploy workflow triggers on pushes to `main`. If on a different branch, inform the user that deployment won't trigger automatically.

---

## Step 5: Monitor the Deploy Workflow

After pushing to `main`, the `deploy.yml` workflow triggers automatically.

### Wait for Workflow to Appear

```bash
sleep 5
gh run list --workflow=deploy.yml --limit 1
```

### Watch the Workflow

```bash
gh run watch --exit-status
```

This blocks until the workflow completes. Exit code 0 = success, non-zero = failure.

**If the workflow succeeds** — report success and the deploy URL. Done!

---

## Step 6: Diagnose Deploy Failures

If the workflow fails:

```bash
run_id=$(gh run list --workflow=deploy.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view $run_id --log-failed
```

### Common Failure Patterns

#### CI Failures (lint-and-test job)

| Pattern | Fix |
|---------|-----|
| `ruff` lint errors | `cd api && uv run ruff check --fix .`, commit & push |
| `ruff-format` | `cd api && uv run ruff format .`, commit & push |
| `ty` type errors | Fix type errors, commit & push |
| `pytest` / `FAILED` | `cd api && uv run pytest tests/ -x`, fix, commit & push |

#### Terraform Failures

| Pattern | Fix |
|---------|-----|
| `Error acquiring the state lock` | Extract Lock ID, `cd infra && terraform force-unlock -force <lock-id>`, re-run |
| `AuthorizationFailed` | Check `AZURE_CREDENTIALS` secret — not fixable locally |
| `ResourceNotFound` | `terraform refresh` or re-import |

#### Build/Deploy Failures

| Pattern | Fix |
|---------|-----|
| `docker build` fails | Fix Dockerfile or `pyproject.toml`, commit & push |
| Smoke test `curl -f` fails | Check `docker logs`, fix startup issue, commit & push |
| API readiness timeout | Check app logs: `az containerapp logs show ...` |

### Fix and Re-deploy

After fixing:
1. Run prek again (Step 1)
2. `git add -A && git commit -m "fix: resolve deploy failure"`
3. `git push`
4. Monitor again (Step 5)

If no code changes needed (e.g., state lock):
```bash
gh run rerun $run_id
gh run watch --exit-status
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

### 1. Pre-commit
✅ All hooks passed / ❌ Failed → fixed → ✅ Passed on re-run

### 2. Stage
✅ X files staged

### 3. Commit
✅ `<commit-hash>` — `<commit-message>`

### 4. Push
✅ Pushed to `<branch>` on `origin`

### 5. Deploy Workflow
✅ Run #<id> — succeeded in X min / ❌ Failed (see step 6)

### 6. Deploy Fix (if needed)
❌ <failure reason> → fixed → ✅ Re-deployed successfully

### 7. Production Health
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
