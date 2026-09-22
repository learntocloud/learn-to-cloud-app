# Planning an Infrastructure Pull Request

Use the supplied PR. If omitted, select it only when exactly one open PR changes
`infra/**`; otherwise ask the user.

1. Confirm the PR is open, targets `main`, and changes `infra/**`.
2. Record its exact head SHA without updating the PR. If it is behind `main`,
   report that limitation; updating the branch requires a separate request.
3. Verify Azure CLI authentication, Terraform availability, and that the active
   subscription matches repository variable `AZURE_SUBSCRIPTION_ID`.
4. Create a detached worktree for that SHA under the current session's `files/`
   directory. Never plan in the primary worktree.
5. Inspect `.github/workflows/infra-deploy.yml` and mirror its current backend
   key and `TF_VAR_*` inputs. Retrieve required repository variables and Azure
   values without printing secrets. If required inputs are inaccessible, report
   the blocker rather than substituting guessed values.
6. In the worktree's `infra/`, run:

   ```bash
   terraform fmt -check -recursive
   terraform init -backend-config="key=learn-to-cloud-${AZURE_ENV_NAME}.tfstate"
   terraform validate
   terraform test -no-color
   terraform plan -input=false -lock-timeout=120s -no-color
   ```

7. Remove the temporary worktree on success or failure.

Never save a plan file, apply, unlock, import, modify state, merge the PR, or
expose secrets. A plan using the signed-in user's identity does not prove the
deployment identity has the required permissions; review those separately.

Report the reviewed SHA and compare every planned resource action with the diff.
If the PR head changes during review, the plan no longer validates its current
head. `No changes` is the expected result for provider-only updates.
