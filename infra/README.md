# Learn to Cloud - Terraform Infrastructure

This directory contains the Terraform infrastructure-as-code for the Learn to Cloud application.

## Architecture

The infrastructure is organized into modular Terraform modules:

- **foundation** - Resource Group and unique naming suffix
- **identity** - User-Assigned Managed Identity for Key Vault access
- **observability** - Log Analytics Workspace and Application Insights
- **database** - PostgreSQL Flexible Server, database, and firewall rules
- **cache** - Azure Cache for Redis (optional, for distributed rate limiting)
- **secrets** - Key Vault, secrets storage, and RBAC
- **registry** - Azure Container Registry and ACR Pull role assignments
- **container-apps** - Container Apps Environment, API app, and Frontend app
- **monitoring** - Action Groups and Metric Alerts

## Prerequisites

- [Terraform](https://www.terraform.io/downloads) >= 1.5.0
- [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli) >= 2.50.0
- [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
- Azure subscription with appropriate permissions

## Quick Start

1. **Login to Azure**:
   ```bash
   az login
   azd auth login
   ```

2. **Setup Terraform backend** (first time only):
   ```bash
   cd infra/scripts
   ./setup-backend.sh
   # Save the ARM_ACCESS_KEY output
   export ARM_ACCESS_KEY="<key-from-output>"
   cd ..
   ```

3. **Configure variables**:
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your values
   ```

4. **Deploy with azd** (recommended):
   ```bash
   azd up
   ```

   Or manually with Terraform:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

## Using with Azure Developer CLI (azd)

The infrastructure is fully integrated with `azd`:

```bash
# Provision infrastructure
azd provision

# Deploy applications
azd deploy api
azd deploy frontend

# Full deployment (provision + deploy)
azd up
```

The `azd` commands automatically run Terraform via hooks defined in `azure.yaml`.

## Configuration

### terraform.tfvars

Copy `terraform.tfvars.example` to `terraform.tfvars` and configure:

| Variable | Description | Required |
|----------|-------------|----------|
| `environment` | Environment name (dev, staging, prod) | Yes |
| `location` | Azure region | Yes |
| `postgres_admin_password` | PostgreSQL admin password | Yes |
| `clerk_secret_key` | Clerk secret key | Yes |
| `clerk_webhook_signing_secret` | Clerk webhook signing secret | Yes |
| `clerk_publishable_key` | Clerk publishable key | Yes |
| `enable_redis` | Enable Redis cache | No (default: true) |
| `frontend_custom_domain` | Custom domain for frontend | No |
| `alert_email_address` | Email for alerts | No |
| `google_api_key` | Google API key for AI features | No |

### Environment Variables

Alternatively, use environment variables:

```bash
export ARM_SUBSCRIPTION_ID="<subscription-id>"
export ARM_ACCESS_KEY="<storage-account-key>"

# Or use TF_VAR_ prefix for Terraform variables
export TF_VAR_postgres_admin_password="<password>"
export TF_VAR_clerk_secret_key="sk_live_..."
```

## Outputs

After deployment, Terraform provides these outputs:

| Output | Description |
|--------|-------------|
| `AZURE_RESOURCE_GROUP` | Resource group name |
| `AZURE_LOCATION` | Azure region |
| `apiUrl` | API Container App URL |
| `frontendUrl` | Frontend Container App URL |
| `postgresHost` | PostgreSQL server FQDN |
| `keyVaultName` | Key Vault name |
| `keyVaultUri` | Key Vault URI |
| `AZURE_CONTAINER_REGISTRY_NAME` | Container Registry name |
| `AZURE_CONTAINER_REGISTRY_ENDPOINT` | Container Registry login server |

## Troubleshooting

### State Lock Error

```bash
# Break lease on Azure Storage blob
az storage blob lease break \
  --account-name <storage-account> \
  --container-name tfstate \
  --blob-name <state-file>.tfstate
```

### Drift Detection

```bash
# Check for configuration drift
terraform plan

# Refresh state from Azure
terraform refresh
```

### Resource Import

If a resource exists in Azure but not in Terraform state:

```bash
terraform import <resource-address> <azure-resource-id>
```

## Security Best Practices

1. **Never commit secrets**: `terraform.tfvars` is in `.gitignore`
2. **Use Key Vault**: Secrets are stored in Azure Key Vault
3. **State encryption**: Backend uses Azure Storage encryption
4. **Rotate secrets**: Regularly rotate Clerk keys and database passwords
5. **Review RBAC**: Ensure minimal required permissions

## Additional Resources

- [Terraform Azure Provider Docs](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Azure Developer CLI Docs](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/)
- [Azure Container Apps Docs](https://learn.microsoft.com/en-us/azure/container-apps/)
