# CI/CD Strategy (Simplified)

## Architecture at a Glance
```
feature-branch ──PR──▶ dev ──merge──▶ main
                       │                │
                       ▼                ▼
                  rg-ltc-dev       rg-ltc-prod
                  (auto)           (merge-to-main)
                  dev-{sha}        prod-{sha}
```

## Core Rules
- Code deploys (api/, frontend/) are separate from infra (infra/).
- Build once in dev, promote to prod (no rebuilds).
- Dev infra is ephemeral (create → test → approve → destroy).

## Reusable Actions
- setup-azure-env: sets env vars (OIDC auth).
- deploy-api: deploys API container and waits for /ready.
 - Terraform secrets are passed at step level (not global env).

## Reusable Workflows
- lint-and-test.yml: API + frontend checks.
- build-and-push.yml: builds images, runs Trivy, pushes to ACR.
- infra-apply.yml: terraform plan/apply (explicit environment input).
- infra-apply.yml supports rollback via `rollback_ref` (default: infra-prod-stable).
- infra-destroy.yml: terraform destroy (explicit environment input).

## Deploy Workflows
### dev-deploy.yml
Triggers:
- PR to dev → lint/test only.
- push to dev or workflow_call → full dev deploy.

Flow (workflow_call):
1) lint-and-test
2) infra-apply (dev)
3) build-and-push (dev)
4) deploy (API + frontend)
5) approval-gate (12h)
6) infra-destroy (dev)

### prod-deploy.yml
Triggers:
- PR to main → lint/test only.
- push to main or workflow_call → promote + deploy.

Flow (push/workflow_call):
1) lint-and-test
2) promote-images (dev-{sha} → prod-{sha})
3) deploy (merge-to-main is approval)

## Weekly Rebuild
- weekly-rebuild.yml runs: dev-deploy(force_rebuild) → prod-deploy.

## Security & Concurrency
- Trivy blocks on HIGH/CRITICAL.
- Concurrency groups: deploy-dev, deploy-prod, infra-{environment}.

## Variables & Secrets
- All static names/URLs stored as GitHub variables.
- Secrets live in GitHub environments.

## Rollback (High Level)
- App: deploy previous prod-{sha} image.
- Infra: apply previous Terraform commit.
