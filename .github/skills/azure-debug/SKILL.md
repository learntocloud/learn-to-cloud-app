---
name: azure-debug
description: Debug Azure Container Apps by fetching logs, checking status, and managing resources. Use when investigating production errors, checking API health, or viewing deployment status.
---

# Azure Debug Skill

Debug and monitor Learn to Cloud Azure infrastructure including Container Apps, logs, and database.

## Setup

1. Ensure Azure CLI is installed and logged in: `az login`
2. Copy `.env.azure.example` to `.env.azure` and fill in your values
3. Source the environment: `source .env.azure`

See [.env.azure.example](.env.azure.example) for required variables.

## Scripts

### Fetch Logs
Use [fetch-logs.sh](./fetch-logs.sh) to quickly get container logs:
```bash
./fetch-logs.sh api console 100    # API console logs (last 100 lines)
./fetch-logs.sh api system 50      # API system logs
./fetch-logs.sh frontend console   # Frontend logs
```

### Reset Database (Pre-Launch Only)
Use [reset-database.sh](./reset-database.sh) to recreate database schema:
```bash
./reset-database.sh   # Interactive - asks for confirmation
```
⚠️ This destroys all data! Only use before launch.

## Quick Commands

### Check Login & Set Subscription
```bash
az account show --output table
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
```

### List Container Apps
```bash
az containerapp list --resource-group "$AZURE_RESOURCE_GROUP" --output table
```

### Fetch API Logs
```bash
# Console logs (application output)
az containerapp logs show \
  --name "$AZURE_API_CONTAINER_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --type console \
  --tail 100

# System logs (container lifecycle)
az containerapp logs show \
  --name "$AZURE_API_CONTAINER_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --type system \
  --tail 50

# Stream logs in real-time
az containerapp logs show \
  --name "$AZURE_API_CONTAINER_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --type console \
  --follow
```

### Fetch Frontend Logs
```bash
az containerapp logs show \
  --name "$AZURE_FRONTEND_CONTAINER_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --type console \
  --tail 100
```

### Check Container App Status
```bash
az containerapp show \
  --name "$AZURE_API_CONTAINER_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "{status:properties.runningStatus,revision:properties.latestRevisionName,fqdn:properties.configuration.ingress.fqdn}" \
  --output table
```

### View Environment Variables
```bash
az containerapp show \
  --name "$AZURE_API_CONTAINER_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "properties.template.containers[0].env" \
  --output table
```

### Update Environment Variable
```bash
az containerapp update \
  --name "$AZURE_API_CONTAINER_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --set-env-vars "KEY=value"
```

### Restart Container App (Force New Revision)
```bash
az containerapp revision restart \
  --name "$AZURE_API_CONTAINER_APP" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --revision "$(az containerapp show --name $AZURE_API_CONTAINER_APP --resource-group $AZURE_RESOURCE_GROUP --query properties.latestRevisionName -o tsv)"
```

## Common Issues

### Database Schema Mismatch
**Error**: `column X does not exist`  
**Cause**: Model changed but production DB not migrated  
**Fix**: Run [reset-database.sh](./reset-database.sh) (pre-launch only)

### Authentication Errors  
**Error**: `AuthorizationFailed`  
**Fix**: Re-login and set subscription:
```bash
az login
az account set --subscription "$AZURE_SUBSCRIPTION_ID"
```

### Container App Not Found
**Error**: `ResourceNotFound`  
**Fix**: Verify names with `az containerapp list`

## Log Output Format

Logs are JSON lines:
```json
{"TimeStamp": "2026-01-13T14:25:19", "Log": "actual log message"}
```

Parse with jq:
```bash
az containerapp logs show ... 2>&1 | jq -r '.Log'
```

## Related Links

- [Azure Container Apps docs](https://learn.microsoft.com/azure/container-apps/)
- [az containerapp CLI](https://learn.microsoft.com/cli/azure/containerapp)
