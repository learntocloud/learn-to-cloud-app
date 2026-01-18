# Infrastructure as Code (IaC)

This document describes the Azure infrastructure managed by Terraform in the `infra/` directory.

## Overview

All infrastructure is defined in Terraform and deployed to Azure. Resources follow the naming convention `{prefix}-ltc-{component}-{environment}` with a random suffix for uniqueness where required.

## Resource Groups

| Resource | Name Pattern | Purpose |
|----------|--------------|---------|
| Resource Group | `rg-ltc-{env}` | Contains all application resources |
| Terraform State RG | `rg-terraform-state` | Stores Terraform state (created manually) |

## Compute Resources

### Container Apps

| Resource | Name Pattern | Description |
|----------|--------------|-------------|
| Container App Environment | `cae-ltc-{env}` | Shared environment for container apps |
| API Container App | `ca-ltc-api-{env}` | FastAPI backend application |

**API Container App Configuration:**
- CPU: 0.5 cores
- Memory: 1Gi
- Replicas: 1-3 (auto-scaling)
- Health probes: liveness, readiness, startup (all on `/health`)

### Static Web App

| Resource | Name Pattern | Description |
|----------|--------------|-------------|
| Static Web App | `swa-ltc-frontend-{env}` | React frontend with global CDN |
| Backend Link | `api` | Links SWA to Container App for `/api/*` routes |

**Static Web App Configuration:**
- Tier: Standard (required for backend linking)
- Custom domain: Configurable via `frontend_custom_domain` variable

## Database

| Resource | Name Pattern | Description |
|----------|--------------|-------------|
| PostgreSQL Flexible Server | `psql-ltc-{env}-{suffix}` | Primary database |
| Database | `learntocloud` | Application database |
| Firewall Rule | `AllowAzureServices` | Allows Azure service access |

**PostgreSQL Configuration:**
- Version: 16
- SKU: B_Standard_B1ms (burstable, 1 vCore)
- Storage: 32GB
- Backup retention: 7 days
- Authentication: Entra ID only (no password auth)
- Public network access: Enabled (secured by firewall rules)

## Identity & Access

| Resource | Name Pattern | Description |
|----------|--------------|-------------|
| User Assigned Identity | `id-ltc-api-{env}` | Managed identity for API |
| Entra Admin | - | API identity as PostgreSQL admin |

The API uses a managed identity for passwordless database access via Entra ID authentication.

## Container Registry

| Resource | Name Pattern | Description |
|----------|--------------|-------------|
| Container Registry | `crltc{suffix}` | Stores API container images |

**Configuration:**
- SKU: Basic
- Admin enabled: Yes (for Container App pull)

## Observability

### Logging & Telemetry

| Resource | Name Pattern | Description |
|----------|--------------|-------------|
| Log Analytics Workspace | `log-ltc-{env}-{suffix}` | Centralized logging |
| Application Insights | `appi-ltc-{env}-{suffix}` | APM and telemetry |

**Configuration:**
- Log retention: 30 days
- Application type: Web

### Monitoring & Alerting

| Resource | Name Pattern | Description |
|----------|--------------|-------------|
| Action Group | `ag-ltc-critical-{env}` | Email notification target |
| Dashboard | `dash-ltc-{env}` | Azure Portal monitoring dashboard |

**Alerts (see [alerting-strategy.md](alerting-strategy.md) for details):**

| Alert | Severity | Trigger |
|-------|----------|---------|
| API 5xx Errors | Sev1 | Any 5xx response |
| Container Restarts | Sev1 | Any restart |
| API High CPU | Sev2 | >80% for 15 min |
| API High Memory | Sev2 | >80% for 15 min |
| API High Latency | Sev2 | >2s avg response |
| DB Connection Failures | Sev1 | Any failure |
| DB Storage | Sev2 | >80% used |
| DB High CPU | Sev2 | >80% for 15 min |
| Failure Anomalies | Sev3 | AI-detected anomalies |

## Variables

### Required Variables

| Variable | Description |
|----------|-------------|
| `subscription_id` | Azure subscription ID |
| `clerk_publishable_key` | Clerk authentication public key |
| `clerk_secret_key` | Clerk authentication secret key |
| `clerk_webhook_signing_secret` | Clerk webhook verification secret |
| `google_api_key` | Google API key for Gemini LLM |
| `ctf_master_secret` | CTF flag generation secret |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `environment` | `dev` | Environment name (dev, staging, prod) |
| `location` | `centralus` | Azure region |
| `frontend_custom_domain` | `""` | Custom domain for frontend |
| `alert_email` | `learntocloudguide@gmail.com` | Alert notification email |

## Outputs

| Output | Description |
|--------|-------------|
| `resource_group_name` | Resource group name |
| `api_url` | API container app URL |
| `frontend_url` | Static web app URL |
| `container_registry` | Container registry login server |
| `database_host` | PostgreSQL FQDN |
| `dashboard_url` | Azure Portal dashboard URL |
| `swa_deployment_token` | SWA deployment token (sensitive) |

## Deployment

### Prerequisites

1. Azure CLI installed and authenticated
2. Terraform >= 1.5.0
3. Terraform state storage account created

### Commands

```bash
cd infra

# Initialize Terraform
terraform init

# Preview changes
terraform plan -out=tfplan

# Apply changes
terraform apply tfplan

# Destroy (use with caution)
terraform destroy
```

### CI/CD Integration

Infrastructure changes are applied via GitHub Actions:
1. Push to `main` triggers the deploy workflow
2. Workflow runs `terraform apply` with auto-approve
3. Container image is built and pushed to ACR
4. Container App is updated with new image
5. Frontend is deployed to Static Web App

See [ci-cd.md](ci-cd.md) for full workflow documentation.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Azure (rg-ltc-dev)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐     ┌─────────────────────────────────────────────┐   │
│  │  Static Web App │     │        Container App Environment            │   │
│  │  (Frontend)     │────▶│  ┌─────────────────────────────────────┐   │   │
│  │                 │     │  │      API Container App              │   │   │
│  │  - React SPA    │     │  │      - FastAPI                      │   │   │
│  │  - Global CDN   │     │  │      - Managed Identity             │   │   │
│  └─────────────────┘     │  │      - Auto-scaling (1-3 replicas)  │   │   │
│                          │  └─────────────────────────────────────┘   │   │
│                          └─────────────────────────────────────────────┘   │
│                                           │                                 │
│                                           │ Entra ID Auth                   │
│                                           ▼                                 │
│  ┌─────────────────┐     ┌─────────────────────────────────────────────┐   │
│  │ Container       │     │     PostgreSQL Flexible Server             │   │
│  │ Registry        │     │     - Version 16                           │   │
│  │                 │     │     - Entra ID auth only                   │   │
│  │ - API images    │     │     - 32GB storage                         │   │
│  └─────────────────┘     └─────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Observability                                │   │
│  │  ┌─────────────┐  ┌──────────────────┐  ┌─────────────────────┐    │   │
│  │  │ Log         │  │ Application      │  │ Alerts & Dashboard  │    │   │
│  │  │ Analytics   │◀─│ Insights         │──│ - 9 alert rules     │    │   │
│  │  │             │  │ - APM            │  │ - 6-panel dashboard │    │   │
│  │  └─────────────┘  └──────────────────┘  └─────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```
