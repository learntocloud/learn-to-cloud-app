# Infrastructure

Terraform configuration for Learn to Cloud app on Azure Container Apps.

## Resources Created

- **Resource Group**: `rg-learntocloud-{env}`
- **Container Registry**: ACR for Docker images
- **PostgreSQL Flexible Server**: Database
- **Container Apps Environment**: Hosting environment
- **Container Apps**: API and Frontend apps
- **Log Analytics + App Insights**: Monitoring

## Quick Start

```bash
cd infra
terraform init
terraform validate
terraform apply
```

## Push Images

After Terraform creates the registry, push your images:

```bash
# Login to ACR
az acr login --name $(terraform output -raw container_registry | cut -d. -f1)

# Build and push API (from repo root, includes content folder)
cd ..
docker build -f api/Dockerfile -t $(terraform output -raw container_registry)/ltc-api:latest .
docker push $(terraform output -raw container_registry)/ltc-api:latest

# Build and push Frontend
docker build -t $(terraform output -raw container_registry)/ltc-frontend:latest \
  --build-arg VITE_CLERK_PUBLISHABLE_KEY=your_key \
  --build-arg VITE_API_URL=$(terraform output -raw api_url) \
  frontend
docker push $(terraform output -raw container_registry)/ltc-frontend:latest
cd infra
```

## Files

- `main.tf` - All resources in one file
- `variables.tf` - Input variables
- `outputs.tf` - Output values
- `terraform.tfvars` - Variable values (do not commit secrets!)
