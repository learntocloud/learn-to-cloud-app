#!/bin/bash
# Reset the production database (PRE-LAUNCH ONLY - destroys all data!)
# This enables RESET_DB_ON_STARTUP, waits for tables to recreate, then disables it.

set -e

# Load environment if available
if [ -f "$(dirname "$0")/.env.azure" ]; then
    source "$(dirname "$0")/.env.azure"
fi

if [ -z "$AZURE_API_CONTAINER_APP" ] || [ -z "$AZURE_RESOURCE_GROUP" ]; then
    echo "Error: Environment variables not set."
    echo "Copy .env.azure.example to .env.azure and fill in values."
    exit 1
fi

echo "⚠️  WARNING: This will DELETE ALL DATA in the production database!"
echo "Only use this before launch when there are no real users."
echo ""
read -p "Type 'RESET' to confirm: " CONFIRM

if [ "$CONFIRM" != "RESET" ]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Step 1/3: Enabling database reset..."
az containerapp update \
    --name "$AZURE_API_CONTAINER_APP" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --set-env-vars "RESET_DB_ON_STARTUP=true" "ENVIRONMENT=development" \
    --output none

echo "Step 2/3: Waiting for container restart (30 seconds)..."
sleep 30

# Check if ready
echo "Checking API health..."
FQDN=$(az containerapp show \
    --name "$AZURE_API_CONTAINER_APP" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" \
    --output tsv)

if curl -sf "https://$FQDN/ready" > /dev/null; then
    echo "✓ API is ready"
else
    echo "⚠ API not ready yet, but continuing..."
fi

echo "Step 3/3: Disabling database reset..."
az containerapp update \
    --name "$AZURE_API_CONTAINER_APP" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --set-env-vars "RESET_DB_ON_STARTUP=false" "ENVIRONMENT=dev" \
    --output none

echo ""
echo "✅ Database reset complete!"
echo "The database schema has been recreated from the SQLAlchemy models."
