---
name: debug-deploy
description: Diagnose and resolve GitHub Actions application deployment, Terraform, migration-job, and Azure authorization failures.
---

# Debug Deploy

Use `gh run list --workflow=app-deploy.yml` for production orchestration failures
or `gh run list --workflow=infra-deploy.yml` for standalone Terraform plans.
Inspect the selected run with `gh run view <id> --log-failed`. Diagnose evidence
from the failed step before changing code or infrastructure.

Common paths:

- **Terraform lock:** identify the lock owner and active workflows. Never force
  unlock until the user confirms the lock is stale and authorizes the exact
  lock ID.
- **Azure/OIDC authorization:** verify repository variables/secrets, federated
  credential subject, Azure RBAC, and Microsoft Graph permissions where used.
- **Drift/not found:** compare configuration, state, and Azure. Do not refresh,
  import, or recreate resources speculatively.
- **Migration job:** inspect the Container Apps Job execution and logs; verify
  image, command, managed identity, PostgreSQL role mapping, and environment.
- **Tests/static checks:** reproduce the exact failing command locally and fix
  the root cause.
- **Quota/platform failure:** confirm Azure resource health and quota evidence
  before recommending a capacity or SKU change.

After a real fix, run the relevant local gate, push it through a PR, and monitor
the new run. Rerun unchanged code only for a demonstrated transient failure.
Never apply Terraform, mutate state, or change production access as part of
diagnosis without explicit confirmation.
