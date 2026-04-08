---
applyTo: "**/*.tf"
---

# Terraform / Azure Conventions

These supplement the project-wide rules in `copilot-instructions.md`.

## Resource Naming
- Pattern: `<service-code>-ltc-<purpose>-${var.environment}[-${local.suffix}]`

## Auth
- Managed Identity (Entra ID) — no passwords in infra.

## File Organization
- One `.tf` file per resource type.

## Azure Container Apps
- App deployed as a single container with revision-scoped scaling.
- Environment variables and secrets managed via Terraform `azurerm_container_app` resource.

## State & Safety
- Remote state in Azure Storage.
- Always run `terraform plan` before `apply`.
- Never modify state manually — use `terraform import` or `terraform state mv`.
