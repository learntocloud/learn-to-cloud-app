---
name: cicd-debug
description: Debug GitHub Actions workflow failures and Terraform errors. Use when deployment failed, Terraform state lock, CI/CD pipeline errors, or troubleshooting deploy.yml.
---

# Debug Deploy Workflow Skill

This skill helps diagnose and fix issues with the GitHub Actions deploy workflow for the Learn to Cloud app.

## When to Use

- User mentions a failed deployment or CI/CD failure
- Terraform state lock errors
- Authentication or authorization failures
- Azure resource issues during deployment
- Workflow debugging or troubleshooting

## Debugging Process

### Step 1: Check Recent Workflow Runs

```bash
gh run list --workflow=deploy.yml --limit 5
```

### Step 2: View Failed Logs

```bash
gh run view <run-id> --log-failed
```

Or use the debug script in this skill's folder:
```bash
.github/skills/cicd-debug/debug-deploy.sh logs
```

### Step 3: Identify the Issue

Look for these common patterns in the logs:

#### Terraform State Lock
**Pattern:** `Error acquiring the state lock` or `state blob is already locked`

**Cause:** Previous workflow was cancelled mid-execution, leaving the state locked.

**Fix:**
1. Extract the Lock ID from the error (looks like `efd4cede-d5a2-61c3-31db-462852989510`)
2. Run: `cd infra && terraform force-unlock -force <lock-id>`
3. Re-run the workflow: `gh run rerun <run-id>`

#### Authentication Failures
**Pattern:** `AuthorizationFailed`, `AADSTS`, `unauthorized`

**Fix:** Check that `AZURE_CREDENTIALS` secret is valid. The service principal may need credential rotation.

#### Resource Not Found
**Pattern:** `ResourceNotFound` or `does not exist`

**Fix:** Resource was deleted outside Terraform. Run `terraform refresh` or re-import.

#### Azure Quota Exceeded
**Pattern:** `QuotaExceeded`

**Fix:** Request quota increase in Azure portal or clean up unused resources.

#### Migration Race Condition (Multi-Worker)
**Pattern:** `/ready` returns 503 but `/health` returns 200, or `DuplicateTableError: relation already exists`

**Cause:** Multiple uvicorn workers tried to run migrations simultaneously.

**Fix:** This should be handled by `pg_advisory_lock` in `api/alembic/env.py`. If it recurs:
1. Test locally: `docker compose down -v && docker compose up db api-multiworker`
2. Check that `alembic/env.py` uses psycopg2 (sync driver) and acquires advisory lock before migrations
3. Ensure the lock is committed before Alembic runs (so Alembic starts a clean transaction)

#### Test Failures
**Pattern:** `FAILED`, `pytest`, `AssertionError`

**Fix:** Run tests locally: `cd api && pytest tests/ -v`

#### Lint Failures
**Pattern:** `ruff`, `lint error`

**Fix:** Run linter locally: `cd api && ruff check .`

### Step 4: Fix and Re-run

After fixing the issue:
```bash
gh run rerun <run-id>
```

Or watch the progress:
```bash
gh run watch <run-id>
```

## Quick Commands Reference

| Command | Description |
|---------|-------------|
| `./.github/skills/cicd-debug/debug-deploy.sh status` | Show recent workflow runs |
| `./.github/skills/cicd-debug/debug-deploy.sh logs` | View and analyze failed logs |
| `./.github/skills/cicd-debug/debug-deploy.sh logs <id>` | View specific run's failed logs |
| `./.github/skills/cicd-debug/debug-deploy.sh unlock` | Fix Terraform state lock |
| `./.github/skills/cicd-debug/debug-deploy.sh rerun` | Re-run most recent failed workflow |
| `./.github/skills/cicd-debug/debug-deploy.sh watch` | Watch running workflow |

## Debug Script

The [debug-deploy.sh](./debug-deploy.sh) script automates the debugging process with automated issue detection.

## Prevention

The workflows are configured with these safeguards:
- `cancel-in-progress: true` - Cancels in-progress runs when a new push arrives (in `deploy.yml`)
- `-lock-timeout=120s` - Waits for locks instead of failing immediately (in `deploy.yml` terraform job)
