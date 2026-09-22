---
name: review-terraform
description: Run and review an Azure-backed Terraform plan for infrastructure changes. Use for "review terraform", "plan terraform PR", or Terraform deployability questions.
---

# Review Terraform

Review the diff and an Azure-backed plan before recommending merge. For an
open infrastructure PR, follow [the planning procedure](references/planning.md).
Inspect the existing head; do not update or rebase the branch unless requested.

Check:

- every planned action matches the intended diff
- no unexpected destroy, replacement, identity, auth, networking, or data change
- resources Azure creates by default are updated/imported rather than recreated
- the GitHub Actions identity has required Azure RBAC and, for `azuread_*`,
  Microsoft Graph permissions
- provider and lock-file-only updates produce no infrastructure changes
- Terraform formatting, validation, and tests pass

For risky identity changes, separate the platform gate from application
deployment.

Report planned resource actions, unexplained changes, and any blocked checks.
Do not recommend merge with unresolved destroy/replacement, identity,
authentication, state-access, or authorization concerns.

Production applies must run through `app-deploy.yml`, which calls the reusable
`infra-deploy.yml` before application deployment. Review does not authorize
apply, state mutation, imports, unlocks, or access changes. Never infer safety
from `terraform validate` alone.
