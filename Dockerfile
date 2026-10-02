# syntax=docker/dockerfile:1.13

# Tailwind CSS v4 build stage
FROM node:22-slim AS tailwind
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY src/learn_to_cloud/static/css/input.css ./static/css/input.css
COPY src/learn_to_cloud/templates/ ./templates/
RUN npx @tailwindcss/cli -i static/css/input.css -o static/css/styles.css --minify

# Build stage - install the project and its dependencies into /app/.venv
# Build from the repository root: docker build --target api-runtime -t api .
FROM python:3.13-slim AS builder

# Build at the same path the runtime uses: console-script shebangs in
# .venv/bin are absolute.
WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv

# Disable uv Python downloads (use system Python) and enable bytecode compilation
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock ./

# Layer 1 (cached): install only third-party dependencies.
RUN uv sync --no-dev --frozen --no-install-project --no-editable

COPY src src
COPY --from=tailwind /build/static/css/styles.css src/learn_to_cloud/static/css/styles.css

# Layer 2: build the wheel and install it non-editably. The runtime images
# run only this installed package; no source tree is copied into them.
RUN uv sync --no-dev --frozen --no-editable

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
COPY --from=builder /app/.venv /app/.venv

# Activate virtual environment
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# Enable Python fault handler for debugging
ENV PYTHONFAULTHANDLER=1

# Use tini as init process for proper signal handling and zombie reaping
ENTRYPOINT ["tini", "-g", "--"]

# Switch to non-root user
USER appuser

# Migration stage
FROM runtime-base AS migrations-runtime

CMD ["learn-to-cloud-migrate"]

# API stage - request-serving runtime
FROM runtime-base AS api-runtime

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "learn_to_cloud.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
