#!/bin/bash
# Smoke test for Frontend Docker image
# Run this after building to verify the image works before pushing
set -euo pipefail

IMAGE_NAME="${1:-learn-to-cloud-frontend:latest}"
CONTAINER_NAME="smoke-test-frontend-$$"
PORT=3080

echo "🔥 Running smoke test for image: $IMAGE_NAME"

# Start container in background with required env vars for Clerk
echo "Starting container..."
docker run -d --name "$CONTAINER_NAME" -p "$PORT:3000" \
    -e "CLERK_SECRET_KEY=sk_test_placeholder" \
    -e "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_placeholder" \
    "$IMAGE_NAME"

# Wait for container to start
echo "Waiting for container to start..."
sleep 15

# Check if container is still running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "❌ Container crashed during startup"
    echo "Container logs:"
    docker logs "$CONTAINER_NAME" 2>&1 | tail -30
    docker rm "$CONTAINER_NAME" > /dev/null 2>&1 || true
    exit 1
fi

# Test that server responds (may return redirect or 500 due to Clerk config, but should at least respond)
echo "Testing root endpoint..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/" || echo "000")

# Cleanup
echo "Cleaning up..."
docker stop "$CONTAINER_NAME" > /dev/null
docker rm "$CONTAINER_NAME" > /dev/null

# Check result - accept 200, 302 (redirect), or 307 (Clerk auth redirect) as valid
if [[ "$RESPONSE" =~ ^(200|302|307)$ ]]; then
    echo "✅ Smoke test PASSED - Server returned $RESPONSE"
    exit 0
else
    echo "❌ Smoke test FAILED - Server returned $RESPONSE"
    exit 1
fi
