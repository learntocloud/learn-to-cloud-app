---
name: debug-deploy
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
.github/skills/debug-deploy/debug-deploy.sh logs
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

**Fix:** Check the OIDC deployment configuration: `AZURE_CLIENT_ID` and `AZURE_TENANT_ID` secrets, plus the `AZURE_SUBSCRIPTION_ID` repository variable. The federated credential or Azure RBAC assignment may need updating.

#### Resource Not Found
**Pattern:** `ResourceNotFound` or `does not exist`

**Fix:** Resource was deleted outside Terraform. Run `terraform refresh` or re-import.

#### Azure Quota Exceeded
**Pattern:** `QuotaExceeded`

**Fix:** Request quota increase in Azure portal or clean up unused resources.

#### Migration Job Failure
**Pattern:** `Run database migrations` fails, `/ready` returns 503 after deploy, or Alembic reports a database error.

**Cause:** The Azure Container Apps migration job failed before the API image was updated. Common causes are missing PostgreSQL role mapping, migration SQL errors, or job image/env override issues.

**Fix:**
1. Inspect the failed workflow step and the ACA Job logs.
2. Verify `migration_identity_principal_id` is mapped to the Terraform `migration_postgres_role` output in PostgreSQL.
3. Confirm `az containerapp job start` passes the SHA image, `alembic upgrade head`, DB env vars, `AZURE_CLIENT_ID`, and `--registry-identity`.
4. Check that `alembic/env.py` still uses psycopg2 and acquires the advisory lock before migrations.

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
| `./.github/skills/debug-deploy/debug-deploy.sh status` | Show recent workflow runs |
| `./.github/skills/debug-deploy/debug-deploy.sh logs` | View and analyze failed logs |
| `./.github/skills/debug-deploy/debug-deploy.sh logs <id>` | View specific run's failed logs |
| `./.github/skills/debug-deploy/debug-deploy.sh unlock` | Fix Terraform state lock |
| `./.github/skills/debug-deploy/debug-deploy.sh rerun` | Re-run most recent failed workflow |
| `./.github/skills/debug-deploy/debug-deploy.sh watch` | Watch running workflow |

## Debug Script

The [debug-deploy.sh](./debug-deploy.sh) script automates the debugging process with automated issue detection.

## Prevention

The workflows are configured with these safeguards:
- `cancel-in-progress: true` - Cancels in-progress runs when a new push arrives (in `deploy.yml`)
- `-lock-timeout=120s` - Waits for locks instead of failing immediately (in `deploy.yml` terraform job)
