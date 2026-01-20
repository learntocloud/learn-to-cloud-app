# CI/CD and Branching Strategy

## Architecture Overview

```
feature-branch ──PR──▶ dev ──merge──▶ main
                       │                │
                       ▼                ▼
                  rg-ltc-dev       rg-ltc-prod
                  (auto-deploy)    (manual approval)
                  dev-{sha}        prod-{sha}
```

## Key Principles

1. **Separation of Concerns**: Code deployments (`api/**`, `frontend/**`) and infrastructure changes (`infra/**`) run independently
2. **Build Once, Promote**: Images built in dev, tested, then retagged for prod (no rebuilds)
3. **Composable Workflows**: Reusable building blocks (`lint-and-test.yml`, `build-and-push.yml`)
4. **GitHub Variables**: Static resource names/URLs stored as repo variables (faster than Terraform queries)

## Branch Strategy

| Branch | Environment | Trigger | Approval |
|--------|-------------|---------|----------|
| `dev` | rg-ltc-dev | Auto on merge | None |
| `main` | rg-ltc-prod | Auto on merge | Manual |

---

## Workflows

### 1. lint-and-test.yml (Reusable)

**Purpose:** Code quality checks (single source of truth)

**Jobs:**
- API: Ruff lint/format, type check, unit tests
- Frontend: ESLint, Vitest, build check

**Called by:** dev-deploy.yml, prod-deploy.yml

---

### 2. build-and-push.yml (Reusable)

**Purpose:** Build Docker images, security scan, push to ACR

**Inputs:**
- `environment` (dev/prod) - required
- `force_rebuild` (boolean) - bypass cache, default false

**Outputs:**
- `image_tag` (e.g., dev-a1b2c3d)

**Jobs:**
1. **build-and-push-api**: Docker build → smoke test → Trivy scan (BLOCKS on HIGH/CRITICAL) → push to ACR
2. **build-frontend**: npm build → upload artifact (7-day retention)

**Called by:** dev-deploy.yml, weekly-rebuild.yml

---

### 3. dev-deploy.yml

**Triggers:** PR to dev (lint/test only), push to dev (full deploy), workflow_call

**Flow:**
```
PR:     lint-and-test → ✅
Push:   lint-and-test → build-and-push → deploy → integration-tests
```

**Deploy job:**
- API: Deploy to Container Apps using `CONTAINER_APP_NAME_DEV`
- Frontend: Download artifact → deploy to Static Web Apps
- Uses GitHub variables (no Terraform queries)

---

### 4. prod-deploy.yml

**Triggers:** PR to main (lint/test only), push to main (promote + deploy), workflow_call

**Flow:**
```
PR:     lint-and-test → ✅
Push:   lint-and-test → promote-images → deploy (with approval gate)
```

**promote-images job:**
- Pull `dev-{sha}` image
- Retag as `prod-{sha}` and `prod-latest`
- Push to ACR

**deploy job:**
- Requires manual approval (GitHub Environment: production)
- Deploy retagged image (same as tested in dev)
- Download frontend artifact from dev build
- No rebuilds

---

### 5. infra.yml (Reusable)

**Triggers:** Push to dev/main when `infra/**` changes, workflow_call, workflow_dispatch

**Inputs:**
- `environment` (dev/prod) - required for workflow_call/dispatch

**Flow:**
```
Push to dev:    terraform → auto-apply to dev
Push to main:   terraform → approval gate → apply to prod
workflow_call:  terraform → apply to specified environment
```

**How it works:**
- Auto-derives environment from branch on push (dev branch → dev env, main branch → prod env)
- Accepts explicit environment input when called from other workflows
- Single terraform job with conditional environment detection

**Why separate from app deployments:**
- Code deploys don't wait for Terraform
- Hotfixes can deploy without touching infrastructure
- Clear audit trail

---

### 6. weekly-rebuild.yml

**Triggers:** Schedule (Sunday 6 AM UTC), manual dispatch

**Purpose:** Pull fresh base images for security updates

**Flow:**
```
dev-deploy (force_rebuild: true) → approval gate → prod-deploy
```

Builds with `--no-cache --pull` to get latest security patches.

---

## Workflow Summary

| Workflow | Type | Triggers |
|----------|------|----------|
| `lint-and-test.yml` | Reusable | Called by dev/prod |
| `build-and-push.yml` | Reusable | Called by dev/weekly |
| `infra.yml` | Reusable | Push to dev/main (infra/**), workflow_call |
| `dev-deploy.yml` | Deploy | PR/push to dev |
| `prod-deploy.yml` | Deploy | PR/push to main |
| `weekly-rebuild.yml` | Scheduled | Sunday 6 AM UTC |

---

## Developer Workflow

**Feature Development:**
```
1. Create feature branch from dev
2. Develop locally (docker compose up)
3. Open PR → dev (triggers lint/test)
4. Merge → auto-deploy to rg-ltc-dev
5. Merge dev → main → promote to rg-ltc-prod
```

**Infrastructure Changes:**
```
1. Modify infra/** on dev branch
2. Merge to dev → auto-apply to rg-ltc-dev
3. Verify in dev
4. Merge to main → approval → apply to rg-ltc-prod
```

---

## GitHub Variables

**Repository → Settings → Actions → Variables**

| Variable | Purpose | Example |
|----------|---------|---------|
| `CONTAINER_REGISTRY_NAME` | ACR name | acrltc |
| `CONTAINER_REGISTRY_ENDPOINT` | ACR endpoint | acrltc.azurecr.io |
| `CONTAINER_APP_NAME_DEV/PROD` | Container App names | ca-ltc-api-dev |
| `API_URL_DEV/PROD` | API URLs | ca-ltc-api-dev.northeurope.azurecontainerapps.io |
| `FRONTEND_URL_DEV/PROD` | Frontend URLs | {swa}.azurestaticapps.net |
| `AZURE_RESOURCE_GROUP_DEV/PROD` | Resource groups | rg-ltc-dev |

**Secrets:**
- `AZURE_CREDENTIALS`, `CLERK_*`, `GOOGLE_API_KEY`, `SWA_DEPLOYMENT_TOKEN_DEV/PROD`

---

## Security & Operations

**Security Scanning:**
- Trivy runs on every build
- HIGH/CRITICAL vulnerabilities BLOCK deployments
- `trivy image --exit-code 1 --severity HIGH,CRITICAL`

**Concurrency:**
- `group: deploy-dev` / `deploy-prod` / `infra-{environment}`
- Prevents conflicts, queues sequential deployments

**Migrations:**
- Auto-run on container startup (`RUN_MIGRATIONS_ON_STARTUP=true`)
- Alembic handles race conditions with DB locks

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Build fails | Check logs, try force rebuild |
| Trivy blocks deploy | Update base image/deps in Dockerfile |
| Terraform state lock | Wait for other deployment or `terraform force-unlock` |
| Health check fails | `az containerapp logs show --follow` |
| Artifact not found | 7-day retention, redeploy to dev if expired |
| Workflow won't trigger | Check `paths-ignore` (infra/docs ignored for code deploys) |

**Rollback:**
```bash
# App rollback
az containerapp update --image {registry}/api:prod-{previous-sha}

# Infra rollback
git checkout {previous-commit} -- main.tf && terraform apply
```
