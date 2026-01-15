#!/bin/bash
# Export Bicep State - Extract resource IDs from existing Azure deployment
# This script creates a mapping file for importing resources into Terraform

set -e

ENVIRONMENT="${1:-dev}"
RESOURCE_GROUP="rg-learntocloud-${ENVIRONMENT}"
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

echo "======================================"
echo "Exporting Bicep State"
echo "======================================"
echo "Environment:    $ENVIRONMENT"
echo "Resource Group: $RESOURCE_GROUP"
echo "Subscription:   $SUBSCRIPTION_ID"
echo ""

# Output file
OUTPUT_FILE="import-map-${ENVIRONMENT}.json"

# Detect unique suffix from existing PostgreSQL server
echo "Detecting unique suffix from existing resources..."
UNIQUE_SUFFIX=$(az postgres flexible-server list \
  --resource-group "$RESOURCE_GROUP" \
  --query "[0].name" -o tsv 2>/dev/null | grep -oP 'psql-learntocloud-'"$ENVIRONMENT"'-\K.*' || echo "")

if [ -z "$UNIQUE_SUFFIX" ]; then
  echo "ERROR: Could not detect unique suffix. Ensure resources exist in $RESOURCE_GROUP"
  exit 1
fi

echo "✓ Detected unique suffix: $UNIQUE_SUFFIX"
echo ""

# Build comprehensive resource ID map
echo "Creating resource mapping..."

cat > "$OUTPUT_FILE" <<EOF
{
  "subscription_id": "$SUBSCRIPTION_ID",
  "environment": "$ENVIRONMENT",
  "resource_group": "$RESOURCE_GROUP",
  "unique_suffix": "$UNIQUE_SUFFIX",
  "resources": {
    "resource_group": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP",
    "user_assigned_identity": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-learntocloud-$ENVIRONMENT",
    "log_analytics": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.OperationalInsights/workspaces/log-learntocloud-$ENVIRONMENT",
    "app_insights": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Insights/components/appi-learntocloud-$ENVIRONMENT",
    "postgres_server": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-learntocloud-$ENVIRONMENT-$UNIQUE_SUFFIX",
    "postgres_database": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-learntocloud-$ENVIRONMENT-$UNIQUE_SUFFIX/databases/learntocloud",
    "postgres_firewall": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DBforPostgreSQL/flexibleServers/psql-learntocloud-$ENVIRONMENT-$UNIQUE_SUFFIX/firewallRules/AllowAzureServices",
    "redis_cache": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Cache/redis/redis-learntocloud-$ENVIRONMENT-$UNIQUE_SUFFIX",
    "container_registry": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.ContainerRegistry/registries/crltc$UNIQUE_SUFFIX",
    "container_apps_environment": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.App/managedEnvironments/cae-learntocloud-$ENVIRONMENT",
    "key_vault": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/kv-ltc-$ENVIRONMENT-$UNIQUE_SUFFIX",
    "api_container_app": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.App/containerApps/ca-learntocloud-api-$ENVIRONMENT",
    "frontend_container_app": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.App/containerApps/ca-learntocloud-frontend-$ENVIRONMENT",
    "action_group": "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Insights/actionGroups/ag-learntocloud-$ENVIRONMENT"
  }
}
EOF

echo "✓ Resource map created: $OUTPUT_FILE"
echo ""

# Get principal IDs for RBAC role assignments
echo "Extracting principal IDs for RBAC..."

API_PRINCIPAL_ID=$(az containerapp show \
  --name "ca-learntocloud-api-$ENVIRONMENT" \
  --resource-group "$RESOURCE_GROUP" \
  --query identity.principalId -o tsv 2>/dev/null || echo "")

FRONTEND_PRINCIPAL_ID=$(az containerapp show \
  --name "ca-learntocloud-frontend-$ENVIRONMENT" \
  --resource-group "$RESOURCE_GROUP" \
  --query identity.principalId -o tsv 2>/dev/null || echo "")

USER_ASSIGNED_IDENTITY_PRINCIPAL_ID=$(az identity show \
  --name "id-learntocloud-$ENVIRONMENT" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId -o tsv 2>/dev/null || echo "")

# Save principal IDs to separate file
cat > "${OUTPUT_FILE}.principals" <<EOF
API_PRINCIPAL_ID=$API_PRINCIPAL_ID
FRONTEND_PRINCIPAL_ID=$FRONTEND_PRINCIPAL_ID
USER_ASSIGNED_IDENTITY_PRINCIPAL_ID=$USER_ASSIGNED_IDENTITY_PRINCIPAL_ID
EOF

echo "✓ Principal IDs saved: ${OUTPUT_FILE}.principals"
echo ""
echo "======================================"
echo "Export Complete!"
echo "======================================"
echo ""
echo "Files created:"
echo "  - $OUTPUT_FILE (resource IDs)"
echo "  - ${OUTPUT_FILE}.principals (principal IDs for RBAC)"
echo ""
echo "Principal IDs:"
echo "  API Container App:       $API_PRINCIPAL_ID"
echo "  Frontend Container App:  $FRONTEND_PRINCIPAL_ID"
echo "  User-Assigned Identity:  $USER_ASSIGNED_IDENTITY_PRINCIPAL_ID"
echo ""
echo "Next step: Review the migration plan and run import commands"
echo ""
