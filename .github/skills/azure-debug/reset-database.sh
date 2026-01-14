#!/bin/bash
# Create database tables for the API
# Uses SQLAlchemy create_all() which is safe - it won't modify existing tables

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

echo "This will create database tables (does not delete existing data)."
echo "Note: create_all() only creates missing tables, it won't modify existing ones."
echo ""
read -p "Continue? (y/n): " CONFIRM

if [ "$CONFIRM" != "y" ]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Creating database tables..."
az containerapp exec \
    --name "$AZURE_API_CONTAINER_APP" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --command "python -c 'import asyncio; from core.database import create_tables; asyncio.run(create_tables())'"

echo ""
echo "✅ Done! Tables created (existing tables were not modified)."
