#!/usr/bin/env bash
#
# Docker preflight check for the devcontainer.
#
# This devcontainer uses "Docker outside of Docker": the Docker CLI runs inside
# the container but talks to the Docker daemon on your host machine through the
# forwarded socket. Run this script to confirm Docker works before you run a
# build or any other Docker-dependent step.
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
    echo "Docker is not available inside this devcontainer."
    echo "This repo expects 'Docker outside of Docker', where the Docker CLI in"
    echo "the container talks to the Docker daemon on your host."
    echo
    echo "To fix it:"
    echo "  1. Make sure Docker is running on your host machine."
    echo "  2. Rebuild the devcontainer (Command Palette: 'Dev Containers:"
    echo "     Rebuild Container') so the docker-outside-of-docker feature and"
    echo "     the forwarded socket are picked up."
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

echo "✅ Docker is available (Docker outside of Docker)."
echo "   docker:         $(docker version --format '{{.Client.Version}}' 2>/dev/null) (client)"
echo "   docker compose: $(docker compose version --short 2>/dev/null)"
echo "   daemon:         reachable ($(docker ps --format '{{.Names}}' | wc -l | tr -d ' ') running container(s))"
echo
echo "Note: the daemon runs on the host, so bind mounts (docker run -v ...) must"
echo "use host paths. Use the LOCAL_WORKSPACE_FOLDER environment variable for the"
echo "repo root instead of /workspaces/learn-to-cloud-app."
