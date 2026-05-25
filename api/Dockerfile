# syntax=docker/dockerfile:1.13

# Build stage - compile dependencies
# Build context should be repo root: docker build -f api/Dockerfile -t api .
FROM python:3.13-slim AS builder

WORKDIR /workspace

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /usr/local/bin/uv

# Copy dependency files and local path dependencies first for caching
COPY api/pyproject.toml api/pyproject.toml
COPY api/uv.lock api/uv.lock
COPY packages/learn-to-cloud-shared packages/learn-to-cloud-shared

# Disable uv Python downloads (use system Python) and enable bytecode compilation
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_COMPILE_BYTECODE=1

# Install dependencies to virtual environment. Local path dependencies are
# installed non-editably so the runtime image does not need the packages tree.
WORKDIR /workspace/api
RUN uv sync --no-dev --frozen --no-install-project --no-editable

# Tailwind CSS v4 build stage
FROM node:22-slim AS tailwind
WORKDIR /build
COPY api/package.json api/package-lock.json ./
RUN npm ci
COPY api/src/learn_to_cloud/static/css/input.css ./static/css/input.css
COPY api/src/learn_to_cloud/templates/ ./templates/
RUN npx @tailwindcss/cli -i static/css/input.css -o static/css/styles.css --minify

# Shared production base for API and migration images
FROM python:3.13-slim AS runtime-base

WORKDIR /app

# Install tini for proper signal handling
RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get install -y --no-install-recommends tini && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Copy virtual environment from builder
COPY --from=builder /workspace/api/.venv /app/.venv

# Activate virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"
ENV PYTHONPATH="/app/src"

# Enable Python fault handler for debugging
ENV PYTHONFAULTHANDLER=1

# Use tini as init process for proper signal handling and zombie reaping
ENTRYPOINT ["tini", "-g", "--"]

# Switch to non-root user
USER appuser

# Migration stage - Alembic plus curriculum YAML sync
FROM runtime-base AS migrations-runtime

COPY --chown=appuser:appuser api/alembic.ini .
COPY --chown=appuser:appuser api/alembic/ ./alembic/
COPY --chown=appuser:appuser api/scripts/run_migrations.py ./scripts/run_migrations.py
COPY --chown=appuser:appuser packages/learn-to-cloud-shared/src/learn_to_cloud_shared/content/phases /app/content/phases

ENV CONTENT__DIR="/app/content/phases"

CMD ["python", "scripts/run_migrations.py"]

# API stage - request-serving runtime
FROM runtime-base AS api-runtime

# Copy application code from api/. The shared package is already installed in
# the virtual environment, without curriculum YAML package data.
COPY --chown=appuser:appuser api/ .

# Copy Tailwind-generated CSS from build stage
COPY --from=tailwind --chown=appuser:appuser /build/static/css/styles.css /app/src/learn_to_cloud/static/css/styles.css

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "-m", "uvicorn", "learn_to_cloud.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
