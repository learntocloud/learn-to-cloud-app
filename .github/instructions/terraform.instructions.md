---
applyTo: "infra/*.tf, infra/*.tfvars"
description: "Azure resource naming, tagging, state management, and security practices"
---

# Terraform Standards

## Naming & Tags
- Resources: `<type>-<project>-<component>-<env>` (e.g., `rg-ltc-api-dev`)
- All resources must have `environment` and `project` tags

## Azure-Specific
- Use `lifecycle.ignore_changes` for fields Azure manages asynchronously (SSL bindings, managed identity assignments)

## State Management
- State stored in Azure Storage Account
- Always use `-lock-timeout=120s`
- Never manually edit state files

## Security
- No secrets in `.tf` files—use `sensitive = true` variables
- Prefer managed identities over service principal secrets

---

## Feedback
If you encounter a pattern, convention, or edge case that should be added to these instructions, let me know so we can consider including it.
