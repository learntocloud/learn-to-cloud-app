FROM mcr.microsoft.com/devcontainers/base:debian

# Pre-create the Copilot home directory owned by the vscode user.
# docker-compose.yml mounts a named volume (copilot_home) at this path so the
# Copilot CLI login and plugins survive container rebuilds. When Docker first
# creates that volume it copies the ownership of this directory. Without this
# line the directory does not exist in the image, so Docker creates the volume
# owned by root, the vscode user cannot write to it, and "copilot plugin ..."
# fails silently during onCreate (which aborts the whole devcontainer setup).
RUN mkdir -p /home/vscode/.copilot && chown vscode:vscode /home/vscode/.copilot

# Install the PostgreSQL command-line client (psql). The query-prod-db skill
# uses psql to connect to the production database with Entra ID tokens. The base
# image does not include it, so without this line the skill fails with
# "psql: command not found".
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
