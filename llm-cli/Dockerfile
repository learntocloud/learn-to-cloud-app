# syntax=docker/dockerfile:1.13
#
# LLM CLI sidecar — runs in headless server mode for the Python SDK.
# Build context: repo root
#   docker build -f llm-cli/Dockerfile -t llm-cli .

FROM node:22-slim

# Install tini for proper signal handling (PID 1)
# ca-certificates: required for outbound HTTPS from the Go-based CLI binary
# (the CLI bundles a Go binary that needs system CA certs at /etc/ssl/certs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends tini ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install the CLI globally (uses @github/copilot npm package)
RUN npm install -g @github/copilot

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Fixed port so the API sidecar can connect
EXPOSE 4321

# Health check — CLI JSON-RPC server responds on the port
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD node -e "const http = require('http'); http.get('http://localhost:4321', () => process.exit(0)).on('error', () => process.exit(1))"

ENTRYPOINT ["tini", "-g", "--"]

# Run CLI in headless (server) mode on a fixed port.
# Authentication is handled via BYOK — the SDK passes provider config
# per-session and the CLI forwards requests to your model endpoint.
# --verbose: emit request/response lifecycle logs to stderr for debugging
CMD ["copilot", "--headless", "--port", "4321", "--verbose"]
