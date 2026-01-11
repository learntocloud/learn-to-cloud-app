#!/bin/bash
# Smoke test for API Docker image
# Run this after building to verify the image works before pushing
set -euo pipefail

IMAGE_NAME="${1:-learn-to-cloud-api:latest}"
CONTAINER_NAME="smoke-test-$$"
PORT=8080

echo "🔥 Running smoke test for image: $IMAGE_NAME"

# Start container in background with minimal config for smoke test
# Uses SQLite in-memory database for testing (no external dependencies)
echo "Starting container..."
docker run -d --name "$CONTAINER_NAME" -p "$PORT:8000" \
    -e "CLERK_SECRET_KEY=sk_test_placeholder" \
    -e "CLERK_PUBLISHABLE_KEY=pk_test_placeholder" \
    -e "CLERK_WEBHOOK_SIGNING_SECRET=whsec_test_placeholder" \
    "$IMAGE_NAME"

# Wait for container to be healthy
echo "Waiting for container to start..."
sleep 10

# Check if container is still running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "❌ Container crashed during startup"
    echo "Container logs:"
    docker logs "$CONTAINER_NAME" 2>&1 | tail -30
    docker rm "$CONTAINER_NAME" > /dev/null 2>&1 || true
    exit 1
fi

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
