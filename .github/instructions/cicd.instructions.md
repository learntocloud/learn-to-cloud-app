---
applyTo: '.github/workflows/*.yml'
---

# CI/CD Workflow Instructions

## Debugging Failed Workflows

When a GitHub Actions workflow fails, use this systematic approach:

### Step 1: View Recent Runs
```bash
gh run list --limit 5
```

### Step 2: View Failed Logs
```bash
gh run view <run-id> --log-failed
```

### Step 3: Common Issues and Fixes

#### Terraform State Lock Error
**Symptoms:** `Error acquiring the state lock` or `state blob is already locked`

**Cause:** Previous workflow was cancelled mid-execution (often due to `cancel-in-progress: true`), leaving the state locked.

**Fix:**
1. Extract the Lock ID from the error message
2. Run: `cd infra && terraform force-unlock -force <lock-id>`
3. Re-run the workflow: `gh run rerun <run-id>`

**Prevention:** Use `cancel-in-progress: false` and add `-lock-timeout=120s` to Terraform commands.

#### Authentication Failures
**Symptoms:** `AuthorizationFailed`, `AADSTS`, or `unauthorized`

**Fix:** Check that `AZURE_CREDENTIALS` secret is valid. The service principal credentials may need rotation.

#### Resource Not Found
**Symptoms:** `ResourceNotFound` or `does not exist`

**Fix:** A resource was deleted outside Terraform. Run `terraform refresh` or import the resource.

#### Azure Quota Exceeded
**Symptoms:** `QuotaExceeded`

**Fix:** Request quota increase in Azure portal or clean up unused resources.

### Quick Debug Script
Use the debug script for automated issue detection:
```bash
./scripts/debug-deploy.sh logs      # View and analyze failed logs
./scripts/debug-deploy.sh unlock    # Fix Terraform state lock
./scripts/debug-deploy.sh rerun     # Re-run failed workflow
```

## Best Practices

1. **Concurrency:** Use `cancel-in-progress: false` for workflows with Terraform to prevent state lock issues
2. **Lock Timeout:** Always use `-lock-timeout=120s` for Terraform plan/apply
3. **Retry Logic:** Add retry logic for transient failures (network, locks)
4. **Secrets:** Use GitHub repository secrets for sensitive values, variables for non-sensitive config
