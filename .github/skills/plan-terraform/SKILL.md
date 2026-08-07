---
name: plan-terraform
description: Run and review an Azure-backed Terraform plan for an infrastructure pull request without changing the user's worktree or remote state.
---

# Plan Terraform Pull Request

Use the supplied PR. If omitted, select it only when exactly one open PR changes
`infra/**`; otherwise ask the user.

1. Confirm the PR is open, targets `main`, and changes `infra/**`.
2. Update it with `main`, then record the exact head SHA.
3. Verify Azure CLI authentication, Terraform availability, and that the active
   subscription matches repository variable `AZURE_SUBSCRIPTION_ID`.
4. Create a detached worktree for that SHA under the current session's `files/`
   directory. Never plan in the primary worktree.
5. Inspect `.github/workflows/deploy.yml` and mirror its current backend key and
   `TF_VAR_*` inputs. Retrieve required repository variables and Azure values
   without printing secrets.
6. In the worktree's `infra/`, run:

   ```bash
   terraform init -backend-config="key=learn-to-cloud-${AZURE_ENV_NAME}.tfstate"
   terraform plan -input=false -lock-timeout=120s -no-color
   ```

7. Remove the temporary worktree on success or failure.

Never save a plan file, apply, unlock, import, modify state, merge the PR, or
expose secrets.

Report every resource action and compare it with the diff. `No changes` is the
expected result for provider-only updates. Block on destroy/replacement,
identity or authentication changes, state-access failures, authorization
errors, or actions not explained by the PR.
