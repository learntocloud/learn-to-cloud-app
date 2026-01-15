# Learn to Cloud - Terraform Infrastructure

This directory contains the Terraform infrastructure-as-code for the Learn to Cloud application, migrated from Azure Bicep.

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

## Quick Start (New Deployment)

1. **Login to Azure**:
   ```bash
   az login
   azd auth login
   ```

2. **Setup Terraform backend**:
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

4. **Deploy infrastructure**:
   ```bash
   azd up
   # Or manually:
   terraform init
   terraform plan
   terraform apply
   ```

## Importing Existing Bicep Resources

If you're migrating from Bicep, follow these steps to import existing resources:

### Step 1: Extract Resource IDs

```bash
cd infra/scripts
./export-bicep-state.sh dev
# This creates import-map-dev.json with all resource IDs
```

### Step 2: Update terraform.tfvars

```bash
cd ..
cp terraform.tfvars.example terraform.tfvars

# IMPORTANT: Set the existing_unique_suffix
# Get it from: jq -r '.unique_suffix' scripts/import-map-dev.json
# Add to terraform.tfvars:
existing_unique_suffix = "abc123def456g"
```

### Step 3: Initialize Terraform

```bash
terraform init
```

### Step 4: Import Resources (Phase by Phase)

Follow the detailed import steps in the migration plan:

**Phase 1: Foundation** (Low risk)
```bash
ENVIRONMENT=dev
UNIQUE_SUFFIX=$(jq -r '.unique_suffix' scripts/import-map-${ENVIRONMENT}.json)

# Import unique suffix
terraform import random_string.unique_suffix "$UNIQUE_SUFFIX"

# Import resource group
terraform import \
  -var="environment=$ENVIRONMENT" \
  module.foundation.azurerm_resource_group.main \
  "/subscriptions/<sub-id>/resourceGroups/rg-learntocloud-$ENVIRONMENT"

# Verify no drift
terraform plan -target=module.foundation
```

**Phase 2-7**: Continue with database, cache, secrets, registry, container-apps, and monitoring

See `/Users/rishabkumar/.claude/plans/eventual-dancing-goose.md` for complete import commands.

### Step 5: Validate Parity

```bash
terraform plan -detailed-exitcode
# Exit code 0 = success (no changes)
# Exit code 2 = drift detected (must fix)
```

## Using with Azure Developer CLI (azd)

The infrastructure is fully integrated with `azd`:

```bash
# Provision infrastructure
azd provision

# Deploy applications
azd deploy api
azd deploy frontend

# Full deployment
azd up
```

The `azd` commands automatically run Terraform via hooks defined in `azure.yaml`.

## Environment Variables

Required environment variables:

```bash
# Azure configuration (set by azd)
export AZURE_ENV_NAME=dev
export AZURE_LOCATION=eastus
export AZURE_SUBSCRIPTION_ID=xxx

# Secrets (set manually or via .azure/<env>/.env)
export TF_VAR_postgres_admin_password="<password>"
export TF_VAR_clerk_secret_key="sk_test_..."
export TF_VAR_clerk_webhook_signing_secret="whsec_..."
export TF_VAR_clerk_publishable_key="pk_test_..."

# Optional
export TF_VAR_frontend_custom_domain="app.example.com"
export TF_VAR_alert_email_address="alerts@example.com"
export TF_VAR_enable_redis=true

# Backend authentication
export ARM_ACCESS_KEY="<storage-account-key>"
```

## Outputs

After deployment, Terraform provides these outputs (compatible with `azd`):

- `AZURE_RESOURCE_GROUP` - Resource group name
- `AZURE_LOCATION` - Azure region
- `apiUrl` - API Container App URL
- `frontendUrl` - Frontend Container App URL
- `postgresHost` - PostgreSQL server FQDN
- `keyVaultName` - Key Vault name
- `keyVaultUri` - Key Vault URI
- `AZURE_CONTAINER_REGISTRY_NAME` - Container Registry name
- `AZURE_CONTAINER_REGISTRY_ENDPOINT` - Container Registry login server

## Helper Scripts

Located in `scripts/`:

- `setup-backend.sh` - Create Azure Storage for Terraform state
- `export-bicep-state.sh` - Extract resource IDs from existing Bicep deployment
- `rollback.sh` - Emergency rollback to Bicep (if needed)

## Troubleshooting

### Import Issues

**Problem**: Resource already managed by Terraform
```bash
# Solution: Remove from state, then re-import
terraform state rm <resource-address>
terraform import <resource-address> <resource-id>
```

**Problem**: Drift detected after import
```bash
# Solution: Review differences
terraform plan
# Adjust Terraform code to match Azure, or use lifecycle ignore_changes
```

### State Issues

**Problem**: State lock error
```bash
# Solution: Break lease on Azure Storage blob
az storage blob lease break \
  --account-name <storage-account> \
  --container-name tfstate \
  --blob-name <state-file>.tfstate
```

**Problem**: Lost state file
```bash
# Solution: Restore from Azure Storage version history
az storage blob list \
  --account-name <storage-account> \
  --container-name tfstate \
  --include v
```

## Security Best Practices

1. **Never commit secrets**: Use `.gitignore` to exclude `terraform.tfvars`
2. **Use Key Vault**: Store secrets in Azure Key Vault, not in tfvars
3. **Enable state encryption**: Backend uses Azure Storage encryption by default
4. **Rotate secrets**: Regularly rotate Clerk keys and database passwords
5. **Review RBAC**: Ensure proper role assignments for managed identities

## Module Details

See individual module README files for details:
- `modules/foundation/README.md` (if exists)
- `modules/secrets/README.md` (if exists)
- etc.

## Support

For migration issues or questions:
1. Review the migration plan: `/Users/rishabkumar/.claude/plans/eventual-dancing-goose.md`
2. Check Azure resources: `az resource list --resource-group rg-learntocloud-dev`
3. Verify Terraform state: `terraform state list`
4. Run validation: `terraform plan`

## Rollback

If critical issues occur during migration:

```bash
cd scripts
./rollback.sh dev
```

This removes Terraform state (keeping Azure resources intact) and restores Bicep files.

## Additional Resources

- [Terraform Azure Provider Docs](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Azure Developer CLI Docs](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/)
- [Migration Plan](../../../.claude/plans/eventual-dancing-goose.md)
