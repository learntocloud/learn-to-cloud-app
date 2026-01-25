---
applyTo: 'infra/*.tf, infra/*.tfvars'
---

# Terraform Standards

## Naming Conventions
- Resources: `<type>-<project>-<component>-<env>` (e.g., `rg-ltc-api-dev`)
- Variables: `snake_case`
- Outputs: `snake_case`

## Required Tags
All resources must include:
- `environment` (dev, staging, prod)
- `project` (ltc)

## Azure-Specific
- Use `lifecycle.ignore_changes` for fields Azure manages asynchronously
- Example: SSL certificate bindings, managed identity assignments

## State Management
- State stored in Azure Storage Account
- Always use `-lock-timeout=120s` to prevent lock issues
- Never manually edit state files

## Security
- No secrets in `.tf` files—use variables with `sensitive = true`
- Use managed identities over service principal secrets

## Comments
- Use `#` comments for non-obvious configurations
- Document **why** defaults are overridden
- Keep comments concise—Terraform is self-documenting
