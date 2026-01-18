# CI/CD Pipeline

This document explains how the GitHub Actions workflows deploy the Learn to Cloud application to Azure.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          GitHub Actions                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   infra.yml                    deploy.yml              weekly-rebuild.yml│
│   ─────────                    ──────────              ──────────────────│
│   Terraform plan + apply       Build & deploy app     Calls deploy.yml   │
│   (infra/** changes)           (all other changes)    (no cache)         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              Azure                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│   │ Container        │    │ Container Apps   │    │ Static Web Apps  │  │
│   │ Registry (ACR)   │───▶│ (API)            │◀───│ (Frontend)       │  │
│   └──────────────────┘    └──────────────────┘    └──────────────────┘  │
│                                    │                                     │
│                                    ▼                                     │
│                           ┌──────────────────┐                           │
│                           │ PostgreSQL       │                           │
│                           │ Flexible Server  │                           │
│                           └──────────────────┘                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Workflows

### 1. deploy.yml — Main Deployment

**Triggers:**
- Push to `main` (except `infra/**` changes)
- Pull requests to `main` (lint/test only, no deploy)
- Manual dispatch
- Called by `weekly-rebuild.yml`

**Jobs:**

| Job | Purpose | Runs On |
|-----|---------|---------|
| `api-lint-and-test` | Ruff lint, type check, unit tests | All triggers |
| `frontend-lint-and-test` | ESLint, Vitest, build check | All triggers |
| `terraform` | Read Terraform outputs | Main branch only |
| `deploy` | Build/push API image, deploy to Azure | Main branch only |

**Pipeline Flow:**

```
┌─────────────────┐     ┌─────────────────────┐
│ api-lint-and-   │     │ frontend-lint-and-  │
│ test            │     │ test                │
└────────┬────────┘     └──────────┬──────────┘
         │                         │
         └───────────┬─────────────┘
                     ▼
              ┌──────────────┐
              │  terraform   │  (reads outputs only)
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │   deploy     │
              └──────────────┘
```

**Deploy Job Steps:**
1. Pull existing API image (cache warming)
2. Build new API image with git commit labels
3. Push to Azure Container Registry (`:sha` and `:latest` tags)
4. Smoke test the image locally
5. Security scan with Trivy
6. Update Container App with new image
7. Wait for API readiness (`/ready` endpoint)
8. Build frontend with Vite
9. Deploy frontend to Static Web Apps

### 2. infra.yml — Infrastructure Changes

**Triggers:**
- Push to `main` with changes in `infra/**`
- Manual dispatch

**Purpose:** Apply Terraform changes to Azure infrastructure.

**Why Separate?**
- Infrastructure changes are riskier and less frequent
- Avoids race conditions with `deploy.yml` reading stale Terraform outputs
- Clearer audit trail for infrastructure modifications
- Can add approval gates independently

**Steps:**
1. Terraform init
2. Terraform validate
3. Terraform plan (with retry logic for state locks)
4. Terraform apply (on push or manual with `apply=true`)

### 3. weekly-rebuild.yml — Security Updates

**Triggers:**
- Scheduled: Every Sunday at 6 AM UTC
- Manual dispatch

**Purpose:** Rebuild all container images without cache to pull:
- Base image updates (python:3.13-slim)
- System package security patches (apt-get upgrade)
- Fresh dependency resolution

**How It Works:**
```yaml
uses: ./.github/workflows/deploy.yml
with:
  force_rebuild: true  # Adds --no-cache --pull to docker build
```

## Content Deployment

Content files in `frontend/public/content/` are:
1. **Served by the frontend** via Static Web Apps CDN
2. **Baked into the API image** at build time (see [content-strategy.md](content-strategy.md))

This means content changes trigger a full deployment to keep both components in sync. The API needs content for server-side validation and LLM grading.

## Concurrency Control

| Workflow | Concurrency Group | Cancel In-Progress |
|----------|-------------------|-------------------|
| deploy.yml | `deploy-{env}` | No (waits in queue) |
| infra.yml | `infra-{env}` | No (waits in queue) |

`cancel-in-progress: false` ensures Terraform operations complete and release state locks properly.

## Required Secrets

| Secret | Description |
|--------|-------------|
| `AZURE_CREDENTIALS` | Service principal JSON with tenantId, clientId, clientSecret |
| `SWA_DEPLOYMENT_TOKEN` | Static Web App deployment token (`terraform output -raw swa_deployment_token`) |
| `CLERK_PUBLISHABLE_KEY` | Clerk frontend key (used in Vite build) |
| `CLERK_SECRET_KEY` | Clerk backend key (Terraform variable) |
| `CLERK_WEBHOOK_SIGNING_SECRET` | Clerk webhook verification |
| `GOOGLE_API_KEY` | Google/Gemini API key for LLM grading |
| `CTF_MASTER_SECRET` | Secret for CTF flag generation |

## Required Repository Variables

| Variable | Description |
|----------|-------------|
| `AZURE_ENV_NAME` | Environment name (e.g., `prod`) |
| `AZURE_LOCATION` | Azure region (e.g., `eastus`) |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription GUID |
| `FRONTEND_CUSTOM_DOMAIN` | Custom domain (e.g., `app.learntocloud.guide`) |

## Manual Operations

### Force Rebuild (Security Update)

```bash
# Via GitHub CLI
gh workflow run weekly-rebuild.yml

# Or trigger deploy.yml with force_rebuild
gh workflow run deploy.yml -f force_rebuild=true
```

### Apply Infrastructure Only

```bash
gh workflow run infra.yml -f apply=true
```

### Redeploy Without Code Changes

```bash
gh workflow run deploy.yml
```

## Troubleshooting

### Terraform State Lock

If you see "Error acquiring the state lock", wait for the other workflow to complete or check Azure Storage for stale locks. The workflows have retry logic with 120s lock timeout.

### API Not Ready

The deploy job waits up to 5 minutes for `/ready` to return 200. Check Container Apps logs:

```bash
az containerapp logs show \
  --name ca-ltc-api-prod \
  --resource-group rg-ltc-prod \
  --type console
```

### Trivy Vulnerabilities

Security scans warn but don't block deployment. Review the scan output and consider:
- Updating base image
- Running `force_rebuild=true` to pull latest patches
- Checking if vulnerabilities are exploitable in your context
