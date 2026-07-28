---
name: plan-terraform
description: Run and review the Azure-backed Terraform plan for an open pull request using the existing deploy workflow. Use when the user says "plan terraform PR", "run the terraform plan", "check the terraform provider PR", "is this terraform PR safe to merge", or asks to validate an infrastructure PR against production state.
---

# Plan Terraform Pull Request

Run Terraform plans in GitHub Actions so they use the repository's pinned
tooling, Azure OIDC identity, variables, secrets, and remote state. Never run
`terraform apply` or merge the pull request as part of this skill.

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

2. Update the pull request branch with the latest `main`:

   ```bash
   gh pr update-branch <pr-number>
   ```

   Re-read the pull request after the update and use its current
   `headRefName`.

3. Dispatch the existing deploy workflow on the pull request branch:

   ```bash
   gh workflow run deploy.yml --ref <head-ref>
   ```

4. Find the new manual run for that branch. Do not select a run created before
   the dispatch:

   ```bash
   gh run list \
     --workflow deploy.yml \
     --branch <head-ref> \
     --event workflow_dispatch \
     --limit 5 \
     --json databaseId,createdAt,status,conclusion,url
   ```

5. Wait for the run and fail if any job fails:

   ```bash
   gh run watch <run-id> --exit-status
   ```

6. Inspect the Terraform job logs:

   ```bash
   gh run view <run-id> --log
   ```

   Report the plan summary and every resource action. A successful workflow
   does not by itself mean the pull request is safe.

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

- Never run the workflow on `main`; that path can apply the saved plan.
- Never run `terraform apply`, `terraform force-unlock`, or modify state.
- Never print repository or environment secrets.
- If branch update, workflow dispatch, Azure login, or state access fails,
  report the failure instead of falling back to a local plan.
