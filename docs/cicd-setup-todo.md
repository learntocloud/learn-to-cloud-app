# CI/CD Setup (Short)

## 1) Env Variables (dev + production)
Set in **Settings → Environments → Variables**

Common:
- `AZURE_LOCATION`
- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `CONTAINER_REGISTRY_NAME`
- `CONTAINER_REGISTRY_ENDPOINT`

Dev:
- `AZURE_RESOURCE_GROUP_DEV`
- `CONTAINER_APP_NAME_DEV`
- `API_URL_DEV`
- `FRONTEND_URL_DEV`
- `FRONTEND_CUSTOM_DOMAIN_DEV` (optional)

Prod:
- `AZURE_RESOURCE_GROUP_PROD`
- `CONTAINER_APP_NAME_PROD`
- `API_URL_PROD`
- `FRONTEND_URL_PROD`
- `FRONTEND_CUSTOM_DOMAIN_PROD` (optional)

## 2) Secrets (dev + production)
Common:
- `CLERK_SECRET_KEY`
- `CLERK_PUBLISHABLE_KEY`
- `CLERK_WEBHOOK_SIGNING_SECRET`
- `GOOGLE_API_KEY`
- `CTF_MASTER_SECRET`

Dev:
- `SWA_DEPLOYMENT_TOKEN_DEV`

Prod:
- `SWA_DEPLOYMENT_TOKEN_PROD`

## 3) Optional Environments
Create `dev` / `production` only if you want extra protection beyond merge‑to‑main.

## 4) TODO (Tests + Health)
- Implement post‑apply health checks (prod infra)
- Implement integration tests (include Azure PostgreSQL)
- Implement E2E tests
- Implement performance tests

## 5) TODO (Security)
- Configure Azure OIDC federated credentials for GitHub Actions
- Protect `infra-prod-stable` rollback tag (immutable/protected)
- (Optional) Add GitHub Environment protection for prod
