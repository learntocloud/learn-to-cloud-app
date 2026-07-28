---
name: plan-terraform
description: Run and review a local Azure-backed Terraform plan for an open pull request. Use when the user says "plan terraform PR", "run the terraform plan", "check the terraform provider PR", "is this terraform PR safe to merge", or asks to validate an infrastructure PR against production state.
---

# Plan Terraform Pull Request

Run Terraform plans locally with the authenticated Azure CLI against the
remote development state. Use a temporary detached worktree so the user's
current branch and files remain untouched. Never run `terraform apply` or
merge the pull request as part of this skill.

## Inputs

Use the pull request number supplied by the user. If none is supplied and
exactly one open pull request changes `infra/**`, use that pull request.
Otherwise, ask which pull request to plan.

## Process

1. Confirm the pull request is open, targets `main`, and changes `infra/**`:

   ```bash
   gh pr view <pr-number> \
     --json state,baseRefName,headRefName,headRepositoryOwner,files,url
   ```

2. Update the pull request branch with the latest `main`, then record its
   current head SHA:

   ```bash
   gh pr update-branch <pr-number>
   gh pr view <pr-number> --json headRefOid --jq .headRefOid
   ```

3. Confirm local prerequisites:

   ```bash
   az account show
   terraform version
   ```

   The Azure subscription must match the repository's
   `AZURE_SUBSCRIPTION_ID` variable. Stop if the user is not authenticated or
   the subscriptions differ.

4. Create a detached worktree for the exact pull request SHA under the current
   Copilot session's `files/` directory:

   ```bash
   git fetch origin
   git worktree add --detach <session-files>/terraform-pr-<pr-number> <head-sha>
   ```

5. Read the non-secret Terraform inputs from GitHub repository variables:

   ```bash
   gh variable list --json name,value
   ```

   Required values are `AZURE_ENV_NAME`, `AZURE_LOCATION`,
   `AZURE_SUBSCRIPTION_ID`, `POSTGRES_ENTRA_ADMIN_OBJECT_ID`,
   `POSTGRES_ENTRA_ADMIN_PRINCIPAL_NAME`, and
   `POSTGRES_ENTRA_ADMIN_PRINCIPAL_TYPE`.

6. Read `github_client_id` from the API Container App's
   `OAUTH__CLIENT_ID` environment variable. Read `smoke_test_token` from the
   `smoke-test-token` Container App secret using `--show-values`. Capture both
   directly into shell variables and never print them.

7. From the temporary worktree's `infra/` directory, initialize the remote
   backend using the environment-specific state key:

   ```bash
   terraform init \
     -backend-config="key=learn-to-cloud-${AZURE_ENV_NAME}.tfstate"
   ```

8. Export the same `TF_VAR_*` inputs used by `.github/workflows/deploy.yml`,
   then run:

   ```bash
   terraform plan -input=false -lock-timeout=120s -no-color
   ```

   Do not save a plan file. Report the plan summary and every resource action.

9. Remove the temporary worktree after the plan, including when initialization
   or planning fails:

   ```bash
   git worktree remove <session-files>/terraform-pr-<pr-number>
   ```

## Decision Rules

- **Safe provider or lock-file update:** The plan says `No changes`.
- **Needs review:** The plan adds or changes any Azure resource.
- **Block:** The plan destroys or replaces a resource, changes identity or
  authentication, cannot acquire state, or reports authorization errors.
- For a non-empty plan, compare every action with the pull request diff.
  Provider-only updates should normally produce no infrastructure changes.
- Check that the deployment identity has the required Azure and Microsoft
  Graph permissions before recommending a merge.

## Safety

- Never run `terraform apply`, `terraform force-unlock`, or modify state.
- Never print repository or environment secrets.
- Never run the plan from the repository's primary worktree.
- If Azure login, variable discovery, secret retrieval, backend
  initialization, or state access fails, report the failure and clean up.
