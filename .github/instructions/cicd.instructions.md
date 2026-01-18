---
applyTo: '.github/workflows/*.yml'
---

# CI/CD Workflow Standards

## Workflow Architecture

This project uses a **single unified pipeline** pattern (`deploy.yml`) following industry best practices:

```
PR/Push → Lint + Unit Tests → Terraform → Build → Deploy
```

### Why One Workflow?
- **No redundancy**: Tests run exactly once per pipeline
- **Clear dependency chain**: Each stage gates the next
- **Easier maintenance**: Single source of truth for CI/CD logic
- **Faster feedback**: Parallel jobs where possible

### Job Structure in deploy.yml
1. `api-lint-and-test` - Python linting (Ruff), type checking (ty), unit tests
2. `frontend-lint-and-test` - ESLint, Vitest tests, build check
3. `terraform` - Infrastructure validation and outputs (main branch only)
4. `deploy` - Build images, security scan, deploy to Azure (main branch only)

### What About Integration Tests?
- **Unit tests** run in CI (fast, no external dependencies)
- **Integration tests** with real database should run locally or in a separate scheduled workflow
- The smoke test in deploy validates the container starts correctly

## Naming
- Workflow files: `<action>.yml` (e.g., `deploy.yml`)
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
- Avoid duplicate test jobs across workflows
