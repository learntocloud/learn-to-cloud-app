#!/bin/bash
# Smoke test for API Docker image
# Run this after building to verify the image works before pushing
set -euo pipefail

IMAGE_NAME="${1:-learn-to-cloud-api:latest}"
CONTAINER_NAME="smoke-test-$$"
PORT=8080

echo "🔥 Running smoke test for image: $IMAGE_NAME"

# Start container in background
echo "Starting container..."
docker run -d --name "$CONTAINER_NAME" -p "$PORT:8000" "$IMAGE_NAME"

# Wait for container to be healthy
echo "Waiting for container to start..."
sleep 5

# Test health endpoint
echo "Testing /health endpoint..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/health" || echo "000")

# Cleanup
echo "Cleaning up..."
docker stop "$CONTAINER_NAME" > /dev/null
docker rm "$CONTAINER_NAME" > /dev/null

# Check result
if [ "$RESPONSE" = "200" ]; then
    echo "✅ Smoke test PASSED - Health check returned 200"
    exit 0
else
    echo "❌ Smoke test FAILED - Health check returned $RESPONSE"
    exit 1
fi
