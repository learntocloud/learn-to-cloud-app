---
name: review-terraform
description: Review Terraform changes for plan safety, existing Azure resources, and deployment-identity permissions. Use for Terraform review or deployability questions.
---

# Review Terraform

Review the diff and an Azure-backed plan before recommending merge.

Check:

- every planned action matches the intended diff
- no unexpected destroy, replacement, identity, auth, networking, or data change
- resources Azure creates by default are updated/imported rather than recreated
- the GitHub Actions identity has required Azure RBAC and, for `azuread_*`,
  Microsoft Graph permissions
- provider and lock-file-only updates produce no infrastructure changes
- Terraform formatting, validation, and tests pass

For Function App `authsettingsV2`, prefer updating the existing child resource
with `azapi_update_resource`. For risky identity changes, separate the platform
gate from application deployment.

Use the `plan-terraform` skill when planning an open pull request against remote
state. Never infer safety from `terraform validate` alone.
