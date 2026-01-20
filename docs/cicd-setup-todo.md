# CI/CD Setup Checklist

## 1. GitHub Repository Variables

**Repository → Settings → Secrets and variables → Actions → Variables**

- `AZURE_LOCATION`
- `AZURE_SUBSCRIPTION_ID`
- `CONTAINER_REGISTRY_NAME`
- `CONTAINER_REGISTRY_ENDPOINT`
- `AZURE_RESOURCE_GROUP_DEV`
- `CONTAINER_APP_NAME_DEV`
- `API_URL_DEV`
- `FRONTEND_URL_DEV`
- `FRONTEND_CUSTOM_DOMAIN_DEV` (optional)
- `AZURE_RESOURCE_GROUP_PROD`
- `CONTAINER_APP_NAME_PROD`
- `API_URL_PROD`
- `FRONTEND_URL_PROD`
- `FRONTEND_CUSTOM_DOMAIN_PROD` (optional)

---

## 2. GitHub Repository Secrets

**Repository → Settings → Secrets and variables → Actions → Secrets**

- `AZURE_CREDENTIALS`
- `CLERK_SECRET_KEY`
- `CLERK_PUBLISHABLE_KEY`
- `CLERK_WEBHOOK_SIGNING_SECRET`
- `GOOGLE_API_KEY`
- `CTF_MASTER_SECRET`
- `SWA_DEPLOYMENT_TOKEN_DEV`
- `SWA_DEPLOYMENT_TOKEN_PROD`

---

## 3. GitHub Environments

**Repository → Settings → Environments**

### Create "production" Environment

1. Click **New environment**
2. Name: `production`
3. Add protection rules:
   - **Required reviewers**: Add yourself/team members
   - **Deployment branches**: Select `main` only

**After creating the environment**, uncomment these lines:
- [prod-deploy.yml](../.github/workflows/prod-deploy.yml) line 94: `# environment: production`
- [infra.yml](../.github/workflows/infra.yml) line 35: `environment: ${{ ... && 'production' || '' }}`

