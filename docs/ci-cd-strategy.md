# CI/CD and Branching Strategy

## Architecture Overview

```
feature-branch ──PR──▶ dev ──merge──▶ main
                       │                │
                       ▼                ▼
                  rg-ltc-dev       rg-ltc-prod
                  (auto-deploy)    (merge-to-main)
                  dev-{sha}        prod-{sha}
```

## Key Principles

1. **Separation of Concerns**: Code deployments (`api/**`, `frontend/**`) and infrastructure changes (`infra/**`) run independently
2. **Build Once, Promote**: Images built in dev, tested, then retagged for prod (no rebuilds)
3. **Composable Workflows**: Reusable building blocks (workflows + actions)
4. **Reusable Actions**: `setup-azure-env` and `deploy-api` eliminate duplication across workflows
5. **GitHub Variables**: Static resource names/URLs stored as repo variables (faster than Terraform queries)
6. **Ephemeral Dev**: Dev environment spins up on demand, tears down after approval (cost optimization)

## Branch Strategy

| Branch | Environment | Trigger | Approval |
|--------|-------------|---------|----------|
| `dev` | rg-ltc-dev | Auto on merge | None |
| `main` | rg-ltc-prod | Auto on merge | Merge to main |

---

## Reusable Actions

### 1. setup-azure-env (Action)

**Purpose:** Configure Azure credentials and environment variables (DRY principle)

**Inputs:**
- `environment` (dev/prod) - required

**What it does:**
- Uses Azure OIDC (no long‑lived credentials)
- Sets environment-specific vars: `AZURE_RESOURCE_GROUP`, `CONTAINER_APP_NAME`, `API_URL`, etc.
- Exports Terraform vars: `TF_VAR_*`, `ARM_*`
- Eliminates 40+ lines of duplicate env var configuration
 - Secrets for Terraform are injected at step-level (not global env)

**Used by:** infra-apply.yml, infra-destroy.yml, dev-deploy.yml, prod-deploy.yml

---

### 2. deploy-api (Action)

**Purpose:** Deploy API container to Azure Container Apps (DRY principle)

**Inputs:**
- `environment` (dev/prod) - required
- `image-tag` - required (e.g., dev-a1b2c3d)

**What it does:**
- Azure CLI login
- Deploy API image to Container Apps with environment-specific settings
- Wait for API `/ready` endpoint (30 retries, 10s intervals)
- Handles custom domains elegantly
- Eliminates 40+ lines of duplicate deployment code

**Used by:** dev-deploy.yml, prod-deploy.yml (deploy jobs)

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

**Triggers:** PR to dev (lint/test only), push to dev and workflow_call (full deploy)

**Flow:**
```
STAGE 1: Validation
PR/Push/Call: lint-and-test

STAGE 2: Infrastructure
Push/Call: create-infra (terraform apply)

STAGE 3: Build
Push/Call: build-and-push

STAGE 4: Deployment
Push/Call: deploy (setup-azure-env → deploy-api + frontend)

STAGE 5: Approval & Teardown
Push/Call: approval-gate (12h manual approval) → destroy-infra (terraform destroy)
```

**Key features:**
- Ephemeral dev environment (spins up on push, destroys after approval)
- Uses `setup-azure-env` + `deploy-api` actions (no env var duplication)
- Reduces costs by destroying infrastructure after testing

---

### 4. prod-deploy.yml

**Triggers:** PR to main (lint/test only), push to main (promote + deploy), workflow_call

**Flow:**
```
STAGE 1: Validation
PR/Push: lint-and-test

STAGE 2: Build & Promote
Push:    promote-images (pull dev-{sha} → retag prod-{sha})

STAGE 3: Deployment
Push:    deploy (setup-azure-env → deploy-api + frontend)
```

**promote-images job:**
- Pull `dev-{sha}` image (tested in dev)
- Retag as `prod-{sha}` and `prod-latest`
- Push to ACR

**deploy job:**
- Uses `setup-azure-env` + `deploy-api` actions
- Deploy retagged image (same as tested in dev)
- Download frontend artifact from dev build
- **No rebuilds** - promotes tested artifacts only

---

### 5. infra-apply.yml (Reusable)

**Triggers:** workflow_call

**Inputs:**
- `environment` (dev/prod) - required
- `rollback_ref` (tag/commit) - optional, default `infra-prod-stable`

**Flow:**
```
workflow_call: terraform plan → apply to specified environment
```

**How it works:**
- Uses `setup-azure-env` action to configure all vars and credentials
- Requires explicit `environment` input (no branch inference)
- Single terraform job focused on apply only
- If post-apply health checks fail in prod, it rolls back by re-applying `rollback_ref`

**Why separate from app deployments:**
- Code deploys don't wait for Terraform
- Hotfixes can deploy without touching infrastructure
- Clear audit trail for infra changes

---

### 6. infra-destroy.yml (Reusable)

**Triggers:** workflow_call

**Inputs:**
- `environment` (dev/prod) - required

**Flow:**
```
workflow_call: terraform destroy for specified environment
```

**How it works:**
- Uses `setup-azure-env` action to configure all vars and credentials
- Requires explicit `environment` input (no branch inference)
- Single terraform job focused on destroy only

---

### 7. weekly-rebuild.yml

**Triggers:** Schedule (Sunday 6 AM UTC), manual dispatch

**Purpose:** Pull fresh base images for security updates

**Flow:**
```
dev-deploy (force_rebuild: true) → approval gate → prod-deploy
```

Builds with `--no-cache --pull` to get latest security patches.

---

## Workflow Summary

| Component | Type | Purpose |
|-----------|------|---------|
| `setup-azure-env` | Reusable Action | Configure Azure env vars + credentials |
| `deploy-api` | Reusable Action | Deploy API container + health checks |
| `lint-and-test.yml` | Reusable Workflow | Code quality checks |
| `build-and-push.yml` | Reusable Workflow | Build images + security scan |
| `infra-apply.yml` | Reusable Workflow | Terraform apply |
| `infra-destroy.yml` | Reusable Workflow | Terraform destroy |
| `dev-deploy.yml` | Deploy Workflow | Ephemeral dev: create → test → approve → destroy |
| `prod-deploy.yml` | Deploy Workflow | Persistent prod: promote → deploy with approval |
| `weekly-rebuild.yml` | Scheduled Workflow | Sunday 6 AM UTC: rebuild + weekly redeploy |

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
