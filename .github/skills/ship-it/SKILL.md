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
- `prek` installed (brew install j178/tap/prek)
- Working directory is inside the repository

---

## Platform Detection

**CRITICAL**: Detect the OS first and use appropriate commands:

- **Windows**: Use PowerShell commands
- **macOS/Linux**: Use bash commands

---

## Step 0: Match users energy

Reply with "LFG 🚀 I'll ship it" to acknowledge the user's intent and energy around shipping their changes.


## Step 1: Run Prek

Run prek on all files to catch lint, format, and type errors before committing.

### Windows (PowerShell)
```powershell
Set-Location <workspace>; prek run --all-files
```

### macOS/Linux
```bash
cd <workspace> && prek run --all-files
```

### Handling Failures

Prek hooks may auto-fix issues (ruff lint `--fix`, ruff format, trailing whitespace, end-of-file).

**If prek fails:**

1. **Check if hooks auto-fixed files** — many hooks (ruff, trailing-whitespace, end-of-file-fixer) modify files in place. Re-run prek to confirm fixes are clean:
   ```powershell
   # Windows
   prek run --all-files
   ```
   ```bash
   # macOS/Linux
   prek run --all-files
   ```

2. **If the second run passes** — the auto-fixes resolved everything. Proceed to Step 2.

3. **If the second run still fails** — there are issues that require manual intervention:
   - **Ruff lint errors**: Read the error output, fix the code, re-run.
   - **ty type errors**: Read the error output, fix type issues, re-run.
   - **check-yaml / check-json**: Fix malformed YAML/JSON files.
   - **check-added-large-files**: Remove or `.gitignore` the large file.
   - **check-merge-conflict**: Resolve merge conflict markers.

4. **Keep re-running prek** until all hooks pass with no failures.

**Do NOT proceed to commit until prek passes cleanly.**

---

## Step 2: Stage Changed Files

After pre-commit passes (including any auto-fixed files), stage the changes.

### Check What Changed
```powershell
# Windows
git status
git diff --stat
```
```bash
# macOS/Linux
git status
git diff --stat
```

### Stage Files

Stage all changed files (including any auto-fixed files from pre-commit):

```powershell
# Windows / macOS / Linux
git add -A
```

**Review what's staged** to ensure nothing unexpected is included:
```powershell
git diff --cached --stat
```

---

## Step 3: Commit

Commit with a clear, conventional-commit-style message.

**If the user provided a commit message**, use it directly.

**If no commit message was provided**, generate one based on the changes:

```powershell
git commit -m "<type>: <concise description>"
```

Conventional commit types:
- `feat:` — new feature
- `fix:` — bug fix
- `refactor:` — code restructuring
- `docs:` — documentation only
- `style:` — formatting, no logic change
- `test:` — adding or fixing tests
- `chore:` — maintenance, dependencies

Ask the user for a commit message if the intent is ambiguous.

---

## Step 4: Push

Push to the current branch:

```powershell
git push
```

If the push is rejected (e.g., behind remote), pull first:
```powershell
git pull --rebase && git push
```

**Note the branch name** — the deploy workflow triggers on pushes to `main`. If on a different branch, inform the user that deployment won't trigger automatically and they may need to open a PR.

---

## Step 5: Monitor the Deploy Workflow

After pushing to `main`, the `deploy.yml` workflow triggers automatically.

### Wait for Workflow to Appear

The workflow may take a few seconds to start. Poll until it appears:

```powershell
# Windows / macOS / Linux
Start-Sleep -Seconds 5  # or: sleep 5
gh run list --workflow=deploy.yml --limit 1
```

### Watch the Workflow

Use `gh run watch` to monitor in real-time:

```powershell
gh run watch --exit-status
```

This blocks until the workflow completes and exits with:
- **Exit code 0**: Workflow succeeded
- **Non-zero exit code**: Workflow failed

**If the workflow succeeds** — report success and the deploy URL. Done!

---

## Step 6: Diagnose Deploy Failures

If the workflow fails, diagnose the issue.

### Get the Failed Run ID

```powershell
$runId = (gh run list --workflow=deploy.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

```bash
run_id=$(gh run list --workflow=deploy.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

### View Failed Logs

```powershell
gh run view $runId --log-failed
```

### Common Failure Patterns and Fixes

#### CI Failures (lint-and-test job)

| Pattern | Cause | Fix |
|---------|-------|-----|
| `ruff` lint errors | Lint failures in CI | Run `cd api && uv run ruff check --fix .`, commit & push |
| `ruff-format` | Format differences | Run `cd api && uv run ruff format .`, commit & push |
| `ty` type errors | Type checking failures | Fix type errors, commit & push |
| `pytest` / `FAILED` | Test failures | Run `cd api && uv run pytest tests/ -x`, fix failing tests, commit & push |

#### Terraform Failures

| Pattern | Cause | Fix |
|---------|-------|-----|
| `Error acquiring the state lock` | State locked by a prior run | Extract Lock ID, run `cd infra && terraform force-unlock -force <lock-id>`, then re-run |
| `AuthorizationFailed` | Expired credentials | Check `AZURE_CREDENTIALS` secret — not fixable locally |
| `ResourceNotFound` | Resource deleted outside TF | Run `terraform refresh` or re-import |

#### Build/Deploy Failures

| Pattern | Cause | Fix |
|---------|-------|-----|
| `docker build` fails | Dockerfile or dependency issue | Fix Dockerfile or `pyproject.toml`, commit & push |
| Smoke test `curl -f` fails | API doesn't start in container | Check `docker logs`, fix startup issue, commit & push |
| `Trivy` vulnerabilities | Security scan found HIGH/CRITICAL CVEs | Warning only (non-blocking), note in report |
| Container app update fails | Azure deployment error | Check Azure resource status, may need re-run |
| API readiness timeout | App didn't become ready in 5 min | Check app logs: `az containerapp logs show ...` |

### Fix and Re-deploy

After fixing the issue:

1. **Run pre-commit again** (go back to Step 1)
2. **Commit the fix**: `git add -A && git commit -m "fix: resolve deploy failure"`
3. **Push**: `git push`
4. **Monitor again** (go back to Step 5)

If the fix doesn't require code changes (e.g., Terraform state lock), re-run the workflow:

```powershell
gh run rerun $runId
gh run watch --exit-status
```

---

## Step 7: Verify Production

After a successful deploy, verify the production API is healthy:

```powershell
# Get the API URL from the workflow output
gh run view $runId --json jobs --jq '.jobs[] | select(.name | contains("deploy")) | .steps[] | select(.name | contains("Wait for API")) | .name'
```

Or check the known production URL if available:

```powershell
# Windows
(Invoke-WebRequest -Uri "https://<api-url>/health" -UseBasicParsing).Content
(Invoke-WebRequest -Uri "https://<api-url>/ready" -UseBasicParsing).Content
```

```bash
# macOS/Linux
curl -s https://<api-url>/health
curl -s https://<api-url>/ready
```

---

## Full Ship-It Flow Summary

Report progress using this format:

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

- **Pre-commit auto-fixes**: Re-run up to 3 times (auto-fixes cascade)
- **Deploy failures**: Attempt fix + re-deploy up to 2 times
- **If still failing after retries**: Stop and report the issue to the user with full error context

---

## Trigger Phrases

- "ship it"
- "commit and deploy"
- "push and deploy"
- "land this"
- "commit push and monitor"
- "deploy this"
