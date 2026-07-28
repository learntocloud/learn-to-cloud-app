---
name: review-terraform
description: Review and validate Terraform infrastructure changes against Azure deployment permissions before merging. Use when the user says "review terraform", "check the terraform plan", "will this terraform change deploy", or is adding/editing .tf files, especially azuread or Entra app registration resources.
---

# Review Terraform

For infrastructure changes, always review the Terraform plan for deployment permissions and Azure resources that may already exist.

- Run an Azure-backed `terraform plan` before merging infrastructure changes.
- Check whether the GitHub Actions deployment identity can create every resource in the plan. Normal Azure RBAC is not enough for Microsoft Graph or Entra app registration resources.
- Be careful with new provider families, especially `azuread`. Adding `azuread_*` resources usually means the deploy identity needs Microsoft Graph permissions, or the identity object should be pre-created and passed into Terraform.
- For Azure child config resources that Azure creates by default, update or import the existing resource instead of trying to create it. For Function App authentication, use `azapi_update_resource` for `authsettingsV2`.
- For risky auth or identity changes, prefer the smallest safe platform change first, then deploy application code after the platform gate is confirmed.
