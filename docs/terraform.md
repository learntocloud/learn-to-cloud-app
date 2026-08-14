# Terraform validation and deployment

Terraform changes pass through three separate checks. Each check has different
credentials and provides a different level of confidence.

| Stage | Command or workflow | Azure access | Purpose |
|-------|---------------------|--------------|---------|
| Local and offline CI | `uv run poe terraform-check` | None | Check formatting, initialize providers without the backend, and validate configuration |
| Pull-request plan | `Terraform PR Plan` | Read-only | Compare the proposed configuration with remote state and current Azure resources |
| Main deployment | `Deploy` | Contributor | Create a fresh locked plan and apply it after merge |

Offline validation cannot detect resource drift or show whether Terraform will
create, update, replace, or delete existing resources. The pull-request plan
fills that gap, but it still cannot guarantee that Azure will accept an apply.
Policy, quota, naming availability, write permissions, and service-specific
validation can still reject changes after merge.

## Pull-request plan security

The Azure-backed plan runs only for same-repository pull requests that change
`infra/**` or the plan workflow. Fork pull requests fail the stable
`terraform-plan-status` check and never request Azure credentials.

The plan job:

- waits for approval through the protected `terraform-plan` environment
- requests an OIDC token only after approval
- uses a dedicated Entra application with subscription `Reader`
- has `Storage Blob Data Reader` only on the Terraform state container
- runs with `-lock=false`, so it does not need state-write or lease permissions
- receives configuration identifiers through environment variables, not
  application secrets
- publishes only aggregate create, update, replace, and delete counts
- fails when any replacement or deletion is proposed

The saved plan, plan JSON, remote state, and full plan output remain only on the
ephemeral GitHub-hosted runner and are never uploaded or added to the pull
request.

## One-time repository setup

An Azure and repository administrator can create the read-only identity,
configure its OIDC trust and role assignments, and protect the GitHub
environment with:

```bash
scripts/configure-terraform-plan.sh \
  GITHUB_OAUTH_CLIENT_ID \
  madebygps \
  rishabkumar7
```

Reviewers must have access to the repository. Self-approval is disabled, so a
pull-request author cannot approve their own plan even when they are listed.
The GitHub OAuth client ID is configuration rather than a secret, but it must
match the value used by the deployed Terraform state so the plan does not
report a false application update.

The script copies the existing Azure environment and PostgreSQL administrator
repository variables into the protected environment. It does not copy or
create GitHub Actions secrets.

After the workflow has reported once, add `terraform-plan-status` to the active
`main` branch ruleset's required status checks. This check succeeds immediately
for pull requests without Terraform changes and gates infrastructure pull
requests on the approved Azure-backed plan.

## Production apply

The existing `Deploy` workflow remains the only path that applies Terraform. It
runs on `main`, authenticates with the deployment identity, creates a new plan
with state locking immediately before apply, and never reuses a pull-request
plan.
