#!/bin/bash
# Smoke test for Frontend Docker image
# Run this after building to verify the image works before pushing
set -euo pipefail

IMAGE_NAME="${1:-learn-to-cloud-frontend:latest}"
CONTAINER_NAME="smoke-test-frontend-$$"
PORT=3080

echo "🔥 Running smoke test for image: $IMAGE_NAME"

# Start container in background
echo "Starting container..."
docker run -d --name "$CONTAINER_NAME" -p "$PORT:3000" "$IMAGE_NAME"

# Wait for container to start
echo "Waiting for container to start..."
sleep 10

# Test that server responds
echo "Testing root endpoint..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" || echo "000")

# Cleanup
echo "Cleaning up..."
docker stop "$CONTAINER_NAME" > /dev/null
docker rm "$CONTAINER_NAME" > /dev/null

# Check result
if [ "$RESPONSE" = "200" ]; then
    echo "✅ Smoke test PASSED - Server returned 200"
    exit 0
else
    echo "❌ Smoke test FAILED - Server returned $RESPONSE"
    exit 1
fi
