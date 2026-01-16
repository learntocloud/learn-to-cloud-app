---
applyTo: '.github/workflows/*.yml'
---

# CI/CD Workflow Standards

## Naming
- Workflow files: `<action>.yml` (e.g., `deploy.yml`, `test.yml`)
- Job names: lowercase with hyphens
- Step names: Sentence case, descriptive

## Terraform Safety
- Always use `cancel-in-progress: false` for workflows with Terraform
- Add `-lock-timeout=120s` to all terraform plan/apply commands
- Use retry logic for transient failures

## Secrets & Variables
- Store secrets in GitHub repository secrets (not variables)
- Use OIDC for Azure authentication when possible
- Never echo secrets to logs

## Best Practices
- Pin action versions to SHA or major version
- Add timeout-minutes to prevent runaway jobs
- Use `if: failure()` for cleanup steps
