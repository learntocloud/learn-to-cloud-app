# syntax=docker/dockerfile:1.13

# Build stage - compile dependencies
# Build context should be repo root: docker build -f api/Dockerfile -t api .
FROM python:3.13-slim AS builder

WORKDIR /workspace

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

# Disable uv Python downloads (use system Python) and enable bytecode compilation
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_COMPILE_BYTECODE=1

# Copy the workspace manifests needed to resolve the locked workspace. All
# member pyproject.toml files must be present so uv can read the workspace
# shape; the single lockfile lives at the repository root.
COPY pyproject.toml uv.lock ./
COPY api/pyproject.toml api/pyproject.toml
COPY packages/learn-to-cloud-shared/pyproject.toml packages/learn-to-cloud-shared/pyproject.toml
COPY apps/verification-functions/pyproject.toml apps/verification-functions/pyproject.toml

# Layer 1 (cached): install only the API package's third-party dependency
# closure, not the workspace members themselves. This pulls api + shared
# dependencies but NOT verification-functions-only dependencies, keeping the
# API image small.
RUN uv sync --package learn-to-cloud-api --no-dev --frozen --no-install-workspace --no-editable

# Copy the source for the members in the API's dependency closure.
COPY api api
COPY packages/learn-to-cloud-shared packages/learn-to-cloud-shared

# Layer 2: build and install the API and shared packages non-editably, so the
# runtime image contains copied packages and does not need the source tree.
RUN uv sync --package learn-to-cloud-api --no-dev --frozen --no-editable

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
COPY --from=builder /workspace/.venv /app/.venv

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
