#!/bin/bash
# Fetch logs from Azure Container Apps
# Usage: ./fetch-logs.sh [api|frontend] [console|system] [lines]

set -e

# Load environment if available
if [ -f "$(dirname "$0")/.env.azure" ]; then
    source "$(dirname "$0")/.env.azure"
fi

SERVICE="${1:-api}"
LOG_TYPE="${2:-console}"
LINES="${3:-100}"

case "$SERVICE" in
    api)
        CONTAINER_APP="$AZURE_API_CONTAINER_APP"
        ;;
    frontend)
        CONTAINER_APP="$AZURE_FRONTEND_CONTAINER_APP"
        ;;
    *)
        echo "Usage: $0 [api|frontend] [console|system] [lines]"
        echo "  api      - Fetch API container logs (default)"
        echo "  frontend - Fetch Frontend container logs"
        echo "  console  - Application output (default)"
        echo "  system   - Container lifecycle events"
        exit 1
        ;;
esac

if [ -z "$CONTAINER_APP" ] || [ -z "$AZURE_RESOURCE_GROUP" ]; then
    echo "Error: Environment variables not set."
    echo "Copy .env.azure.example to .env.azure and fill in values."
    exit 1
fi

echo "Fetching $LOG_TYPE logs from $SERVICE ($CONTAINER_APP)..."
echo "---"

az containerapp logs show \
    --name "$CONTAINER_APP" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --type "$LOG_TYPE" \
    --tail "$LINES"
