# syntax=docker/dockerfile:1.13

# Build stage - compile dependencies
# Build context should be repo root: docker build -f api/Dockerfile -t api .
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for caching
COPY api/pyproject.toml ./

# Disable uv Python downloads (use system Python) and enable bytecode compilation
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_COMPILE_BYTECODE=1
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# Install dependencies to virtual environment
RUN uv venv /app/.venv && \
    uv sync --no-dev

# Tailwind CSS v4 build stage
FROM node:22-slim AS tailwind
WORKDIR /build
COPY api/package.json api/package-lock.json ./
RUN npm ci
COPY api/static/css/input.css ./static/css/input.css
COPY api/templates/ ./templates/
RUN npx @tailwindcss/cli -i static/css/input.css -o static/css/styles.css --minify

# Production stage - minimal runtime
FROM python:3.13-slim AS runtime

WORKDIR /app

# Install Cairo library for PDF generation (required by cairosvg) and tini for proper signal handling
RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends libcairo2 tini && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Activate virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# Enable Python fault handler for C crash debugging (useful for cairosvg/Cairo)
ENV PYTHONFAULTHANDLER=1

# Set content directory for Docker
ENV CONTENT_DIR="/app/content/phases"

# Copy application code from api/
COPY --chown=appuser:appuser api/ .

# Copy Tailwind-generated CSS from build stage
COPY --from=tailwind --chown=appuser:appuser /build/static/css/styles.css /app/static/css/styles.css

# Copy content YAML files (single source of truth)
COPY --chown=appuser:appuser content /app/content

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Use tini as init process for proper signal handling and zombie reaping
ENTRYPOINT ["tini", "-g", "--"]

# Run with a single worker — concurrency comes from asyncio (FastAPI is async)
# and horizontal scaling via Container Apps replicas (max_replicas=2).
# Multiple workers use fork(), which breaks the Azure Monitor OTel exporter's
# background threads — logs/traces stop reaching Application Insights post-fork.
# Use python -m uvicorn instead of direct uvicorn to avoid shebang path issues
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
