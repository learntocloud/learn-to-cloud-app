#!/usr/bin/env bash
#
# Docker preflight check for local development.
#
# Run this script to confirm the Docker CLI can reach the daemon before starting
# Compose services, building images, or running other Docker-dependent steps.
#
# Usage: scripts/check-docker.sh
#
# Exit codes:
#   0  Docker CLI is installed and can reach the host daemon.
#   1  Docker is not available (see the printed guidance to fix it).
set -uo pipefail

fail() {
    echo "❌ $1"
    echo
    echo "Docker is not available from this environment."
    echo
    echo "Under WSL, make sure Docker Desktop is running and WSL integration is"
    echo "enabled for this distribution."
    exit 1
}

# 1. Is the Docker CLI on the PATH?
if ! command -v docker >/dev/null 2>&1; then
    fail "The 'docker' command was not found on the PATH."
fi

# 2. Can the CLI reach the daemon? 'docker version' talks to both client and
#    server, so a non-zero exit here means the socket is not reachable.
if ! docker version >/dev/null 2>&1; then
    fail "The 'docker' CLI is installed but cannot reach the host Docker daemon."
fi

# 3. Is the Compose plugin available? The deploy workflow uses 'docker compose'.
if ! docker compose version >/dev/null 2>&1; then
    fail "'docker compose' is not available."
fi

# 4. Can we list containers? Confirms real daemon access, not just a version handshake.
if ! docker ps >/dev/null 2>&1; then
    fail "'docker ps' failed, so the daemon is not fully reachable."
fi

echo "✅ Docker is available."
echo "   docker:         $(docker version --format '{{.Client.Version}}' 2>/dev/null) (client)"
echo "   docker compose: $(docker compose version --short 2>/dev/null)"
echo "   daemon:         reachable ($(docker ps --format '{{.Names}}' | wc -l | tr -d ' ') running container(s))"
